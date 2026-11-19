#!/usr/bin/env python3
"""Simple Jetson mic test: live level meter + record WAV from a chosen input.

  python scripts/mic_web_test.py --device 0 --port 8091

Open http://<jetson-ip>:8091/  (works from Mac browser — records on Jetson).
"""

from __future__ import annotations

import argparse
import io
import json
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import sounddevice as sd

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Jetson mic test</title>
  <style>
    :root { color-scheme: light; font-family: ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; min-height: 100vh; background: #0f1419; color: #e8eef5; }
    main { max-width: 720px; margin: 0 auto; padding: 28px 20px 48px; }
    h1 { font-size: 1.5rem; margin: 0 0 8px; }
    p { color: #9db0c5; line-height: 1.45; }
    .card { background: #1a2330; border: 1px solid #2a3a4d; border-radius: 14px; padding: 18px; margin-top: 16px; }
    .meter { height: 22px; background: #0b1016; border-radius: 999px; overflow: hidden; }
    .meter > span { display:block; height:100%; width:0%; background: linear-gradient(90deg,#3dd68c,#f5c542,#ff6b6b); transition: width .08s linear; }
    .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-top:14px; }
    button, select { font: inherit; padding: 10px 14px; border-radius: 10px; border: 0; cursor: pointer; }
    button { background: #3b82f6; color: #fff; font-weight: 600; }
    button.ghost { background: #2a3a4d; color: #e8eef5; }
    button:disabled { opacity: .5; cursor: not-allowed; }
    code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .stats { display:grid; grid-template-columns: repeat(3,1fr); gap:10px; margin-top:12px; }
    .stat { background:#0b1016; border-radius:10px; padding:10px 12px; }
    .stat b { display:block; font-size:1.15rem; }
    .stat span { color:#9db0c5; font-size:.85rem; }
    audio { width: 100%; margin-top: 12px; }
    .ok { color:#3dd68c; } .warn { color:#f5c542; } .bad { color:#ff6b6b; }
  </style>
</head>
<body>
<main>
  <h1>Jetson mic test</h1>
  <p>Records on the Jetson (server-side), not your Mac mic. Speak toward the C270 while watching the meter.</p>

  <div class="card">
    <label>Input device<br/>
      <select id="device"></select>
    </label>
    <div class="meter" aria-label="level"><span id="bar"></span></div>
    <div class="stats">
      <div class="stat"><span>RMS</span><b id="rms">—</b></div>
      <div class="stat"><span>Peak</span><b id="peak">—</b></div>
      <div class="stat"><span>Status</span><b id="status" class="warn">…</b></div>
    </div>
    <div class="row">
      <button id="rec">Record 5s</button>
      <button class="ghost" id="refresh">Refresh devices</button>
      <span class="mono" id="info"></span>
    </div>
    <audio id="player" controls></audio>
  </div>
</main>
<script>
const $ = (id) => document.getElementById(id);
async function loadDevices() {
  const r = await fetch('/api/devices');
  const data = await r.json();
  const sel = $('device');
  sel.innerHTML = '';
  for (const d of data.devices) {
    const opt = document.createElement('option');
    opt.value = d.index;
    opt.textContent = `[${d.index}] ${d.name} (ch=${d.channels})`;
    if (d.index === data.default) opt.selected = true;
    sel.appendChild(opt);
  }
  $('info').textContent = `default=${data.default}`;
}
function verdict(peak) {
  if (peak < 0.01) return ['SILENT / too quiet', 'bad'];
  if (peak < 0.05) return ['quiet — speak closer or raise gain', 'warn'];
  if (peak < 0.4) return ['OK for STT', 'ok'];
  return ['hot / clipping risk', 'warn'];
}
async function poll() {
  const device = $('device').value || '0';
  try {
    const r = await fetch('/api/level?device=' + encodeURIComponent(device));
    const j = await r.json();
    const pct = Math.min(100, Math.round(j.peak * 220));
    $('bar').style.width = pct + '%';
    $('rms').textContent = j.rms.toFixed(4);
    $('peak').textContent = j.peak.toFixed(4);
    const [txt, cls] = verdict(j.peak);
    const el = $('status');
    el.textContent = txt;
    el.className = cls;
  } catch (e) {
    $('status').textContent = 'poll error';
    $('status').className = 'bad';
  }
}
$('rec').onclick = async () => {
  $('rec').disabled = true;
  $('status').textContent = 'recording…';
  $('status').className = 'warn';
  const device = $('device').value || '0';
  try {
    const r = await fetch('/api/record?device=' + encodeURIComponent(device) + '&seconds=5');
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    $('player').src = url;
    $('player').play();
    const peak = Number(r.headers.get('X-Peak') || '0');
    const rms = Number(r.headers.get('X-Rms') || '0');
    $('rms').textContent = rms.toFixed(4);
    $('peak').textContent = peak.toFixed(4);
    const [txt, cls] = verdict(peak);
    $('status').textContent = 'saved · ' + txt;
    $('status').className = cls;
  } catch (e) {
    $('status').textContent = String(e);
    $('status').className = 'bad';
  } finally {
    $('rec').disabled = false;
  }
};
$('refresh').onclick = loadDevices;
loadDevices().then(() => setInterval(poll, 250));
</script>
</body>
</html>
"""


class MicState:
    def __init__(self, default_device: int) -> None:
        self.default_device = default_device
        self._lock = threading.Lock()

    def list_inputs(self) -> list[dict]:
        out = []
        for i, d in enumerate(sd.query_devices()):
            ch = int(d.get("max_input_channels") or 0)
            if ch <= 0:
                continue
            out.append(
                {
                    "index": i,
                    "name": d["name"],
                    "channels": ch,
                    "samplerate": float(d.get("default_samplerate") or 48000),
                }
            )
        return out

    def measure(self, device: int, seconds: float = 0.2) -> tuple[float, float, int]:
        info = sd.query_devices(device)
        ch = max(1, min(1, int(info.get("max_input_channels") or 1)))
        sr = int(info.get("default_samplerate") or 48000)
        frames = max(1, int(sr * seconds))
        audio = sd.rec(frames, samplerate=sr, channels=ch, dtype="float32", device=device)
        sd.wait()
        y = np.asarray(audio, dtype=np.float32).reshape(-1)
        if y.size == 0:
            return 0.0, 0.0, sr
        rms = float(np.sqrt(np.mean(np.square(y))))
        peak = float(np.max(np.abs(y)))
        return rms, peak, sr

    def record_wav(self, device: int, seconds: float = 5.0) -> tuple[bytes, float, float]:
        info = sd.query_devices(device)
        ch = 1
        sr = int(info.get("default_samplerate") or 48000)
        frames = max(1, int(sr * seconds))
        audio = sd.rec(frames, samplerate=sr, channels=ch, dtype="float32", device=device)
        sd.wait()
        y = np.asarray(audio, dtype=np.float32).reshape(-1)
        rms = float(np.sqrt(np.mean(np.square(y)))) if y.size else 0.0
        peak = float(np.max(np.abs(y))) if y.size else 0.0
        pcm = np.clip(y, -1.0, 1.0)
        pcm_i16 = (pcm * 32767.0).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm_i16.tobytes())
        return buf.getvalue(), rms, peak


def make_handler(state: MicState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # quieter
            print(f"[mic-test] {self.address_string()} {fmt % args}")

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path in ("/", "/index.html"):
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/devices":
                self._json(
                    200,
                    {"default": state.default_device, "devices": state.list_inputs()},
                )
                return

            if path == "/api/level":
                device = int((qs.get("device") or [state.default_device])[0])
                with state._lock:
                    rms, peak, sr = state.measure(device, 0.15)
                self._json(200, {"device": device, "rms": rms, "peak": peak, "sr": sr})
                return

            if path == "/api/record":
                device = int((qs.get("device") or [state.default_device])[0])
                seconds = float((qs.get("seconds") or ["5"])[0])
                seconds = max(1.0, min(15.0, seconds))
                with state._lock:
                    wav, rms, peak = state.record_wav(device, seconds)
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav)))
                self.send_header("Content-Disposition", 'attachment; filename="mic_test.wav"')
                self.send_header("X-Rms", f"{rms:.6f}")
                self.send_header("X-Peak", f"{peak:.6f}")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(wav)
                return

            self.send_error(404)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Web mic level + record test")
    parser.add_argument("--device", type=int, default=0, help="sounddevice input index")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()

    state = MicState(default_device=args.device)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"Mic web test on http://0.0.0.0:{args.port}/  (device {args.device})")
    print("Open from Mac: http://192.168.1.125:{}/".format(args.port))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()
