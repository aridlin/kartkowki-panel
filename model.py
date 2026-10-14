"""Small, replaceable vision/text adapter. Models only propose structured observations."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import requests

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["student_name", "answers"],
    "properties": {
        "student_name": {"type": "string"},
        "answers": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["question_id", "selected", "text", "uncertain"],
            "properties": {
                "question_id": {"type": "string"},
                "selected": {"type": "array", "items": {"type": "string"}},
                "text": {"type": "string"},
                "uncertain": {"type": "boolean"},
            },
        }},
    },
}

AUTHOR_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["questions"],
    "properties": {"questions": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["type", "prompt", "points", "options", "correct", "rubric"],
        "properties": {
            "type": {"type": "string", "enum": ["single", "multi", "open"]},
            "prompt": {"type": "string"}, "points": {"type": "number"},
            "options": {"type": "array", "items": {"type": "string"}},
            "correct": {"type": "array", "items": {"type": "integer"}},
            "rubric": {"type": "string"},
        },
    }}},
}


def _run_codex(prompt, image=None, schema=SCHEMA, model=None, timeout=180):
    with tempfile.TemporaryDirectory() as d:
        schema_path = Path(d) / "schema.json"
        output_path = Path(d) / "result.json"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        command = ["codex", "exec", "--ephemeral", "--skip-git-repo-check",
                   "--sandbox", "read-only", "--output-schema", str(schema_path),
                   "--output-last-message", str(output_path)]
        if model:
            command += ["--model", model]
        if image:
            command += ["--image", str(image)]
        command += ["--", prompt]
        subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True,
                       cwd=d)
        return json.loads(output_path.read_text(encoding="utf-8"))


def _run_ollama(prompt, image=None, schema=SCHEMA):
    import base64
    url = os.environ.get("KARTKOWKI_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("KARTKOWKI_OLLAMA_MODEL")
    if not model:
        raise ValueError("KARTKOWKI_OLLAMA_MODEL is required")
    message = {"role": "user", "content": prompt}
    if image:
        message["images"] = [base64.b64encode(Path(image).read_bytes()).decode("ascii")]
    response = requests.post(url + "/api/chat", json={"model": model, "messages": [message],
                                                 "stream": False, "format": schema}, timeout=180)
    response.raise_for_status()
    return json.loads(response.json()["message"]["content"])


def observe(image, layout, provider):
    questions = [{"question_id": q["id"], "type": q["type"],
                  "letters": [o["letter"] for o in q.get("options", [])]}
                 for q in layout]
    prompt = (
        "Read this single Polish classroom quiz sheet. Return only JSON matching the supplied "
        "schema. Copy the handwritten name; use an empty string if unreadable. For each question "
        "report the printed answer letters that are clearly marked. For an open question put the "
        "student's writing in text. Do not solve any question, infer intent, or guess marks. If a "
        "mark is ambiguous set uncertain=true. Include every question exactly once. "
        "Questions: " + json.dumps(questions, ensure_ascii=False)
    )
    result = _run_codex(prompt, image) if provider == "codex" else _run_ollama(prompt, image)
    validate_observation(result, layout)
    return result


def validate_observation(result, layout):
    if not isinstance(result, dict) or not isinstance(result.get("student_name"), str):
        raise ValueError("Invalid model output: name")
    answers = result.get("answers")
    if not isinstance(answers, list) or len(answers) != len(layout):
        raise ValueError("Invalid model output: answer count")
    seen = set()
    by_id = {q["id"]: q for q in layout}
    for answer in answers:
        if not isinstance(answer, dict) or answer.get("question_id") not in by_id:
            raise ValueError("Invalid model output: question ID")
        qid = answer["question_id"]
        if qid in seen:
            raise ValueError("Invalid model output: duplicate question")
        seen.add(qid)
        if not isinstance(answer.get("selected"), list) or not isinstance(answer.get("text"), str) or not isinstance(answer.get("uncertain"), bool):
            raise ValueError("Invalid model output: answer fields")
        allowed = {o["letter"] for o in by_id[qid].get("options", [])}
        if any(x not in allowed for x in answer["selected"]):
            raise ValueError("Invalid model output: answer letter")
        if len(set(answer["selected"])) != len(answer["selected"]):
            raise ValueError("Invalid model output: duplicate letter")


def suggest_open(image, question, answer, provider):
    prompt = (
        "A teacher needs a tentative evaluation of a Polish open-answer quiz question. "
        "Return one JSON object with student_name as an empty string and exactly one answers "
        "item: question_id, selected empty, text as a short Polish explanation of the proposed "
        "score, uncertain=true. Start text with 'Punkty: N;'. Award between 0 and maximum. "
        "This is a suggestion for teacher approval, not a final grade. "
        + json.dumps({"question_id": question["id"], "question": question["prompt"],
                      "rubric": question.get("rubric", ""), "maximum": question["points"],
                      "student_answer": answer}, ensure_ascii=False)
    )
    return _run_codex(prompt, image) if provider == "codex" else _run_ollama(prompt, image)


def propose_questions(topic, provider):
    prompt = (
        "Propose exactly three Polish classroom quiz questions about the teacher's topic. "
        "Use single or multi choice by default; include an open question only if the teacher asks for one. "
        "For single choice supply exactly one correct 0-based option index. For multiple choice "
        "supply all correct 0-based indexes. Every question has 3 points. Make distractors plausible "
        "and check the key carefully. Return only JSON matching the schema. Topic: " + topic
    )
    result = _run_codex(prompt, schema=AUTHOR_SCHEMA) if provider == "codex" else _run_ollama(prompt, schema=AUTHOR_SCHEMA)
    if not isinstance(result, dict) or not isinstance(result.get("questions"), list):
        raise ValueError("Invalid authoring output")
    return result["questions"]
