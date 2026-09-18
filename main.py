import os, logging, time, re, subprocess, asyncio, threading, json, uuid, hashlib
from d_id_client import get_did_client
from pricing_config import is_valid_tier, get_tier_info
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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

app = FastAPI(title="NarrativeAI", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ===== FREEMIUM CONFIG =====
FREE_CONVERSIONS_PER_DAY = 5
DOWNLOAD_PRICE_GBP = 1.0
SESSION_DB_FILE = Path("sessions_db.json")
GOOGLE_ANALYTICS_ID = "G-XXXXXXXXXX"  # Replace with your GA ID

# ===== SQUARE PAYMENT CONFIG =====
SQUARE_ACCESS_TOKEN = os.getenv('SQUARE_ACCESS_TOKEN')
SQUARE_APPLICATION_ID = os.getenv('SQUARE_APPLICATION_ID')
SQUARE_LOCATION_ID = os.getenv('SQUARE_LOCATION_ID')
SQUARE_ENVIRONMENT = os.getenv('SQUARE_ENVIRONMENT', 'production')
SQUARE_AVAILABLE = bool(os.getenv('SQUARE_ACCESS_TOKEN') and os.getenv('SQUARE_APPLICATION_ID'))

# D-ID Video Generation
D_ID_CLIENT = get_did_client()
D_ID_AVAILABLE = D_ID_CLIENT is not None
if D_ID_AVAILABLE:
    logger.info("✅ D-ID video generation enabled")


def get_square_client():
    """Initialize Square client for payments"""
    if not SQUARE_AVAILABLE or not SQUARE_ACCESS_TOKEN:
        return None
    try:
        client = Client(
            access_token=SQUARE_ACCESS_TOKEN,
            environment=SQUARE_ENVIRONMENT
        )
        logger.info("✅ Square client initialized")
        return client
    except Exception as e:
        logger.error(f"❌ Square initialization error: {e}")
        return None


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

# ===== FREEMIUM SESSION TRACKING =====
sessions_lock = threading.Lock()

def load_sessions_from_disk():
    """Load session data from persistent storage"""
    if SESSION_DB_FILE.exists():
        try:
            with open(SESSION_DB_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_sessions_to_disk(sessions_data):
    """Save sessions to persistent storage"""
    try:
        with open(SESSION_DB_FILE, 'w') as f:
            json.dump(sessions_data, f)
    except Exception as e:
        logger.error(f"Error saving sessions: {e}")

sessions = load_sessions_from_disk()
logger.info(f"✅ Loaded {len(sessions)} session records")

def get_client_id(request: Request) -> str:
    """Create unique ID from user's IP + User Agent"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    raw = f"{client_ip}:{user_agent}"
    return hashlib.md5(raw.encode()).hexdigest()

def get_today() -> str:
    """Get today's date (resets daily at midnight UTC)"""
    return time.strftime("%Y-%m-%d", time.gmtime())

def check_free_tier(user_id: str) -> tuple:
    """Check if user has free conversions left. Returns (is_free, used, remaining)"""
    today = get_today()
    key = f"{user_id}:{today}"
    
    with sessions_lock:
        used = sessions.get(key, 0)
        remaining = max(0, FREE_CONVERSIONS_PER_DAY - used)
        return remaining > 0, used, remaining

def count_conversion(user_id: str):
    """Increment user's daily conversion count"""
    today = get_today()
    key = f"{user_id}:{today}"
    
    with sessions_lock:
        sessions[key] = sessions.get(key, 0) + 1
        save_sessions_to_disk(sessions)
        logger.info(f"✅ Conversion tracked for {user_id[:8]}... (total: {sessions[key]}/{FREE_CONVERSIONS_PER_DAY})")


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


# ===== FREEMIUM API ENDPOINTS =====
@app.get("/api/free-tier")
async def free_tier_status(request: Request):
    """Check user's free tier status"""
    user_id = get_client_id(request)
    is_free, used, remaining = check_free_tier(user_id)
    return {
        "is_free_tier": is_free,
        "used": used,
        "remaining": remaining,
        "limit": FREE_CONVERSIONS_PER_DAY
    }

@app.get("/api/square-config")
async def square_config():
    """Get Square Web Payments SDK configuration"""
    return {
        "applicationId": SQUARE_APPLICATION_ID,
        "locationId": SQUARE_LOCATION_ID,
        "priceGBP": DOWNLOAD_PRICE_GBP,
        "environment": SQUARE_ENVIRONMENT,
        "squareAvailable": SQUARE_AVAILABLE
    }

@app.post("/api/square-payment")
async def create_square_payment(request: Request):
    """Process payment using Square"""
    try:
        user_id = get_client_id(request)
        body = await request.json()
        source_id = body.get("sourceId")
        job_id = body.get("jobId")
        
        if not source_id or not job_id:
            raise HTTPException(400, "Missing sourceId or jobId")
        
        client = get_square_client()
        if not client:
            raise HTTPException(503, "Payment service unavailable")
        
        # Create payment
        payment_body = {
            "source_id": source_id,
            "amount_money": {
                "amount": int(DOWNLOAD_PRICE_GBP * 100),
                "currency": "GBP"
            },
            "currency": "GBP",
            "idempotency_key": str(uuid.uuid4()),
            "reference_id": job_id,
            "note": f"NarrativeAI: {job_id}",
            "autocomplete": True
        }
        
        result = client.payments.create_payment(payment_body)
        
        if result.is_success():
            payment_id = result.result["payment"]["id"]
            logger.info(f"✅ Payment successful: {payment_id} for job {job_id}")
            
            # Grant extra conversion
            today = get_today()
            paid_key = f"{user_id}:paid:{today}"
            with sessions_lock:
                sessions[paid_key] = sessions.get(paid_key, 0) + 1
                save_sessions_to_disk(sessions)
            
            return {
                "success": True,
                "paymentId": payment_id,
                "message": "Payment successful! You can now download your audiobook.",
                "extraConversions": 1
            }
        else:
            error_msg = str(result.errors) if result.errors else "Payment processing error"
            logger.error(f"❌ Payment error: {error_msg}")
            raise HTTPException(400, f"Payment failed: {error_msg}")
    
    except Exception as e:
        logger.error(f"❌ Square payment error: {e}")
        raise HTTPException(500, f"Payment error: {str(e)}")

@app.get("/", response_class=HTMLResponse)
async def root():
    # Serve the new landing page
    landing_path = Path(__file__).parent / "index_new.html"
    if landing_path.exists():
        return landing_path.read_text()
    else:
        # Fallback to old UI if index_new.html not found
        ui_path = Path(__file__).parent / "ui.html"
        return ui_path.read_text() if ui_path.exists() else get_html_ui()

@app.post("/upload")
async def upload(bg: BackgroundTasks, file: UploadFile = File(...), multi_voice: bool = True, tier: str = "audio_only"):
    """Upload PDF and start conversion with pricing tier support"""
    if not file.filename.endswith('.pdf'):
        raise HTTPException(400, "Only PDF files are supported")
    
    # Validate tier
    if not is_valid_tier(tier):
        raise HTTPException(400, f"Invalid tier: {tier}. Must be one of: audio_only, video_addon, premium_bundle")
    
    content = await file.read()
    if len(content) > 50*1024*1024:
        raise HTTPException(413, "File too large")
    
    # Create job ID with just timestamp + random suffix (avoid filename issues)
    import uuid
    jid = f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    pdf_filename = file.filename.replace('.pdf', '')
    (UPLOAD_DIR / f"{jid}.pdf").write_bytes(content)
    
    tier_info = get_tier_info(tier)
    
    with jobs_lock:
        jobs[jid] = {
            "id": jid, 
            "status": "pending", 
            "file": file.filename, 
            "filename": pdf_filename, 
            "progress": 0,
            "tier": tier,
            "include_video": tier in ["video_addon", "premium_bundle"],
            "video_status": None,
            "video_id": None
        }
        save_jobs_to_disk(jobs)
    
    logger.info(f"✅ Job {jid} created for file: {file.filename}, tier: {tier}")
    bg.add_task(run_process_pdf, jid, UPLOAD_DIR / f"{jid}.pdf", multi_voice, tier)
    return {"job_id": jid, "status": "pending", "tier": tier}

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
    """Download audio file from completed job (legacy endpoint)"""
    if jid not in jobs or jobs[jid]['status'] != 'completed':
        raise HTTPException(400, "Job not ready or not found")
    
    f = OUTPUT_DIR / f"{jid}.mp3"
    if not f.exists():
        logger.error(f"❌ Download: Audio file not found: {f}")
        raise HTTPException(404, f"Audio file not found for job {jid}")
    
    filename = f"{jobs[jid]['file'].replace('.pdf','')}.mp3"
    logger.info(f"✅ Download: Sending {filename} ({f.stat().st_size / 1024 / 1024:.1f}MB)")
    return FileResponse(f, filename=filename, media_type="audio/mpeg")

@app.get("/video-status/{job_id}")
async def get_video_status(job_id: str):
    """Get D-ID video generation status"""
    if not D_ID_AVAILABLE:
        raise HTTPException(503, "Video generation service unavailable")
    
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    
    job = jobs[job_id]
    if not job.get("include_video"):
        raise HTTPException(400, "This job does not have video generation enabled")
    
    if not job.get("video_id"):
        return {
            "status": "pending",
            "message": "Video generation not yet started"
        }
    
    try:
        status_result = D_ID_CLIENT.get_status(job["video_id"])
        
        with jobs_lock:
            jobs[job_id]["video_status"] = status_result.get("status")
            save_jobs_to_disk(jobs)
        
        return {
            "video_id": job["video_id"],
            "status": status_result.get("status"),
            "result_url": status_result.get("result_url") if status_result.get("status") == "completed" else None
        }
    except Exception as e:
        logger.error(f"❌ Error getting video status: {e}")
        raise HTTPException(500, f"Error checking video status: {str(e)}")

@app.get("/download/{job_id}")
async def download_file(job_id: str, type: str = "audio"):
    """Download audio or video file. Type: 'audio' or 'video'"""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    
    job = jobs[job_id]
    
    if type == "audio":
        # Download audio MP3
        if job['status'] != 'completed':
            raise HTTPException(400, "Audio not yet available")
        
        f = OUTPUT_DIR / f"{job_id}.mp3"
        if not f.exists():
            logger.error(f"❌ Download: Audio file not found: {f}")
            raise HTTPException(404, f"Audio file not found for job {job_id}")
        
        filename = f"{job['file'].replace('.pdf','')}.mp3"
        logger.info(f"✅ Download: Sending {filename} ({f.stat().st_size / 1024 / 1024:.1f}MB)")
        return FileResponse(f, filename=filename, media_type="audio/mpeg")
    
    elif type == "video":
        # Download video MP4
        if not job.get("include_video"):
            raise HTTPException(400, "This job does not include video")
        
        if not job.get("video_id"):
            raise HTTPException(400, "Video not yet generated")
        
        # Get video status
        try:
            status_result = D_ID_CLIENT.get_status(job["video_id"])
            if status_result.get("status") != "completed":
                raise HTTPException(400, f"Video not yet ready: {status_result.get('status')}")
            
            # Return the video URL from D-ID
            video_url = status_result.get("result_url")
            if not video_url:
                raise HTTPException(500, "Video URL not available from D-ID")
            
            logger.info(f"✅ Download: Video ready for {job_id}")
            return {"video_url": video_url, "status": "completed"}
        except Exception as e:
            logger.error(f"❌ Error downloading video: {e}")
            raise HTTPException(500, f"Error retrieving video: {str(e)}")
    
    else:
        raise HTTPException(400, "Invalid type. Must be 'audio' or 'video'")

def detect_speaker(text: str, segment_index: int = 0) -> tuple:
    """
    Advanced speaker detection with NLP analysis and character tracking.
    Returns: (voice_id, text) tuple
    
    Detection hierarchy:
    1. Character names (e.g., "John said") - consistent voice assignment
    2. Dialogue with gender hints (he/she said)
    3. Single-quoted speech
    4. Questions (ends with ?)
    5. Exclamations (ends with !)
    6. Emotional tone analysis (sentiment polarity)
    7. Voice rotation for narrative variety
    
    OPTIMIZED FOR: Professional adult narration using Standard engine
    - Professional voices: Joanna, Matthew, Justin, Ivy, Salli, Brian, Kimberly
    - No SSML prosody (not supported in all AWS regions)
    - Simple text delivery for maximum compatibility
    """
    global GLOBAL_CHARACTER_VOICES
    
    text_lower = text.lower()
    voice_id = "narrator"
    
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
    
    # LEVEL 2: DIALOGUE DETECTION - Gender-aware dialogue handling
    elif re.search(r'"[^"]{10,}"', text):
        if re.search(r'(he\s+said|he\s+asked|he\s+exclaimed|he\s+bellowed)', text_lower):
            voice_id = "male_1"
        elif re.search(r'(she\s+said|she\s+asked|she\s+whispered)', text_lower):
            voice_id = "female_2"
        else:
            voice_id = "male_1" if segment_index % 2 == 0 else "female_1"
    
    # LEVEL 3: SINGLE-QUOTED SPEECH
    elif re.search(r"'[^']{10,}'", text):
        voice_id = "female_1"
    
    # LEVEL 4: QUESTIONS
    elif text.strip().endswith('?'):
        voice_id = "female_2" if segment_index % 3 == 0 else "male_2"
    
    # LEVEL 5: EXCLAMATIONS
    elif text.strip().endswith('!'):
        voice_id = "male_2" if segment_index % 2 == 0 else "female_1"
    
    # LEVEL 6: EMOTIONAL TONE DETECTION using TextBlob sentiment analysis
    else:
        try:
            if HAS_TEXTBLOB:
                blob = TextBlob(text[:500])
                polarity = blob.sentiment.polarity
                
                if polarity > 0.4:  # Happy/positive
                    voice_id = "female_1"
                elif polarity < -0.4:  # Sad/negative
                    voice_id = "old_male"
                else:  # Neutral
                    voice_rotation = ["narrator", "male_2", "male_1"]
                    voice_id = voice_rotation[segment_index % len(voice_rotation)]
            else:
                # LEVEL 7: FALLBACK - Voice rotation
                voice_rotation = ["narrator", "male_2", "male_1"]
                voice_id = voice_rotation[segment_index % len(voice_rotation)]
        except Exception as e:
            logger.debug(f"Sentiment analysis failed: {e}")
            voice_rotation = ["narrator", "male_2", "male_1"]
            voice_id = voice_rotation[segment_index % len(voice_rotation)]
    
    return voice_id

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
                            # detect_speaker now returns only voice_id
                            voice_id = detect_speaker(para, segment_index)
                            segments.append({
                                "text": para.strip(), 
                                "voice_id": voice_id,
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

def run_process_pdf(jid: str, path: Path, use_multi_voice: bool = True, tier: str = "audio_only"):
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
            loop.run_until_complete(process_pdf(jid, path, use_multi_voice, tier))
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

async def process_pdf(jid: str, path: Path, use_multi_voice: bool = True, tier: str = "audio_only"):
    global GLOBAL_CHARACTER_VOICES
    GLOBAL_CHARACTER_VOICES = {}  # Reset character voices for each new PDF
    try:
        logger.info(f"Starting {jid} with tier: {tier}")
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
                    
                    # For Standard engine: use plain text (no SSML prosody)
                    # Standard engine is compatible with all voices in all AWS regions
                    # Professional voices (Joanna, Matthew, etc.) already sound adult-like
                    plain_text = text
                    
                    # Use STANDARD engine - compatible with all regions and voices
                    # Professional voices provide:
                    # - Natural, adult-sounding narration
                    # - Clear enunciation
                    # - Professional delivery
                    response = polly_client.synthesize_speech(
                        Text=plain_text, 
                        TextType="text", 
                        OutputFormat="mp3", 
                        VoiceId=voice, 
                        Engine="standard"  # Standard engine for wide compatibility
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
        
        # Now handle video generation if tier includes it
        if tier in ["video_addon", "premium_bundle"] and D_ID_AVAILABLE:
            logger.info(f"Job {jid}: Starting D-ID video generation for tier: {tier}")
            with jobs_lock:
                jobs[jid]["progress"] = 95
                save_jobs_to_disk(jobs)
            
            try:
                # Audio URL must be publicly accessible
                audio_url = f"https://narrativeai.myblognow.uk/download/{jid}?type=audio"
                
                # Create D-ID video
                video_result = D_ID_CLIENT.create_video(
                    audio_url=audio_url,
                    driver_url="https://d-id-public-bucket.s3.amazonaws.com/or-paul_20220721.png"  # Default avatar
                )
                
                video_id = video_result.get("id")
                if video_id:
                    logger.info(f"✅ D-ID video creation initiated: {video_id}")
                    with jobs_lock:
                        jobs[jid]["video_id"] = video_id
                        jobs[jid]["video_status"] = "processing"
                        save_jobs_to_disk(jobs)
                else:
                    logger.error(f"❌ D-ID video creation failed: no video ID returned")
                    with jobs_lock:
                        jobs[jid]["video_status"] = "failed"
                        save_jobs_to_disk(jobs)
            except Exception as e:
                logger.error(f"❌ D-ID video generation error: {e}")
                with jobs_lock:
                    jobs[jid]["video_status"] = "failed"
                    jobs[jid]["error"] = f"Video generation failed: {str(e)}"
                    save_jobs_to_disk(jobs)
        
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


# ===== BLOG ROUTES =====
BLOG_POSTS = {
    "pdf-to-audiobook-guide": {
        "title": "Complete Guide: Convert PDF to Audiobook Free",
        "slug": "pdf-to-audiobook-guide",
        "excerpt": "Learn how to convert any PDF into a professional audiobook in minutes using NarrativeAI.",
        "image": "https://via.placeholder.com/800x400?text=PDF+to+Audiobook",
        "author": "NarrativeAI Team",
        "date": "2026-09-17",
        "content": """
<h2>Why Convert PDF to Audiobook?</h2>
<p>PDF to audiobook conversion is perfect for:</p>
<ul>
  <li>📚 Students wanting to learn while commuting</li>
  <li>🚗 Drivers who want educational content</li>
  <li>♿ People with visual impairments</li>
  <li>📖 Book lovers who want to "read" faster</li>
</ul>

<h2>How to Use NarrativeAI</h2>
<ol>
  <li>Upload your PDF file</li>
  <li>Choose your preferred voice</li>
  <li>Click Convert</li>
  <li>Download your audiobook as MP3</li>
</ol>

<h2>Features</h2>
<ul>
  <li>✅ Natural-sounding voices</li>
  <li>✅ Multiple voice options</li>
  <li>✅ High-quality audio output</li>
  <li>✅ Fast processing</li>
  <li>✅ Secure and private</li>
</ul>

<h2>Pricing</h2>
<p>Get <strong>5 free conversions every day</strong>, then just £1 per additional conversion.</p>
        """
    },
    "best-text-to-speech-tools": {
        "title": "Best Text-to-Speech Tools Compared (2026)",
        "slug": "best-text-to-speech-tools",
        "excerpt": "Compare the top TTS tools and discover why NarrativeAI is the best choice for PDF audiobooks.",
        "image": "https://via.placeholder.com/800x400?text=TTS+Comparison",
        "author": "NarrativeAI Team",
        "date": "2026-09-16",
        "content": """
<h2>Text-to-Speech Tools Comparison</h2>

<table>
  <tr>
    <th>Tool</th>
    <th>Quality</th>
    <th>Price</th>
    <th>Speed</th>
  </tr>
  <tr>
    <td>NarrativeAI</td>
    <td>⭐⭐⭐⭐⭐</td>
    <td>£1 per conversion</td>
    <td>⚡ Instant</td>
  </tr>
  <tr>
    <td>Google Cloud TTS</td>
    <td>⭐⭐⭐⭐</td>
    <td>Complex pricing</td>
    <td>⚡ Fast</td>
  </tr>
  <tr>
    <td>Amazon Polly</td>
    <td>⭐⭐⭐⭐</td>
    <td>Complex pricing</td>
    <td>⚡ Fast</td>
  </tr>
</table>

<h2>Why Choose NarrativeAI?</h2>
<ul>
  <li>💰 Simple pricing (£1 per conversion)</li>
  <li>🎯 Optimized for PDFs</li>
  <li>⚡ Lightning-fast processing</li>
  <li>🎵 High-quality audio</li>
  <li>😊 Easy to use interface</li>
</ul>
        """
    }
}

@app.get("/blog", response_class=HTMLResponse)
async def blog_home():
    """Blog homepage"""
    posts_html = ""
    for post in BLOG_POSTS.values():
        posts_html += f"""
        <div class="blog-card">
            <img src="{post['image']}" alt="{post['title']}" class="blog-image">
            <div class="blog-content">
                <h3>{post['title']}</h3>
                <p class="blog-excerpt">{post['excerpt']}</p>
                <div class="blog-meta">
                    <span>By {post['author']}</span>
                    <span>{post['date']}</span>
                </div>
                <a href="/blog/{post['slug']}" class="read-more">Read More →</a>
            </div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Blog - NarrativeAI</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; }}
            nav {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 1em 2em; position: sticky; top: 0; z-index: 100; }}
            nav a {{ color: white; text-decoration: none; font-weight: 600; margin-right: 2em; }}
            nav a:hover {{ opacity: 0.8; }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 2em; }}
            .blog-grid {{ display: grid; gap: 2em; }}
            .blog-card {{ background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); transition: all 0.3s; }}
            .blog-card:hover {{ transform: translateY(-5px); box-shadow: 0 8px 16px rgba(0,0,0,0.15); }}
            .blog-image {{ width: 100%; height: 250px; object-fit: cover; }}
            .blog-content {{ padding: 1.5em; }}
            .blog-content h3 {{ color: #667eea; margin-bottom: 0.5em; }}
            .blog-excerpt {{ color: #666; line-height: 1.6; margin-bottom: 1em; }}
            .blog-meta {{ font-size: 0.9em; color: #999; display: flex; gap: 1em; margin-bottom: 1em; }}
            .read-more {{ color: #667eea; text-decoration: none; font-weight: 600; }}
            .read-more:hover {{ text-decoration: underline; }}
            h1 {{ color: #667eea; margin-bottom: 1em; }}
        </style>
    </head>
    <body>
        <nav>
            <a href="/">Home</a>
            <a href="/blog">Blog</a>
        </nav>
        <div class="container">
            <h1>📖 NarrativeAI Blog</h1>
            <p>Tips, guides, and stories about PDF to audiobook conversion</p>
            <div class="blog-grid">
                {posts_html}
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post(slug: str):
    """Individual blog post"""
    if slug not in BLOG_POSTS:
        raise HTTPException(status_code=404, detail="Blog post not found")
    
    post = BLOG_POSTS[slug]
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="description" content="{post['excerpt']}">
        <meta property="og:title" content="{post['title']}">
        <meta property="og:description" content="{post['excerpt']}">
        <meta property="og:image" content="{post['image']}">
        <title>{post['title']} - NarrativeAI</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.8; color: #333; }}
            nav {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 1em 2em; position: sticky; top: 0; z-index: 100; }}
            nav a {{ color: white; text-decoration: none; font-weight: 600; margin-right: 2em; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 2em; }}
            .blog-header {{ margin-bottom: 2em; }}
            .blog-header img {{ width: 100%; height: auto; border-radius: 8px; margin-bottom: 1em; }}
            .blog-meta {{ color: #999; font-size: 0.9em; margin-bottom: 1em; }}
            h1 {{ color: #667eea; margin-bottom: 0.5em; font-size: 2.5em; }}
            h2 {{ color: #667eea; margin-top: 1.5em; margin-bottom: 0.5em; }}
            p {{ margin-bottom: 1em; }}
            ul, ol {{ margin-left: 2em; margin-bottom: 1em; }}
            li {{ margin-bottom: 0.5em; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 1em; }}
            th, td {{ border: 1px solid #ddd; padding: 0.75em; text-align: left; }}
            th {{ background: #f5f5f5; }}
            .back-link {{ color: #667eea; text-decoration: none; font-weight: 600; }}
            .back-link:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <nav>
            <a href="/">Home</a>
            <a href="/blog">Blog</a>
        </nav>
        <div class="container">
            <a href="/blog" class="back-link">← Back to Blog</a>
            <div class="blog-header">
                <img src="{post['image']}" alt="{post['title']}">
                <h1>{post['title']}</h1>
                <div class="blog-meta">
                    <span>By {post['author']}</span>
                    <span>{post['date']}</span>
                </div>
            </div>
            <div class="blog-body">
                {post['content']}
            </div>
        </div>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv('PORT', 8000)))
