import os, logging, time, re, subprocess, asyncio
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

VOICES = {"narrator": "Joanna", "male_1": "Matthew", "male_2": "Justin",
    "female_1": "Ivy", "female_2": "Salli", "old_male": "Gary", "child": "Kimberly"}

class Health(BaseModel):
    status: str
    version: str
    aws_ok: bool

@app.get("/health", response_model=Health)
async def health():
    return Health(status="healthy", version="0.2.0", aws_ok=bool(os.getenv('AWS_ACCESS_KEY_ID')))

@app.get("/", response_class=HTMLResponse)
async def root():
    ui_path = Path(__file__).parent / "ui.html"
    return ui_path.read_text() if ui_path.exists() else get_html_ui()

@app.post("/upload")
async def upload(bg: BackgroundTasks, file: UploadFile = File(...), multi_voice: bool = True):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(400, "Only PDF files are supported")
    content = await file.read()
    if len(content) > 50*1024*1024:
        raise HTTPException(413, "File too large")
    jid = f"job_{int(time.time())}_{file.filename.replace('.pdf','')}"
    (UPLOAD_DIR / f"{jid}.pdf").write_bytes(content)
    jobs[jid] = {"id": jid, "status": "pending", "file": file.filename, "progress": 0}
    bg.add_task(run_process_pdf, jid, UPLOAD_DIR / f"{jid}.pdf", multi_voice)
    logger.info(f"Job {jid} queued")
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

def detect_speaker(text: str) -> str:
    if re.search(r'"[^"]{10,}"', text):
        return "male_1"
    if re.search(r"'[^']{10,}'", text):
        return "female_1"
    return "narrator"

def extract_segments(pdf_path: Path) -> list:
    segments = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    for para in text.split('\n\n'):
                        if para.strip():
                            segments.append({"text": para.strip(), "speaker": detect_speaker(para), "page": page_num + 1})
    except Exception as e:
        logger.error(f"Error: {e}")
        raise
    return segments

def run_process_pdf(jid: str, path: Path, use_multi_voice: bool = True):
    """Wrapper to run async process_pdf in background task"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_pdf(jid, path, use_multi_voice))
    finally:
        loop.close()

async def process_pdf(jid: str, path: Path, use_multi_voice: bool = True):
    try:
        logger.info(f"Starting {jid}")
        jobs[jid]["status"] = "processing"
        jobs[jid]["progress"] = 5
        logger.info(f"Job {jid}: Progress 5% - Starting extraction")
        
        segments = extract_segments(path)
        if not segments:
            raise ValueError("No text found")
        
        logger.info(f"Found {len(segments)} segments")
        jobs[jid]["progress"] = 20
        logger.info(f"Job {jid}: Progress 20% - Extraction complete")
        
        audio_files = []
        if polly:
            for idx, seg in enumerate(segments):
                try:
                    voice = VOICES.get(seg["speaker"], VOICES["narrator"]) if use_multi_voice else VOICES["narrator"]
                    text = seg["text"][:500]
                    ssml = f'<speak>{text}</speak>'
                    response = polly.synthesize_speech(Text=ssml, TextType="ssml", OutputFormat="mp3", VoiceId=voice, Engine="neural")
                    audio_path = OUTPUT_DIR / f"{jid}_seg_{idx}.mp3"
                    audio_path.write_bytes(response["AudioStream"].read())
                    audio_files.append(audio_path)
                    
                    # Calculate progress (20-85%)
                    progress = 20 + int((idx / len(segments)) * 65)
                    jobs[jid]["progress"] = progress
                    logger.info(f"Job {jid}: Progress {progress}% - Synthesized segment {idx + 1}/{len(segments)}")
                    
                    # Small delay to allow frontend to poll
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Segment error: {e}")
                    continue
            
            jobs[jid]["progress"] = 85
            logger.info(f"Job {jid}: Progress 85% - All segments synthesized")
            
            if audio_files:
                try:
                    concat_file = OUTPUT_DIR / f"{jid}_concat.txt"
                    with open(concat_file, "w") as f:
                        for af in audio_files:
                            f.write(f"file '{af}'\n")
                    
                    jobs[jid]["progress"] = 90
                    logger.info(f"Job {jid}: Progress 90% - Concatenating audio")
                    
                    output_path = OUTPUT_DIR / f"{jid}.mp3"
                    subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output_path), "-y"], capture_output=True, timeout=300, check=True)
                    concat_file.unlink(missing_ok=True)
                    for af in audio_files:
                        af.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"ffmpeg error: {e}")
                    if audio_files:
                        audio_files[0].rename(OUTPUT_DIR / f"{jid}.mp3")
                        for af in audio_files[1:]:
                            af.unlink(missing_ok=True)
        
        jobs[jid]["status"] = "completed"
        jobs[jid]["progress"] = 100
        logger.info(f"Job {jid}: Progress 100% - Completed")
    except Exception as e:
        logger.error(f"Error: {e}")
        jobs[jid]["status"] = "failed"
        jobs[jid]["error"] = str(e)

def get_html_ui():
    return ""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv('PORT', 8000)))
