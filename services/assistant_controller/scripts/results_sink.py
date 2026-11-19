#!/usr/bin/env python3
"""Tiny HTTP sink to receive provisional AC result callbacks."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="QLBN Results Sink (demo)")
RECEIVED: list[dict] = []


@app.post("/api/v1/vision/results")
async def results(
    request: Request,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
) -> JSONResponse:
    body = await request.json()
    RECEIVED.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "correlation_id": x_correlation_id,
            "body": body,
        }
    )
    print(json.dumps(RECEIVED[-1], indent=2, ensure_ascii=False, default=str))
    return JSONResponse({"ok": True})


@app.get("/api/v1/vision/results")
async def list_results() -> JSONResponse:
    return JSONResponse({"count": len(RECEIVED), "items": RECEIVED})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8099, log_level="info")
