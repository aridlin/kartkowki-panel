"""Teacher-controlled quiz workflow. No route submits a grade to Librus."""
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import subprocess
import tempfile
import unicodedata
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_file, session, url_for
from PIL import Image
from werkzeug.middleware.proxy_fix import ProxyFix

from grade_rules import grade, percent, school_grade, class_profile
from model import observe, suggest_open, propose_questions
from scans import pages, read_code, read_name

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("KARTKOWKI_DATA", ROOT / "data")).expanduser().resolve()
DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
DATA.chmod(0o700)
(DATA / "scans").mkdir(mode=0o700, exist_ok=True)
DB = DATA / "kartkowki.sqlite3"
APP = Flask(__name__)
APP.wsgi_app = ProxyFix(APP.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
APP.secret_key = os.environ.get("KARTKOWKI_SECRET") or secrets.token_bytes(32)
APP.config.update(MAX_CONTENT_LENGTH=40 * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE="Strict")
if os.environ.get("KARTKOWKI_PUBLIC_BASE"):
    APP.config["SESSION_COOKIE_SECURE"] = True


@contextmanager
def conn():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    with conn() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS roster(class_name TEXT NOT NULL, librus_id TEXT NOT NULL,
            name TEXT NOT NULL, PRIMARY KEY(class_name,librus_id));
        CREATE TABLE IF NOT EXISTS quizzes(id TEXT PRIMARY KEY, class_name TEXT NOT NULL,
            title TEXT NOT NULL, questions TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sheets(code TEXT PRIMARY KEY, quiz_id TEXT NOT NULL,
            group_label TEXT NOT NULL, layout TEXT NOT NULL,
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id));
        CREATE TABLE IF NOT EXISTS responses(code TEXT PRIMARY KEY, quiz_id TEXT NOT NULL,
            scan_path TEXT NOT NULL, observed_name TEXT NOT NULL DEFAULT '',
            student_id TEXT, answers TEXT NOT NULL DEFAULT '[]', open_points TEXT NOT NULL DEFAULT '{}',
            explanation TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'needs_review',
            paperless_id TEXT, paperless_task TEXT, share_hash TEXT, share_token TEXT,
            share_expires TEXT, updated TEXT NOT NULL,
            FOREIGN KEY(code) REFERENCES sheets(code));
        CREATE UNIQUE INDEX IF NOT EXISTS one_response_per_student
            ON responses(quiz_id,student_id) WHERE student_id IS NOT NULL AND status='reviewed';
        """)


init_db()


def teacher(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        proxy_teacher = (os.environ.get("KARTKOWKI_TRUST_PROXY_AUTH") == "1" and
                         request.headers.get("X-Kartkowki-Teacher") == "1")
        if not session.get("teacher") and not proxy_teacher:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped


@APP.before_request
def check_origin():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            abort(403)


def fail(message, status=400):
    return jsonify({"error": message}), status


def norm(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(c for c in value if not unicodedata.combining(c) and c.isalnum() or c.isspace()).split())


def now():
    return datetime.now(timezone.utc).isoformat()


@APP.get("/login")
def login():
    return render_template("login.html")


@APP.post("/login")
def do_login():
    password = os.environ.get("KARTKOWKI_PASSWORD")
    if not password:
        return "Set KARTKOWKI_PASSWORD on the server", 503
    if not hmac.compare_digest(request.form.get("password", ""), password):
        return render_template("login.html", error="Nieprawidłowe hasło"), 403
    session.clear()
    session["teacher"] = True
    return redirect(url_for("home"))


@APP.post("/logout")
@teacher
def logout():
    session.clear()
    return redirect(url_for("login"))


@APP.get("/")
@teacher
def home():
    return render_template("papers.html", base=url_for("home"), sandbox=os.environ.get("KARTKOWKI_SANDBOX")=="1")


@APP.get("/api/state")
@teacher
def state():
    with conn() as db:
        quizzes = [dict(r) for r in db.execute("SELECT id,class_name,title,created FROM quizzes ORDER BY created DESC")]
        classes = [dict(r) for r in db.execute("SELECT class_name,COUNT(*) count FROM roster GROUP BY class_name ORDER BY class_name")]
    return jsonify({"quizzes": quizzes, "classes": classes})


@APP.post("/api/roster")
@teacher
def import_roster():
    name = request.form.get("class_name", "").strip()
    file = request.files.get("file")
    if not name or not file:
        return fail("Class name and CSV file are required")
    try:
        content = file.read().decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(content)))
        if not rows or not {"id", "name"}.issubset(rows[0]):
            return fail("CSV needs id,name columns")
        students = [(name, str(r["id"]).strip(), str(r["name"]).strip()) for r in rows]
        if any(not sid or not person for _, sid, person in students) or len({s[1] for s in students}) != len(students):
            return fail("Empty or duplicate student IDs")
        with conn() as db:
            db.execute("DELETE FROM roster WHERE class_name=?", (name,))
            db.executemany("INSERT INTO roster VALUES(?,?,?)", students)
        return jsonify({"class_name": name, "count": len(students)})
    except (UnicodeError, csv.Error, KeyError) as exc:
        return fail(str(exc))


def validate_questions(items):
    if not isinstance(items, list) or not items:
        raise ValueError("Add at least one question")
    seen = set()
    clean = []
    for index, q in enumerate(items, 1):
        typ = q.get("type")
        qid = str(q.get("id") or f"q{index}")
        prompt = str(q.get("prompt", "")).strip()
        points = float(q.get("points", 0))
        if qid in seen or typ not in {"single", "multi", "open"} or not prompt or points <= 0:
            raise ValueError(f"Question {index} is incomplete")
        seen.add(qid)
        options = q.get("options", [])
        correct = q.get("correct", [])
        if typ != "open":
            if not isinstance(options, list) or not 2 <= len(options) <= 8 or any(not str(x).strip() for x in options):
                raise ValueError(f"Question {index} needs 2–8 answer choices")
            if not isinstance(correct, list) or not correct or any(not isinstance(x, int) or x < 0 or x >= len(options) for x in correct):
                raise ValueError(f"Question {index} needs correct choice indexes")
            if typ == "single" and len(correct) != 1:
                raise ValueError("Single choice needs one correct answer")
        else:
            options, correct = [], []
        clean.append({"id": qid, "type": typ, "prompt": prompt, "points": points,
                      "options": [str(x).strip() for x in options], "correct": sorted(set(correct)),
                      "rubric": str(q.get("rubric", "")).strip()})
    return clean


@APP.post("/api/quizzes")
@teacher
def create_quiz():
    body = request.get_json(silent=True) or {}
    try:
        questions = validate_questions(body.get("questions"))
    except (ValueError, TypeError) as exc:
        return fail(str(exc))
    class_name, title = str(body.get("class_name", "")).strip(), str(body.get("title", "")).strip()
    if not class_name or not title:
        return fail("Class and title are required")
    with conn() as db:
        if not db.execute("SELECT 1 FROM roster WHERE class_name=?", (class_name,)).fetchone():
            return fail("Import the class roster first")
        qid = secrets.token_hex(8)
        db.execute("INSERT INTO quizzes VALUES(?,?,?,?,?)", (qid, class_name, title,
                   json.dumps(questions, ensure_ascii=False), now()))
    return jsonify({"id": qid})


@APP.post("/api/questions/propose")
@teacher
def propose():
    body = request.get_json(silent=True) or {}
    topic = str(body.get("topic", "")).strip()
    provider = body.get("provider", "codex")
    if not 5 <= len(topic) <= 1000 or provider not in {"codex", "ollama"}:
        return fail("Give a topic and choose a provider")
    try:
        questions = validate_questions(propose_questions(topic, provider))
        return jsonify({"questions": questions})
    except Exception as exc:
        return fail(str(exc)[:300], 502)


@APP.post("/api/quizzes/<quiz_id>/sheets")
@teacher
def create_sheets(quiz_id):
    body = request.get_json(silent=True) or {}
    try:
        count = int(body.get("count", 0))
        variants = int(body.get("variants", 1))
    except (TypeError, ValueError):
        return fail("Invalid copy count")
    if not 1 <= count <= 100 or not 1 <= variants <= 30:
        return fail("Use 1–100 sheets and 1–30 variants")
    with conn() as db:
        quiz = db.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()
        if not quiz:
            abort(404)
        questions = json.loads(quiz["questions"])
        for i in range(count):
            v = i % variants
            layout = []
            for q in questions:
                # Rotate the printed choice order per variant, preserving choice IDs.
                indexes = list(range(len(q["options"])))
                if indexes:
                    offset = v % len(indexes)
                    indexes = indexes[offset:] + indexes[:offset]
                layout.append({**q, "options": [
                    {"letter": chr(65 + k), "text": q["options"][original], "original": original}
                    for k, original in enumerate(indexes)]})
            code = "K-" + secrets.token_urlsafe(15)
            db.execute("INSERT INTO sheets VALUES(?,?,?,?)", (code, quiz_id, str(v + 1),
                       json.dumps(layout, ensure_ascii=False)))
    return jsonify({"print_url": url_for("print_sheets", quiz_id=quiz_id), "count": count})


def qr_data(code):
    encoded = subprocess.run(["qrencode", "-m", "2", "-s", "8", "-o", "-", code],
                             capture_output=True, check=True, timeout=10).stdout
    import base64
    return "data:image/png;base64," + base64.b64encode(encoded).decode("ascii")


@APP.get("/print/<quiz_id>")
@teacher
def print_sheets(quiz_id):
    with conn() as db:
        quiz = db.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()
        if not quiz:
            abort(404)
        sheets = [{**dict(r), "layout": json.loads(r["layout"]), "qr": qr_data(r["code"])}
                  for r in db.execute("SELECT * FROM sheets WHERE quiz_id=? ORDER BY rowid", (quiz_id,))]
    return render_template("print.html", quiz=quiz, sheets=sheets)


def match_student(db, class_name, name):
    if not name:
        return None
    candidates = [(r["librus_id"], SequenceMatcher(None, norm(name), norm(r["name"])).ratio())
                  for r in db.execute("SELECT librus_id,name FROM roster WHERE class_name=?", (class_name,))]
    candidates.sort(key=lambda x: x[1], reverse=True)
    if candidates and candidates[0][1] >= .92 and (len(candidates) == 1 or candidates[0][1] - candidates[1][1] >= .12):
        return candidates[0][0]
    return None


@APP.post("/api/quizzes/<quiz_id>/scans")
@teacher
def import_scans(quiz_id):
    files = request.files.getlist("files")
    provider = request.form.get("provider", "codex")
    if provider not in {"codex", "ollama"} or not files:
        return fail("Select scans and a model provider")
    with conn() as db:
        quiz = db.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()
        if not quiz:
            abort(404)
        results = []
        for file in files:
            try:
                for image_bytes in pages(file.read(), file.filename):
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        tmp.write(image_bytes)
                        tmp_path = Path(tmp.name)
                    try:
                        code = read_code(tmp_path)
                        if not code:
                            results.append({"status": "unreadable_qr", "file": file.filename})
                            continue
                        sheet = db.execute("SELECT * FROM sheets WHERE code=? AND quiz_id=?", (code, quiz_id)).fetchone()
                        if not sheet:
                            results.append({"status": "unknown_qr", "file": file.filename})
                            continue
                        if db.execute("SELECT 1 FROM responses WHERE code=?", (code,)).fetchone():
                            results.append({"status": "duplicate", "code": code})
                            continue
                        scan_path = DATA / "scans" / (hashlib.sha256(code.encode()).hexdigest() + ".png")
                        scan_path.write_bytes(image_bytes)
                        scan_path.chmod(0o600)
                        layout = json.loads(sheet["layout"])
                        try:
                            observation = observe(tmp_path, layout, provider)
                            model_error = None
                        except Exception as exc:
                            observation = {"student_name": read_name(tmp_path), "answers": [
                                {"question_id": q["id"], "selected": [], "text": "", "uncertain": True} for q in layout]}
                            model_error = str(exc)[:300]
                        name = observation["student_name"] or read_name(tmp_path)
                        sid = match_student(db, quiz["class_name"], name)
                        db.execute("INSERT INTO responses(code,quiz_id,scan_path,observed_name,student_id,answers,updated) VALUES(?,?,?,?,?,?,?)",
                                   (code, quiz_id, str(scan_path), name, sid,
                                    json.dumps(observation["answers"], ensure_ascii=False), now()))
                        results.append({"status": "needs_review", "code": code, "name": name,
                                        "matched_id": sid, "model_error": model_error})
                    finally:
                        tmp_path.unlink(missing_ok=True)
            except Exception as exc:
                results.append({"status": "error", "file": file.filename, "error": str(exc)[:300]})
        db.commit()
    return jsonify({"results": results})


@APP.get("/api/quizzes/<quiz_id>/review")
@teacher
def review_list(quiz_id):
    with conn() as db:
        quiz = db.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()
        if not quiz:
            abort(404)
        roster = [dict(r) for r in db.execute("SELECT librus_id,name FROM roster WHERE class_name=? ORDER BY name", (quiz["class_name"],))]
        responses = []
        for r in db.execute("SELECT r.*,s.layout,s.group_label FROM responses r JOIN sheets s USING(code) WHERE r.quiz_id=? ORDER BY r.updated", (quiz_id,)):
            item = dict(r)
            item.pop("scan_path")
            item.pop("share_hash")
            item.pop("share_token")
            item["answers"] = json.loads(item["answers"])
            item["open_points"] = json.loads(item["open_points"])
            item["layout"] = json.loads(item["layout"])
            item["scan_url"] = url_for("scan_image", code=r["code"])
            responses.append(item)
    return jsonify({"quiz": {"id": quiz["id"], "title": quiz["title"], "class_name": quiz["class_name"]},
                    "roster": roster, "responses": responses})


@APP.get("/scan/<code>")
@teacher
def scan_image(code):
    with conn() as db:
        row = db.execute("SELECT scan_path FROM responses WHERE code=?", (code,)).fetchone()
    if not row:
        abort(404)
    return send_file(row["scan_path"], mimetype="image/png")


def score(layout, answers, open_points):
    by_id = {a["question_id"]: a for a in answers}
    total = 0.0
    maximum = 0.0
    for q in layout:
        maximum += q["points"]
        answer = by_id.get(q["id"])
        if not answer or answer.get("uncertain"):
            raise ValueError("Every answer must be reviewed and marked certain")
        if q["type"] == "open":
            if q["id"] not in open_points:
                raise ValueError("Approve points for each open answer")
            points = float(open_points[q["id"]])
            if not 0 <= points <= q["points"]:
                raise ValueError("Open-answer points outside range")
            total += points
        else:
            selected = answer.get("selected", [])
            if q["type"] == "single" and len(selected) > 1:
                raise ValueError("Too many choices in a single-choice question")
            actual = {o["original"] for o in q["options"] if o["letter"] in selected}
            if actual == set(q["correct"]):
                total += q["points"]
    return total, maximum


@APP.post("/api/responses/<code>/review")
@teacher
def save_review(code):
    body = request.get_json(silent=True) or {}
    with conn() as db:
        row = db.execute("SELECT r.*,s.layout,q.class_name FROM responses r JOIN sheets s USING(code) JOIN quizzes q ON q.id=r.quiz_id WHERE r.code=?", (code,)).fetchone()
        if not row:
            abort(404)
        sid = str(body.get("student_id", "")).strip()
        if not db.execute("SELECT 1 FROM roster WHERE class_name=? AND librus_id=?", (row["class_name"], sid)).fetchone():
            return fail("Choose a student from this class")
        answers = body.get("answers")
        layout = json.loads(row["layout"])
        if not isinstance(answers, list) or {a.get("question_id") for a in answers if isinstance(a, dict)} != {q["id"] for q in layout}:
            return fail("Review every answer")
        open_points = body.get("open_points", {})
        try:
            points, maximum = score(layout, answers, open_points)
            calculated = school_grade(points, maximum, class_profile(row["class_name"]))
        except (ValueError, TypeError, KeyError) as exc:
            return fail(str(exc))
        explanation = str(body.get("explanation", "")).strip()
        if len(explanation) > 600:
            return fail("Explanation is too long")
        if not explanation:
            explanation = f"Kartkówka: {points:g}/{maximum:g} pkt ({percent(points, maximum):g}%)."
        try:
            db.execute("UPDATE responses SET student_id=?,answers=?,open_points=?,explanation=?,status='reviewed',updated=? WHERE code=?",
                       (sid, json.dumps(answers, ensure_ascii=False), json.dumps(open_points), explanation, now(), code))
        except sqlite3.IntegrityError:
            return fail("Another reviewed scan is already assigned to this student")
    return jsonify({"points": points, "maximum": maximum, "grade": calculated, "explanation": explanation})


@APP.post("/api/responses/<code>/suggest")
@teacher
def open_suggestion(code):
    body = request.get_json(silent=True) or {}
    provider = body.get("provider", "codex")
    if provider not in {"codex", "ollama"}:
        return fail("Invalid provider")
    with conn() as db:
        row = db.execute("SELECT r.scan_path,r.answers,s.layout FROM responses r JOIN sheets s USING(code) WHERE code=?", (code,)).fetchone()
    if not row:
        abort(404)
    layout = json.loads(row["layout"])
    q = next((q for q in layout if q["id"] == body.get("question_id") and q["type"] == "open"), None)
    if not q:
        return fail("Choose an open question")
    answer = next((a["text"] for a in json.loads(row["answers"]) if a["question_id"] == q["id"]), "")
    try:
        suggestion = suggest_open(row["scan_path"], q, answer, provider)
        return jsonify(suggestion)
    except Exception as exc:
        return fail(str(exc)[:300], 502)


def paperless_upload(row):
    base = os.environ.get("KARTKOWKI_PAPERLESS_URL", "").rstrip("/")
    token = os.environ.get("KARTKOWKI_PAPERLESS_TOKEN", "")
    if not base or not token:
        return None
    with open(row["scan_path"], "rb") as fh:
        res = requests.post(base + "/api/documents/post_document/",
                            headers={"Authorization": "Token " + token},
                            files={"document": (f"kartkowka-{row['code']}.png", fh, "image/png")},
                            data={"title": f"Kartkówka {row['code']}"}, timeout=90)
    res.raise_for_status()
    return res.text.strip().strip('"')


def paperless_task_status(task_id):
    base = os.environ["KARTKOWKI_PAPERLESS_URL"].rstrip("/")
    token = os.environ["KARTKOWKI_PAPERLESS_TOKEN"]
    res = requests.get(base + "/api/tasks/", params={"task_id": task_id},
                       headers={"Authorization": "Token " + token}, timeout=20)
    res.raise_for_status()
    payload = res.json()
    tasks = payload.get("results", []) if isinstance(payload, dict) else payload
    task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if not task:
        return "pending", None
    status = str(task.get("status", "")).lower()
    data = task.get("result_data") or {}
    document_id = data.get("document_id") if isinstance(data, dict) else None
    if not document_id and status == "success":
        legacy = task.get("result")
        if isinstance(legacy, int) or isinstance(legacy, str) and legacy.isdigit():
            document_id = legacy
    return status, str(document_id) if document_id else None


@APP.post("/api/responses/<code>/share")
@teacher
def make_share(code):
    base = os.environ.get("KARTKOWKI_PUBLIC_BASE", "").rstrip("/")
    end = os.environ.get("KARTKOWKI_SCHOOL_YEAR_END", "")
    if not base.startswith("https://"):
        return fail("Configure public HTTPS base URL")
    try:
        if date.fromisoformat(end) <= date.today():
            raise ValueError
    except ValueError:
        return fail("Configure a future KARTKOWKI_SCHOOL_YEAR_END")
    with conn() as db:
        row = db.execute("SELECT * FROM responses WHERE code=? AND status='reviewed'", (code,)).fetchone()
        if not row:
            return fail("Review this scan first")
        task = row["paperless_task"]
        if not task and not row["paperless_id"] and os.environ.get("KARTKOWKI_PAPERLESS_TOKEN"):
            try:
                task = paperless_upload(row)
            except requests.RequestException as exc:
                return fail(f"Paperless upload failed: {str(exc)[:200]}", 502)
        raw = secrets.token_urlsafe(32)
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        db.execute("UPDATE responses SET share_hash=?,share_token=?,share_expires=?,paperless_task=?,updated=? WHERE code=?",
                   (hashed, raw, end, task, now(), code))
    return jsonify({"url": base + "/s/" + raw, "expires": end, "paperless_task": task})


@APP.post("/api/responses/<code>/paperless-sync")
@teacher
def sync_paperless(code):
    with conn() as db:
        row = db.execute("SELECT paperless_task,paperless_id FROM responses WHERE code=?", (code,)).fetchone()
        if not row:
            abort(404)
        if row["paperless_id"]:
            return jsonify({"status": "success", "document_id": row["paperless_id"]})
        if not row["paperless_task"]:
            return fail("Upload to Paperless has not been started")
        try:
            status, doc_id = paperless_task_status(row["paperless_task"])
        except requests.RequestException as exc:
            return fail(str(exc)[:300], 502)
        if doc_id:
            db.execute("UPDATE responses SET paperless_id=?,updated=? WHERE code=?", (doc_id, now(), code))
    return jsonify({"status": status, "document_id": doc_id})


@APP.post("/api/responses/<code>/revoke")
@teacher
def revoke_share(code):
    with conn() as db:
        db.execute("UPDATE responses SET share_hash=NULL,share_token=NULL,share_expires=NULL,updated=? WHERE code=?", (now(), code))
    return jsonify({"revoked": True})


@APP.get("/s/<token>")
def public_scan(token):
    if len(token) > 100:
        abort(404)
    hashed = hashlib.sha256(token.encode()).hexdigest()
    with conn() as db:
        row = db.execute("SELECT scan_path,share_expires FROM responses WHERE share_hash=? AND status='reviewed'", (hashed,)).fetchone()
    if not row or not row["share_expires"] or date.fromisoformat(row["share_expires"]) < date.today():
        abort(404)
    response = send_file(row["scan_path"], mimetype="image/png", as_attachment=False)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@APP.get("/api/quizzes/<quiz_id>/export")
@teacher
def export_librus(quiz_id):
    base = os.environ.get("KARTKOWKI_PUBLIC_BASE", "").rstrip("/")
    with conn() as db:
        quiz = db.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()
        if not quiz:
            abort(404)
        rows = db.execute("SELECT r.*,s.layout,ro.name FROM responses r JOIN sheets s USING(code) LEFT JOIN roster ro ON ro.class_name=? AND ro.librus_id=r.student_id WHERE r.quiz_id=?", (quiz["class_name"], quiz_id)).fetchall()
    if not rows:
        return fail("No scanned works")
    if any(r["status"] != "reviewed" or not r["student_id"] for r in rows):
        return fail("Review every scanned work before export")
    if any(not r["share_hash"] or not r["share_token"] for r in rows):
        return fail("Create a scan link for every reviewed work")
    if os.environ.get("KARTKOWKI_PAPERLESS_TOKEN") and any(not r["paperless_id"] for r in rows):
        return fail("Confirm every Paperless import before export")
    items = []
    for r in rows:
        points, maximum = score(json.loads(r["layout"]), json.loads(r["answers"]), json.loads(r["open_points"]))
        result = school_grade(points, maximum, class_profile(quiz["class_name"]))
        items.append({"librus_id": r["student_id"], "name": r["name"], "grade": result,
                      "points": points, "maximum": maximum,
                      "comment": r["explanation"] + " Skan: " + base + "/s/" + r["share_token"]})
    data = json.dumps({"format": "kartkowki-librus-v1", "class_name": quiz["class_name"],
                       "title": quiz["title"], "students": items}, ensure_ascii=False, indent=2)
    return Response(data, mimetype="application/json", headers={"Content-Disposition": f"attachment; filename=kartkowka-{quiz_id}-librus.json", "Cache-Control": "no-store"})


from paper_workflow import register as register_papers
register_papers(APP, teacher)

if __name__ == "__main__":
    host = os.environ.get("KARTKOWKI_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost"} and not os.environ.get("KARTKOWKI_PUBLIC_BASE", "").startswith("https://"):
        raise SystemExit("Non-loopback binding requires KARTKOWKI_PUBLIC_BASE=https://...")
    APP.run(host=host, port=int(os.environ.get("KARTKOWKI_PORT", "8765")))
