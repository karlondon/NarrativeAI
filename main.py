import os, logging, time, re, subprocess
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
from dotenv import load_dotenv
import pdfplumber

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="NarrativeAI", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

try:
    polly = boto3.client('polly', region_name=os.getenv('AWS_REGION', 'us-east-1'))
except Exception as e:
    logger.warning(f"AWS Polly not available: {e}")
    polly = None

UPLOAD_DIR, OUTPUT_DIR = Path("uploads"), Path("output")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
jobs = {}

# MULTI-VOICE SUPPORT: Different voices for characters and narration
VOICES = {
    "narrator": "Joanna",      # Female narrator
    "male_1": "Matthew",       # Male character 1
    "male_2": "Justin",        # Male character 2
    "female_1": "Ivy",         # Female character 1
    "female_2": "Salli",       # Female character 2
    "old_male": "Gary",        # Older male character
    "child": "Kimberly"        # Child character
}

class Health(BaseModel):
    status: str
    version: str
    aws_ok: bool

@app.get("/health", response_model=Health)
async def health():
    return Health(status="healthy", version="0.2.0", aws_ok=bool(os.getenv('AWS_ACCESS_KEY_ID')))

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve beautiful web UI for uploads and downloads"""
    return get_html_interface()

@app.post("/upload")
async def upload(file: UploadFile = File(...), multi_voice: bool = True, bg: BackgroundTasks = None):
    """Upload PDF and start multi-voice conversion"""
    if not file.filename.endswith('.pdf'):
        raise HTTPException(400, "Only PDF files are supported")
    content = await file.read()
    if len(content) > 50*1024*1024:
        raise HTTPException(413, "File too large (max 50MB)")
    jid = f"job_{int(time.time())}_{file.filename.replace('.pdf','')}"
    (UPLOAD_DIR / f"{jid}.pdf").write_bytes(content)
    jobs[jid] = {"id": jid, "status": "pending", "file": file.filename, "progress": 0, "multi_voice": multi_voice}
    if bg:
        bg.add_task(process_pdf, jid, UPLOAD_DIR / f"{jid}.pdf", multi_voice)
    return {"job_id": jid, "status": "pending"}

@app.get("/jobs/{jid}")
async def status(jid: str):
    return jobs.get(jid, {"error": "not found"})

@app.get("/jobs/{jid}/download")
async def download(jid: str):
    if jid not in jobs or jobs[jid]['status'] != 'completed':
        raise HTTPException(400, "not ready")
    f = OUTPUT_DIR / f"{jid}.mp3"
    return FileResponse(f, filename=f"{jobs[jid]['file'].replace('.pdf','')}.mp3", media_type="audio/mpeg") if f.exists() else None

async def process(jid, path):
    try:
        jobs[jid]['status'] = 'processing'
        import pdfplumber
        text = ""
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                t = p.extract_text()
                if t: text += t + "\n"
        if polly:
            r = polly.synthesize_speech(Text=text[:3000], OutputFormat='mp3', VoiceId='Joanna')
            (OUTPUT_DIR / f"{jid}.mp3").write_bytes(r['AudioStream'].read())
        jobs[jid]['status'] = 'completed'
        jobs[jid]['progress'] = 100
    except Exception as e:
        jobs[jid]['status'] = 'failed'
        jobs[jid]['error'] = str(e)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv('PORT', 8000)))
