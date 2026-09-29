"""Dadi web server.

Run:  uv run uvicorn dadi.app:app --reload   then open http://localhost:8000
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from dadi import network, report  # noqa: E402
from dadi.detector import DEFAULT_PATH, Detector  # noqa: E402
from dadi.persona import Persona  # noqa: E402
from dadi.session import CallSession, CallStore  # noqa: E402
from dadi.tactics import TacticBandit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DATA = ROOT / "data" / "runtime"

if not DEFAULT_PATH.exists():
    raise SystemExit("No trained detector found. Run: uv run python -m dadi.train")

detector = Detector.load(DEFAULT_PATH)
detector.predict("warmup")  # load the sentence encoder before the first call
bandit = TacticBandit(DATA / "bandit.json")
persona = Persona()
store = CallStore(DATA / "calls.jsonl")

app = FastAPI(title="Dadi")
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/status")
def status() -> dict:
    records = store.all()
    return {
        "persona_mode": persona.mode,
        "calls": len(records),
        "wasted_s": sum(r.get("wasted_s", 0) for r in records),
        "identifiers": len({v for r in records for k in ("upi_ids", "phones", "accounts", "ifsc")
                            for v in r["intel"].get(k, [])}),
        "bandit": bandit.stats(),
    }


@app.get("/api/metrics")
def metrics() -> dict:
    path = DEFAULT_PATH.parent / "metrics.json"
    return json.loads(path.read_text()) if path.exists() else {}


@app.get("/api/graph")
def graph() -> dict:
    return network.to_json(network.build(store.all()))


@app.get("/api/report/{call_id}", response_class=PlainTextResponse)
def call_report(call_id: str) -> str:
    record = store.get(call_id)
    if not record:
        raise HTTPException(404, "call not found")
    ring = network.ring_of(network.build(store.all()), call_id)
    return report.draft(record, ring)


@app.websocket("/ws/call")
async def call(ws: WebSocket) -> None:
    await ws.accept()
    session: CallSession | None = None
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "start":
                session = CallSession(detector, bandit, persona, store)
                await ws.send_json({"type": "started", **session.snapshot(), "persona_mode": persona.mode})
            elif kind == "caller" and session and session.state != "ended" and msg.get("text", "").strip():
                await ws.send_json(await session.on_caller(msg["text"]))
            elif kind == "tick" and session:
                await ws.send_json({"type": "tick", "wasted_s": session.wasted_s})
            elif kind == "end" and session:
                record = session.end()
                await ws.send_json({"type": "ended", "call_id": session.id, "saved": record is not None,
                                    "wasted_s": record["wasted_s"] if record else 0})
                session = None
    except WebSocketDisconnect:
        if session:
            session.end()
