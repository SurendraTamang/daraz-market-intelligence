#!/usr/bin/env python3
"""Live data endpoint for the React dashboard.

    uvicorn api:app --reload        # http://localhost:8000/api/data

Point the frontend at it with VITE_API_URL (see frontend/README). Serves the same
payload as export_json.py, computed fresh from data.db on each request.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analyze import build_payload

app = FastAPI(title="Daraz Market API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ponytail: open CORS for a read-only public dashboard; lock down if it ever serves private data
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/data")
def data():
    return build_payload()  # honours DARAZ_DB
