import io
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
import soundfile as sf
from runtime import ROOT, Recognizer

app = FastAPI(title="SLOAN STT")
model = Recognizer(top_k=3)

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((ROOT / "web" / "index.html").read_text(encoding="utf-8"))

@app.post("/api/classify")
async def classify(audio: UploadFile = File(...), min_confidence: float=.55,
                   min_margin: float=.05, head: str="sloan"):
    samples, rate = sf.read(io.BytesIO(await audio.read()), dtype="float32", always_2d=False)
    try:
        return model.predict(samples, rate, min_confidence, min_margin, head=head)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
