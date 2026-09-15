# Multi-stage build: install deps in a builder layer, copy only the
# installed packages + source into a slim runtime layer, run as a
# non-root user.
FROM python:3.13-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=app:app . .

USER app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "sampling.api:app", "--host", "0.0.0.0", "--port", "8000"]
