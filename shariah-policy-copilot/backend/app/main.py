import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import documents, query, review
from app.database import init_db

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Shariah Policy Copilot",
    description=(
        "Internal research assistant that retrieves approved Shariah rulings/standards, "
        "compares them, and produces a cited evidence pack for human Shariah review. "
        "This system never issues a fatwa."
    ),
    version="1.0.0",
)

# Dev-only: allow the local Vite frontend to call this API from a different origin/port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Starlette's default 500 response bypasses CORSMiddleware (it sits outside the
    # exception-handling layer), so the frontend just sees an opaque CORS failure
    # instead of the real error. Handling it here keeps the response in the normal
    # flow so CORS headers still get attached.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(documents.router)
app.include_router(query.router)
app.include_router(review.router)
