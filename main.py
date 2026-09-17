import os, logging, time, re, subprocess, asyncio, threading, json
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
JOBS_DB_FILE = Path("jobs_db.json")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

jobs_lock = threading.Lock()  # Thread-safe access to jobs dict

def load_jobs_from_disk():
    """Load jobs from persistent storage"""
    if JOBS_DB_FILE.exists():
        try:
            with open(JOBS_DB_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading jobs: {e}")
    return {}

def save_jobs_to_disk(jobs_data):
    """Save jobs to persistent storage"""
    try:
        with open(JOBS_DB_FILE, 'w') as f:
            json.dump(jobs_data, f)
    except Exception as e:
        logger.error(f"Error saving jobs: {e}")

# Load existing jobs from disk at startup
jobs = load_jobs_from_disk()
logger.info(f"Loaded {len(jobs)} jobs from disk")

VOICES = {
    "narrator": "Joanna",           # Female narrator - warm, engaging
    "male_1": "Matthew",            # Male voice - strong, authoritative
    "male_2": "Justin",             # Male voice - younger, friendly
    "female_1": "Ivy",              # Female voice - energetic, young
    "female_2": "Salli",            # Female voice - mature, professional
    "old_male": "Gary",             # Male voice - older, wise
    "child": "Kimberly"             # High-pitched for children
}

def detect_speaker(text: str, segment_index: int = 0) -> str:
    """Detect appropriate speaker voice based on text content and variation"""
    text_lower = text.lower()
    
    # Dialogue detection (quoted speech)
    if re.search(r'"[^"]{10,}"', text):
        # Character dialogue - alternate between male and female voices
        if re.search(r'(he said|asked|replied|exclaimed|shouted|whispered)', text_lower):
            return "male_1" if segment_index % 2 == 0 else "female_1"
        return "male_1"
    
    if re.search(r"'[^']{10,}'", text):
        return "female_1"
    
    # Question detection - use different voice for variety
    if text.strip().endswith('?'):
        return "female_2" if segment_index % 3 == 0 else "male_2"
    
    # Exclamation detection
    if text.strip().endswith('!'):
        return "male_2" if segment_index % 2 == 0 else "female_1"
    
    # Narrative text - rotate through narrator and other voices for variation
    # This prevents monotone reading by varying the voice every few segments
    voice_rotation = [
        "narrator",    # Primary narrator (Joanna - female)
        "male_2",      # Secondary narrator (Justin - male)
        "male_1",      # Tertiary (Matthew - male)
    ]
    return voice_rotation[segment_index % len(voice_rotation)]

def extract_segments(pdf_path: Path) -> list:
    segments = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            logger.info(f"📖 Opening PDF: {pdf_path}, Pages: {len(pdf.pages)}")
            segment_index = 0
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    page_segments = 0
                    for para in text.split('\n\n'):
                        if para.strip():
                            segments.append({"text": para.strip(), "speaker": detect_speaker(para, segment_index), "page": page_num + 1})
                            segment_index += 1
                            page_segments += 1
                    logger.info(f"Page {page_num + 1}: Extracted {page_segments} paragraphs")
            logger.info(f"✅ Total segments extracted: {len(segments)}")
    except Exception as e:
        logger.error(f"❌ PDF extraction error: {e}", exc_info=True)
        raise
    return segments

def run_process_pdf(jid: str, path: Path, use_multi_voice: bool = True):
    """Wrapper to run async process_pdf in background task"""
    print(f"🚀 BACKGROUND TASK STARTED for {jid}")
    print(f"File path: {path}, exists: {path.exists()}")
    logger.info(f"🚀 BACKGROUND TASK STARTED for {jid}")
    logger.info(f"File path: {path}, exists: {path.exists()}")
    
    try:
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")
            
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process_pdf(jid, path, use_multi_voice))
        finally:
            loop.close()
    except Exception as e:
        error_msg = f"Background task failed: {str(e)}"
        print(f"💥 CRITICAL ERROR in {jid}: {error_msg}")
        logger.error(f"💥 CRITICAL ERROR in background task {jid}: {e}", exc_info=True)
        with jobs_lock:
            jobs[jid]["status"] = "failed"
            jobs[jid]["error"] = error_msg
            jobs[jid]["progress"] = 0
            save_jobs_to_disk(jobs)

async def process_pdf(jid: str, path: Path, use_multi_voice: bool = True):
    try:
        logger.info(f"Starting {jid}")
        with jobs_lock:
            jobs[jid]["status"] = "processing"
            jobs[jid]["progress"] = 5
            save_jobs_to_disk(jobs)
        logger.info(f"Job {jid}: Progress 5% - Starting extraction")
        
        segments = extract_segments(path)
        if not segments:
            raise ValueError("No text found")
        
        logger.info(f"Found {len(segments)} segments")
        with jobs_lock:
            jobs[jid]["progress"] = 20
            save_jobs_to_disk(jobs)
        logger.info(f"Job {jid}: Progress 20% - Extraction complete")
        
        audio_files = []
        if polly:
            logger.info(f"🎤 AWS Polly available - synthesizing {len(segments)} segments")
            for idx, seg in enumerate(segments):
                try:
                    voice = VOICES.get(seg["speaker"], VOICES["narrator"]) if use_multi_voice else VOICES["narrator"]
                    text = seg["text"]
                    
                    # AWS Polly limit is 3000 characters, use 2900 to be safe
                    if len(text) > 2900:
                        logger.warning(f"Segment {idx} too long ({len(text)} chars), truncating to 2900")
                        text = text[:2900]
                    
                    ssml = f'<speak>{text}</speak>'
                    response = polly.synthesize_speech(Text=ssml, TextType="ssml", OutputFormat="mp3", VoiceId=voice, Engine="neural")
                    audio_path = OUTPUT_DIR / f"{jid}_seg_{idx}.mp3"
                    audio_path.write_bytes(response["AudioStream"].read())
                    audio_files.append(audio_path)
                    
                    # Calculate progress (20-85%)
                    progress = 20 + int((idx / len(segments)) * 65)
                    with jobs_lock:
                        jobs[jid]["progress"] = progress
                        save_jobs_to_disk(jobs)
                    logger.info(f"Job {jid}: Progress {progress}% - Synthesized segment {idx + 1}/{len(segments)} ({len(text)} chars)")
                    
                    # Small delay to allow frontend to poll
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"❌ Segment {idx} error: {e}")
                    continue
            
            with jobs_lock:
                jobs[jid]["progress"] = 85
                save_jobs_to_disk(jobs)
            logger.info(f"Job {jid}: Progress 85% - All segments synthesized")
            
            if audio_files:
                try:
                    concat_file = OUTPUT_DIR / f"{jid}_concat.txt"
                    with open(concat_file, "w") as f:
                        for af in audio_files:
                            f.write(f"file '{af}'\n")
                    
                    with jobs_lock:
                        jobs[jid]["progress"] = 90
                        save_jobs_to_disk(jobs)
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
        
        with jobs_lock:
            jobs[jid]["status"] = "completed"
            jobs[jid]["progress"] = 100
            save_jobs_to_disk(jobs)
        logger.info(f"Job {jid}: Progress 100% - Completed")
    except Exception as e:
        logger.error(f"Error: {e}")
        with jobs_lock:
            jobs[jid]["status"] = "failed"
            jobs[jid]["error"] = str(e)
            save_jobs_to_disk(jobs)

def get_html_ui():
    return ""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv('PORT', 8000)))
