"""RFC 7807 problem-details error responses (section 6.2)."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_TITLES = {
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    409: "Conflict", 422: "Unprocessable Entity", 429: "Too Many Requests",
    500: "Internal Server Error",
}


def _problem(status_code: int, detail: str, instance: str) -> JSONResponse:
    body = {
        "type": f"https://errors.audit-sampling-agent.local/{status_code}",
        "title": _TITLES.get(status_code, "Error"),
        "status": status_code,
        "detail": detail,
        "instance": instance,
    }
    return JSONResponse(status_code=status_code, content=body)


def register_problem_details(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        response = _problem(exc.status_code, str(exc.detail), str(request.url.path))
        if exc.headers:
            for k, v in exc.headers.items():
                response.headers[k] = v
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(422, str(exc.errors()), str(request.url.path))
