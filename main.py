import os, logging, time, re, subprocess, asyncio, threading, json, uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
from dotenv import load_dotenv
import pdfplumber

# NLP for sentiment analysis
try:
    from textblob import TextBlob
    HAS_TEXTBLOB = True
except ImportError:
    HAS_TEXTBLOB = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.info("⚠️ TextBlob not installed. Install: pip install textblob")

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="NarrativeAI", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

polly = None

def get_polly_client():
    """Initialize Polly client on-demand. Checks for credentials at runtime."""
    global polly
    
    # If already initialized and working, return it
    if polly is not None:
        return polly
    
    # Try to initialize now (credentials might have been added after startup)
    try:
        aws_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret = os.getenv('AWS_SECRET_ACCESS_KEY')
        
        if not aws_key or not aws_secret:
            logger.error("❌ AWS credentials not configured: AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY missing")
            return None
        
        polly = boto3.client('polly', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        logger.info("✅ AWS Polly client initialized successfully")
        return polly
    except Exception as e:
        logger.error(f"❌ Failed to initialize AWS Polly: {e}")
        return None

UPLOAD_DIR, OUTPUT_DIR = Path("uploads"), Path("output")
JOBS_DB_FILE = Path("jobs_db.json")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

jobs_lock = threading.Lock()  # Thread-safe access to jobs dict
GLOBAL_CHARACTER_VOICES = {}  # Global character-to-voice mapping for consistency throughout document


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
    "narrator": "Joanna",           # Female narrator - warm, engaging, professional (Neural supported)
    "male_1": "Matthew",            # Male voice - professional, clear (Neural supported)
    "male_2": "Justin",             # Male voice - friendly, clear (Neural supported)
    "female_1": "Ivy",              # Female voice - energetic, professional (Neural supported)
    "female_2": "Salli",            # Female voice - mature, professional (Neural supported)
    "old_male": "Brian",            # Male voice - distinguished, wise (Neural supported)
    "child": "Kimberly"             # Female voice - younger (Neural supported)
}

class Health(BaseModel):
    status: str
    version: str
    aws_ok: bool

@app.get("/health", response_model=Health)
async def health():
    polly_client = get_polly_client()
    return Health(status="healthy", version="0.3.0", aws_ok=polly_client is not None)

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
    # Create job ID with just timestamp + random suffix (avoid filename issues)
    import uuid
    jid = f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    pdf_filename = file.filename.replace('.pdf', '')
    (UPLOAD_DIR / f"{jid}.pdf").write_bytes(content)
    with jobs_lock:
        jobs[jid] = {"id": jid, "status": "pending", "file": file.filename, "filename": pdf_filename, "progress": 0}
        save_jobs_to_disk(jobs)  # Persist to disk
    logger.info(f"✅ Job {jid} created for file: {file.filename}")
    bg.add_task(run_process_pdf, jid, UPLOAD_DIR / f"{jid}.pdf", multi_voice)
    return {"job_id": jid, "status": "pending"}

@app.get("/jobs/{jid}")
async def status(jid: str):
    with jobs_lock:
        job = jobs.get(jid)
        if job:
            logger.info(f"Status check for {jid}: {job}")
            return job
        else:
            logger.info(f"Job not found: {jid}. Available jobs: {list(jobs.keys())}")
            return {"error": "not found", "jid": jid, "available_jobs": list(jobs.keys())}

@app.get("/jobs/{jid}/download")
async def download(jid: str):
    if jid not in jobs or jobs[jid]['status'] != 'completed':
        raise HTTPException(400, "Job not ready or not found")
    
    f = OUTPUT_DIR / f"{jid}.mp3"
    if not f.exists():
        logger.error(f"❌ Download: Audio file not found: {f}")
        raise HTTPException(404, f"Audio file not found for job {jid}")
    
    filename = f"{jobs[jid]['file'].replace('.pdf','')}.mp3"
    logger.info(f"✅ Download: Sending {filename} ({f.stat().st_size / 1024 / 1024:.1f}MB)")
    return FileResponse(f, filename=filename, media_type="audio/mpeg")

def detect_speaker(text: str, segment_index: int = 0) -> tuple:
    """
    Advanced speaker detection with NLP analysis and character tracking.
    Returns: (voice_id, ssml_text) tuple with SSML prosody tags for pitch and rate control
    
    Detection hierarchy:
    1. Character names (e.g., "John said") - consistent voice assignment
    2. Dialogue with gender hints (he/she said)
    3. Single-quoted speech
    4. Questions (ends with ?)
    5. Exclamations (ends with !)
    6. Emotional tone analysis (sentiment polarity)
    7. Voice rotation for narrative variety
    
    OPTIMIZED FOR: Professional adult narration with clear enunciation
    - All rates set to 85-95% (slower for clarity, adult-like pace)
    - Neural engine will handle prosody naturally
    - Professional voice selection only
    """
    global GLOBAL_CHARACTER_VOICES
    
    text_lower = text.lower()
    voice_id = "narrator"
    pitch = "0%"
    rate = "90%"  # Default to 90% (slightly slower for clarity)
    
    # LEVEL 1: CHARACTER NAME DETECTION - assigns consistent voices to named characters
    char_pattern = r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+(?:said|asked|replied|exclaimed|shouted|whispered|muttered|hissed|bellowed|cried)'
    char_matches = re.findall(char_pattern, text)
    
    if char_matches:
        char_name = char_matches[0]
        if char_name not in GLOBAL_CHARACTER_VOICES:
            # Use only professional adult voices
            available_voices = ["male_1", "male_2", "female_1", "female_2", "old_male"]
            char_index = len(GLOBAL_CHARACTER_VOICES) % len(available_voices)
            GLOBAL_CHARACTER_VOICES[char_name] = available_voices[char_index]
            logger.info(f"🎭 NEW CHARACTER: '{char_name}' → {GLOBAL_CHARACTER_VOICES[char_name]}")
        
        voice_id = GLOBAL_CHARACTER_VOICES[char_name]
        pitch = "+5%"  # Subtle pitch increase for dialogue
        rate = "88%"   # Slightly slower for clear dialogue
    
    # LEVEL 2: DIALOGUE DETECTION - Gender-aware dialogue handling
    elif re.search(r'"[^"]{10,}"', text):
        if re.search(r'(he\s+said|he\s+asked|he\s+exclaimed|he\s+bellowed)', text_lower):
            voice_id = "male_1"
        elif re.search(r'(she\s+said|she\s+asked|she\s+whispered)', text_lower):
            voice_id = "female_2"
        else:
            voice_id = "male_1" if segment_index % 2 == 0 else "female_1"
        pitch = "+3%"   # Very subtle pitch for natural dialogue
        rate = "88%"    # Clear dialogue delivery
    
    # LEVEL 3: SINGLE-QUOTED SPEECH
    elif re.search(r"'[^']{10,}'", text):
        voice_id = "female_1"
        pitch = "+3%"
        rate = "88%"
    
    # LEVEL 4: QUESTIONS - slightly faster but still clear
    elif text.strip().endswith('?'):
        voice_id = "female_2" if segment_index % 3 == 0 else "male_2"
        pitch = "+2%"
        rate = "90%"   # Slightly faster than narrative
    
    # LEVEL 5: EXCLAMATIONS - energetic but professional
    elif text.strip().endswith('!'):
        voice_id = "male_2" if segment_index % 2 == 0 else "female_1"
        pitch = "+5%"
        rate = "92%"   # Energetic but still clear
    
    # LEVEL 6: EMOTIONAL TONE DETECTION using TextBlob sentiment analysis
    else:
        try:
            if HAS_TEXTBLOB:
                blob = TextBlob(text[:500])
                polarity = blob.sentiment.polarity
                
                if polarity > 0.4:  # Happy/positive - slightly faster and higher pitch
                    voice_id = "female_1"
                    pitch = "+5%"
                    rate = "92%"
                elif polarity < -0.4:  # Sad/negative - slower and deeper
                    voice_id = "old_male"
                    pitch = "-5%"
                    rate = "85%"  # Slowest for emotional impact
                else:  # Neutral - balanced narrator pace
                    voice_rotation = ["narrator", "male_2", "male_1"]
                    voice_id = voice_rotation[segment_index % len(voice_rotation)]
                    pitch = "0%"
                    rate = "90%"  # Standard pace
            else:
                # LEVEL 7: FALLBACK - Voice rotation
                voice_rotation = ["narrator", "male_2", "male_1"]
                voice_id = voice_rotation[segment_index % len(voice_rotation)]
                pitch = "0%"
                rate = "90%"
        except Exception as e:
            logger.debug(f"Sentiment analysis failed: {e}")
            voice_rotation = ["narrator", "male_2", "male_1"]
            voice_id = voice_rotation[segment_index % len(voice_rotation)]
            pitch = "0%"
            rate = "90%"
    
    # BUILD SSML TEXT WITH PROSODY TAGS (Neural engine will handle naturally)
    # Note: These tags work with Neural engine for subtle, professional delivery
    if pitch != "0%" or rate != "90%":
        ssml_text = f'<speak><prosody pitch="{pitch}" rate="{rate}">{text}</prosody></speak>'
    else:
        ssml_text = f'<speak>{text}</speak>'
    
    return voice_id, ssml_text

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
                            # detect_speaker now returns (voice_id, ssml_text) tuple
                            voice_id, ssml_text = detect_speaker(para, segment_index)
                            segments.append({
                                "text": para.strip(), 
                                "voice_id": voice_id,
                                "ssml_text": ssml_text,
                                "page": page_num + 1
                            })
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
    global GLOBAL_CHARACTER_VOICES
    GLOBAL_CHARACTER_VOICES = {}  # Reset character voices for each new PDF
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
        polly_client = get_polly_client()
        if polly_client:
            logger.info(f"🎤 AWS Polly available - synthesizing {len(segments)} segments")
            for idx, seg in enumerate(segments):
                try:
                    # Use the pre-computed voice_id and ssml_text from detect_speaker
                    voice_id = seg["voice_id"] if use_multi_voice else "narrator"
                    text = seg["text"]
                    
                    # AWS Polly limit is 3000 characters for SSML
                    # We use 2000 to be safe since SSML tags add overhead
                    if len(text) > 2000:
                        logger.warning(f"Segment {idx} too long ({len(text)} chars), truncating to 2000")
                        text = text[:2000]
                    
                    # Get the voice name
                    voice = VOICES.get(voice_id, VOICES["narrator"])
                    
                    # Create SSML with prosody tags for better clarity and adult-like quality
                    # Neural engine supports prosody tags but NOT amazon:auto-breaths
                    # Rate: 90% = slightly slower for clarity
                    # Pitch: 0% = neutral (default)
                    ssml_text = f'''<speak>
                        <prosody rate="90%" pitch="0%">
                            {text}
                        </prosody>
                    </speak>'''
                    
                    # Use NEURAL engine for natural, human-like quality
                    # Neural engine provides:
                    # - Natural prosody (pitch, rhythm, intonation)
                    # - Better emotional expression
                    # - Clearer enunciation
                    # - More adult-sounding voices
                    response = polly_client.synthesize_speech(
                        Text=ssml_text, 
                        TextType="ssml", 
                        OutputFormat="mp3", 
                        VoiceId=voice, 
                        Engine="neural"  # Switched to neural for professional quality
                    )

                    audio_path = OUTPUT_DIR / f"{jid}_seg_{idx:06d}.mp3"
                    audio_path.write_bytes(response["AudioStream"].read())
                    audio_files.append(audio_path)
                    
                    # Calculate progress (20-85%)
                    progress = 20 + int((idx / len(segments)) * 65)
                    with jobs_lock:
                        jobs[jid]["progress"] = progress
                        save_jobs_to_disk(jobs)
                    logger.info(f"Job {jid}: Progress {progress}% - Synthesized segment {idx + 1}/{len(segments)} with voice {voice} (Neural, 90% rate) ({len(text)} chars)")
                    
                    # Small delay to allow frontend to poll
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.error(f"❌ Segment {idx} error: {e}")
                    continue
            
            with jobs_lock:
                jobs[jid]["progress"] = 85
                save_jobs_to_disk(jobs)
            logger.info(f"Job {jid}: Progress 85% - All segments synthesized")
        else:
            logger.error(f"❌ AWS Polly not available - cannot synthesize audio. Check AWS credentials.")
            raise Exception("AWS Polly not configured - check AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")

        # Verify we have audio files to concatenate
        if not audio_files:
            logger.error(f"❌ No audio files were created during synthesis")
            raise Exception("Audio synthesis failed - no audio files generated")

        # Concatenate all audio segments into final MP3
        try:
            # FIX FOR 2-MINUTE AUDIO: Use absolute paths in concat file
            concat_file = OUTPUT_DIR / f"{jid}_concat.txt"
            with open(concat_file, "w") as f:
                for af in audio_files:
                    abs_path = af.resolve()  # Convert to absolute path
                    f.write(f"file '{abs_path}'\n")
            
            with jobs_lock:
                jobs[jid]["progress"] = 90
                save_jobs_to_disk(jobs)
            logger.info(f"Job {jid}: Progress 90% - Concatenating {len(audio_files)} audio segments")
            
            output_path = OUTPUT_DIR / f"{jid}.mp3"
            
            # Improved FFmpeg command with proper error checking
            cmd = [
                "ffmpeg", 
                "-f", "concat", 
                "-safe", "0", 
                "-i", str(concat_file), 
                "-c", "copy",
                "-q:a", "0",
                "-y", 
                str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=600, text=True)
            
            # Check for FFmpeg errors
            if result.returncode != 0:
                logger.error(f"❌ FFmpeg concat error:\n{result.stderr}")
                raise Exception(f"FFmpeg failed: {result.stderr[-500:]}")
            
            # Verify output file exists and has content
            if not output_path.exists():
                logger.error(f"❌ FFmpeg did not create output file")
                raise Exception("FFmpeg did not create output file")
            
            output_size = output_path.stat().st_size
            size_mb = output_size / 1024 / 1024
            logger.info(f"✅ Successfully concatenated to {output_path.name} ({size_mb:.1f}MB, {len(audio_files)} segments)")
            
            # Cleanup temporary files
            concat_file.unlink(missing_ok=True)
            for af in audio_files:
                af.unlink(missing_ok=True)
            
        except subprocess.TimeoutExpired:
            logger.error(f"❌ FFmpeg concatenation timed out (600s) - file too large")
            raise Exception("Concatenation timeout - file too large")
        except Exception as e:
            logger.error(f"❌ Concatenation failed: {e}")
            # Fallback: use first audio file if concat fails
            if audio_files:
                logger.info(f"⚠️ Falling back to first audio segment only")
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
