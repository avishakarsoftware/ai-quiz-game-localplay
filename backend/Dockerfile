# 3.14 to match CI and the local dev venv (REVIEW-2026-08 O5) — before this, all 1,400+
# backend tests ran on an interpreter prod never used. Timing-sensitive asyncio code makes
# version skew a real risk, not a cosmetic one.
FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY static ./static

ENV FRONTEND_DIST_DIR=/app/static

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
