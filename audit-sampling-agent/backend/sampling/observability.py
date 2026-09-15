"""Structured JSON logging with a correlation id carried from an HTTP
request through to job completion (section 8.3).

The id is generated (or read from an inbound X-Correlation-Id header) by
FastAPI middleware, stored in a contextvar so any log call in that
request's call stack can pick it up without threading it through every
function signature, and passed explicitly as a job argument when a
request enqueues a job -- contextvars do not cross the process boundary
to an ARQ worker, so the worker side sets it explicitly from that
argument at the start of the job.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_correlation_id(correlation_id: str) -> None:
    _correlation_id.set(correlation_id)


def get_correlation_id() -> str:
    return _correlation_id.get()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", get_correlation_id()),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def log_with_fields(logger: logging.Logger, level: int, message: str, **fields) -> None:
    # correlation_id is stamped into extra_fields explicitly (not only
    # picked up by JsonFormatter at format time) so callers -- including
    # tests using caplog, which never runs records through the formatter
    # -- can read it straight off the record.
    fields.setdefault("correlation_id", get_correlation_id())
    logger.log(level, message, extra={"extra_fields": fields, "correlation_id": fields["correlation_id"]})
