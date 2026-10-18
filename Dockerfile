FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    qrencode zbar-tools poppler-utils tesseract-ocr tesseract-ocr-pol nodejs npm \
    && rm -rf /var/lib/apt/lists/*
RUN npm install --global @openai/codex@0.156.1 && npm cache clean --force

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py grade_rules.py model.py scans.py paper_workflow.py paper_worker.py scan_geometry.py assessment_mcp.py import_papers.py points_marks.py paper_generator.py paper_authoring.py seeded_generator.py seeded_generator_v2.py paper_generator_v2.py /app/
COPY templates /app/templates
COPY static /app/static
RUN useradd --uid 10001 --create-home kartkowki && mkdir /data /home/kartkowki/.codex && chown -R kartkowki:kartkowki /data /home/kartkowki/.codex
USER kartkowki
ENV KARTKOWKI_DATA=/data KARTKOWKI_HOST=0.0.0.0 KARTKOWKI_PORT=8765
EXPOSE 8765
CMD ["gunicorn", "--bind", "0.0.0.0:8765", "--workers", "2", "--threads", "4", "--timeout", "240", "app:APP"]
