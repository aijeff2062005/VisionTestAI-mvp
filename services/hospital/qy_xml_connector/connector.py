"""Poll a shared XML folder and forward each stable patient batch to QY Hospital.

This small agent is intended to run on an always-on PC that can read the HIS
share and reach the QY site. It stores only processed file keys locally.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path


LOG = logging.getLogger("qy_xml_connector")
API_METHOD = "/api/method/qy_vision_hospital.api.xml_intake.import_patient_xml"
MAX_XML_BYTES = 2 * 1024 * 1024


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def file_key(relative_name: str, modified_ns: int, contents: bytes) -> str:
    content_hash = hashlib.sha256(contents).hexdigest()
    raw = f"{relative_name}\0{modified_ns}\0{content_hash}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def post_xml(site_url: str, api_key: str, api_secret: str, file_name: str, source_key: str, xml_content: str) -> dict:
    body = json.dumps({"xml_content": xml_content, "source_file": file_name, "source_key": source_key}).encode("utf-8")
    request = urllib.request.Request(
        site_url.rstrip("/") + API_METHOD,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"token {api_key}:{api_secret}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    message = payload.get("message") or {}
    if not message.get("success"):
        raise RuntimeError("QY site did not confirm XML intake")
    return message


def run() -> None:
    inbox = Path(env("QY_XML_INBOX"))
    site_url = env("QY_SITE_URL")
    api_key = env("QY_API_KEY")
    api_secret = env("QY_API_SECRET")
    state_path = Path(env("QY_XML_STATE", str(Path.cwd() / "qy_xml_state.sqlite3")))
    poll_seconds = max(float(env("QY_XML_POLL_SECONDS", "30")), 1.0)
    stable_seconds = max(float(env("QY_XML_STABLE_SECONDS", "1")), 0.5)

    if not inbox.is_dir() or not site_url or not api_key or not api_secret:
        raise SystemExit("Set QY_XML_INBOX, QY_SITE_URL, QY_API_KEY, and QY_API_SECRET first.")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(state_path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS processed (source_key TEXT PRIMARY KEY, file_key TEXT NOT NULL, modified_ns INTEGER NOT NULL, size INTEGER NOT NULL, seen_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        db.commit()
        LOG.info("Watching configured XML inbox; polling every %.1fs", poll_seconds)
        while True:
            files = sorted((item for item in inbox.rglob("*") if item.is_file() and item.suffix.lower() == ".xml"), key=lambda item: (item.stat().st_mtime_ns, item.name))
            for path in files:
                try:
                    before = path.stat()
                    relative_name = str(path.relative_to(inbox))
                    relative_key = hashlib.sha256(relative_name.encode("utf-8")).hexdigest()
                    if db.execute(
                        "SELECT 1 FROM processed WHERE file_key=? AND modified_ns=? AND size=?",
                        (relative_key, before.st_mtime_ns, before.st_size),
                    ).fetchone():
                        continue
                    time.sleep(stable_seconds)
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        continue
                    if after.st_size <= 0 or after.st_size > MAX_XML_BYTES:
                        LOG.warning("Skipping XML with invalid size")
                        continue
                    raw = path.read_bytes()
                    key = file_key(relative_name, after.st_mtime_ns, raw)
                    if db.execute("SELECT 1 FROM processed WHERE source_key=?", (key,)).fetchone():
                        continue
                    result = post_xml(site_url, api_key, api_secret, f"xml-{key[:12]}.xml", key, raw.decode("utf-8-sig"))
                    db.execute(
                        "INSERT OR IGNORE INTO processed(source_key, file_key, modified_ns, size) VALUES (?, ?, ?, ?)",
                        (key, relative_key, after.st_mtime_ns, after.st_size),
                    )
                    db.commit()
                    LOG.info("XML accepted as request %s%s", result.get("request", ""), " (duplicate acknowledged)" if result.get("duplicate") else "")
                except FileNotFoundError:
                    # The HIS may rotate the inbox while it is being scanned.
                    continue
                except (UnicodeDecodeError, ValueError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                    # Keep the file unmarked so the next poll retries it.
                    LOG.error("XML delivery failed: %s", exc)
                except Exception:
                    LOG.exception("Unexpected XML connector error")
            time.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
