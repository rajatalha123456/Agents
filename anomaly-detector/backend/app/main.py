import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .routers import generic_anomaly, uploads

app = FastAPI(
    title="Mizan API",
    description="Generic explainable anomaly detection agent: upload a CSV or JSON "
                 "file and get model-ranked, explained anomalies.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("MIZAN_ALLOWED_ORIGINS", "*").split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generic_anomaly.router, prefix="/v1", tags=["anomaly"])
app.include_router(uploads.router, prefix="/v1", tags=["uploads"])


@app.get("/v1/health")
def health():
    return {"status": "ok", "product": "Mizan", "mode": "anomaly-detector-agent"}
