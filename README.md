# Kartkówki — panel prac z kodami

Self-hosted Polish classroom assessment panel: printable clean worksheets, answer keys, class rosters, barcode assignment, scan cropping, Codex OAuth grading, manual point marks and revocable student work links.

## Workflow

1. Choose an assessment and class. **Nowy komplet dla klasy** makes a new bundle with new work codes and the same questions. Existing works retain their original identity and key.
2. **Twórz / popraw z Codexem** prepares a draft using a model available in the authenticated Codex session. Review the questions, independently calculated answers and PDF, then save a new bundle for a class. Draft corrections create a new version.
3. Print two works per A4 page. Each work has inward ArUco corners, Code128 and a solution grid. The first three barcode characters identify its group; the full code identifies the work.
4. Assign a work to a pupil by entering a group number or scanning the full code in the pupil row. USB keyboard scanners support Enter and Tab terminators.
5. Scan papers. The worker decodes codes, rectifies each work, and reads names and mathematical steps with the selected Codex model. Unknown pupils, unclear marks and failed imports remain available for review.
6. Scan a barcode in the summary field: **grade → points → pupil → assessment**. The field stays ready for the next scan. Copy a password-in-link URL for the teacher to paste into a Librus grade comment.

Three-point tasks have a triangle divided into three segments; four-point tasks have a square divided into four segments. Each main segment is one point. An adjacent small square has four quarter-point segments: two main segments plus two small segments means 2.5 points. Per-task website corrections use 0.25 increments and update the figures on a graded copy; originals remain intact. Choose **Tryb przycisku Send** to distinguish Codex grading of written solutions from trusted teacher point-mark reading. In Codex mode, pre-existing point figures do not override mathematical grading. Empty figures alone do not establish a completed manual zero grade. Use the upload option **Odczytaj ręczne punkty (także 0)** when importing a manually scored all-zero paper. Ambiguous fills require teacher review.

Dark, light and system themes are available and saved in the browser. Generation, scan review, class mapping and scanner summary are separate actions.

## Grading policies

The chosen school policy determines the grade from points; the language model proposes mathematical observations and points, not percentage thresholds. Exact rational comparisons avoid rounding a result across a boundary.

- **SP 263:** point-scored written work, statute §60(9), page 43: 2 from 31%, 3 from 51%, 4 from 75%, 5 from 91%, 6 at 100%. [Published statute](https://www.sp263.waw.pl/images/2026.02.05_STATUT_AKTUALNY.pdf).
- **ZS 33 / Technikum 6:** 3 from 55%, 4 from 75%, 5 from 93%; 6 requires all base points and at least half of a declared bonus task. [Published statute](https://www.zs33.pl/images/AKTUALNOSCI/2023_2024/PDF/statut%20T%20nr%206.pdf).
- **ZS 33 / BS I stopnia 7:** the same published point scale. [Published statute](https://www.zs33.pl/images/AKTUALNOSCI/2023_2024/PDF/Statut%20BS1S%20nr%207.pdf).

The ZS 33 source leaves a boundary gap around 34%. This deployment's teacher explicitly resolved it as **exactly 34% → 1; every result above 34% → at least 2**, without rounding. A ZS 33 quiz without a bonus tops out at 5. SP 263 also contains a separate general current-grading scale; this panel defaults to the specific point-scored written-work provision, not the older calculator preset. Policies are shown with sources and may be selected per assessment. An unknown school requires configuration rather than guessing.

## Run with Docker

Copy `.env.example` to `.env`, set private values, then:

```sh
mkdir -p data sandbox-data codex-home
sudo chown -R 10001:10001 data sandbox-data codex-home
docker compose build
docker compose up -d
```

Visit the loopback-bound port through your authenticated reverse proxy. Mounts use UID 10001. The application stores SQLite data and files under `/data`; keep the production and sandbox mounts separate. The `sandbox` service uses fictional data only. Bootstrap a test class and a bundle using the panel or the import helper.

The Docker image includes the official Codex CLI. Use **Zaloguj Codexa przez ChatGPT** in the protected panel and complete device authentication. The private Codex home volume persists the server's own OAuth login; do not copy credentials from another machine. Model options come from that session's model catalogue. Text/image calls use `codex exec --ephemeral --sandbox read-only --output-schema …`, with `--` before the prompt.

Application login uses `KARTKOWKI_PASSWORD`. If `KARTKOWKI_TRUST_PROXY_AUTH=1`, the reverse proxy must authenticate requests and overwrite `X-Kartkowki-Teacher`; keep the application port loopback-only. Public individual-work paths `/s/*` do not need portal login, but validate their own unpredictable password. Strip the teacher header on those public routes. Example Caddy configuration is in `deploy/Caddyfile.example`.

The ingest endpoint `/internal/papers/ingest` requires `X-Scanner-Token`. A production web service can mount the sandbox database read-only using `KARTKOWKI_SANDBOX_DB` and forward recognized test codes to `KARTKOWKI_SANDBOX_URL`. A mixed production/test sheet is cropped before routing its works to separate databases. Durable jobs preserve originals and deduplicate retries. The example Send handler in `scanner/` forwards locally instead of uploading through binup. Preserve scanner locking and the existing Paperless import when integrating it.

## MCP and reusable Codex workflow

MCP runs over authenticated SSH/stdio, with no public MCP listener:

```toml
[mcp_servers.kartkowki]
command = "ssh"
args = ["assessment-host", "docker", "exec", "-i", "assessment-web", "python", "/app/assessment_mcp.py"]
```

Tools include assessment listing, model listing, manifests, cropped work reads, grading, clean class cloning, draft proposals, draft inspection and draft publication. Connect the test instance separately. The reusable skill lives in `skills/coded-school-quizzes/`.

No feature submits grades to Librus. The teacher copies links manually; an autofill extension is a separate integration.

## Data and tests

Roster files, pupil names, scans, databases, OAuth homes and private environment files are excluded from the repository and build context. Only necessary roster names and identifiers are used for handwritten-name matching; sensitive pupil notes are not model inputs. Password links expose one cropped graded work, can be copied repeatedly without rotation, and can be revoked. Database rows hold the password hash; a private 0600 file enables repeated copying. Treat the full link as the password to that work.

Back up SQLite and files before deployment. Verify rendered PDFs, arithmetic, all barcodes, corners and crops; a decoder test does not establish physical scanner or handwriting performance. Generation validates exact arithmetic and barcode decoding before a draft can be published.

```sh
python test_school_grading.py
python -m unittest discover -s tests
```

Repeated barcodes are rescan versions, including repeated works within one uploaded PDF. All originals, evaluations and corrections remain available in the version selector; summaries and pupil links show the newest received version. Editing an older version does not change the order. A new upload is a new capture even if bytes are identical. Scanner integrations should send a stable `X-Scan-Id` for retries of one capture, and a fresh ID for each physical scan; a reused ID with different bytes is rejected. Revoking a work link revokes all earlier link tokens for that work.

Scan rectification preserves the whole A5 area (about 8.5 mm beyond the corner markers) and stores a second view with another 12 pt / 4.2 mm of context from the input scan. Codex, work previews and shared work images use that wider view. Point reading uses the original canonical A5 coordinates; overlays are placed inside the stored content frame. Teachers can open the untouched job source through the authenticated `/papers/scan/<id>/source` route. The shared pupil URL never grants access to the whole source document. Existing scans keep working without regeneration; a new rescan receives the wider view. No image can recover writing absent from the original scan.

## Reproducible future worksheets

Future randomized quizzes use a frozen deterministic generator. Codex designs three expression templates, explicit number domains and criteria (for example **the answer must be an integer**); Python draws all numeric values from a seed, rejects division by zero and checks those criteria using exact fractions. An LLM is never needed to replay a printed work. Choose **Nowe liczby losowane z seed i kryteriów** for new randomized data, or **Dokładna korekta wybranych zadań** to preserve specifically approved questions. Exact corrections and class clones freeze their approved values rather than randomizing them again.

The 32-digit Code128 format is `GGG | 9101 | RRRRRRRRRRRRR | SSSSSSSSSS | CC`: three-digit group, protocol v1, a 40-bit source-recipe identifier, a 32-bit seed and a mod-97 typo checksum. Criteria are **in the shared source recipe, not in the barcode**. The numeric format keeps the printed code within the existing 235 pt area at the same 1 pt module width. The recipe ID is an identifier, not a recoverable encoding of its criteria; the barcode is not a password. Old 15-character codes retain their database lookup behavior and are never rewritten.

Download **Generator z kryteriami ZIP** for each new bundle and retain/share that original source package. It includes `recipe.json`, frozen v1 generator/rendering code, exact Python dependency versions, bundled DejaVu fonts and SHA-256 file checks. It contains no pupil roster, scans, grades or OAuth credentials. With that package and one barcode, restore the original clean A5 work and answer key offline:

```sh
python -m pip install -r requirements.txt
python seeded_generator.py SCANNED_BARCODE --render --output restored
```

The restored `Arkusz.pdf` keeps the original barcode. Neither a quiz database, an AI model nor a network connection is used during reconstruction. Retain the original package when updating generators: a new format must get a new version. A mismatched recipe, changed source-package file or damaged barcode fails explicitly. The public repository contains an example in `examples/seeded_integer_recipe_v1.json`; pass it with `--recipe` when using the repository directly. Other quizzes require their own original source recipe/package, not this example.

The teacher panel can also reconstruct a code using its source-file registry at `/papers/recreate/<barcode>.pdf`; this operation does not consult quiz DB rows. Unknown seed codes in the scanner field offer that recovery link. `recreate_clean_work` exposes the same operation to Codex through MCP. The registry and source ZIP are preserved with assessment files. Existing worksheets and their codes/keys remain unchanged.

Tests require Poppler (`pdftoppm`), zbar (`zbarimg`) and DejaVu fonts in addition to Python requirements. The round-trip test unpacks only the original code package, sets an unusable DB location, renders offline, verifies matching tasks and barcodes, and rejects a modified recipe.
