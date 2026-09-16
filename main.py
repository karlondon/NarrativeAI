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

VOICES = {
    "narrator": "Joanna",
    "male_1": "Matthew",
    "male_2": "Justin",
    "female_1": "Ivy",
    "female_2": "Salli",
    "old_male": "Gary",
    "child": "Kimberly"
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
    return get_html_ui()

@app.post("/upload")
async def upload(file: UploadFile = File(...), multi_voice: bool = True, bg: BackgroundTasks = None):
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
        logger.error(f"Error extracting: {e}")
        raise
    return segments

async def process_pdf(jid: str, path: Path, use_multi_voice: bool = True):
    try:
        jobs[jid]["status"] = "processing"
        jobs[jid]["progress"] = 10
        segments = extract_segments(path)
        if not segments:
            raise ValueError("No text found")
        jobs[jid]["progress"] = 30
        audio_files = []
        if polly:
            for idx, seg in enumerate(segments):
                try:
                    voice = VOICES.get(seg["speaker"], VOICES["narrator"]) if use_multi_voice else VOICES["narrator"]
                    text = seg["text"]
                    if seg["speaker"] != "narrator":
                        ssml = f'<speak><prosody rate="1.0" pitch="+5%">{text}</prosody></speak>'
                    else:
                        ssml = f'<speak>{text}</speak>'
                    response = polly.synthesize_speech(Text=ssml, TextType="ssml", OutputFormat="mp3", VoiceId=voice, Engine="neural")
                    audio_path = OUTPUT_DIR / f"{jid}_seg_{idx}.mp3"
                    audio_path.write_bytes(response["AudioStream"].read())
                    audio_files.append(audio_path)
                    jobs[jid]["progress"] = min(30 + int((idx / len(segments)) * 60), 90)
                    logger.info(f"Segment {idx+1}/{len(segments)} - {voice}")
                except Exception as e:
                    logger.error(f"Segment {idx}: {e}")
                    continue
            jobs[jid]["progress"] = 90
            if audio_files:
                try:
                    concat_file = OUTPUT_DIR / f"{jid}_concat.txt"
                    with open(concat_file, "w") as f:
                        for af in audio_files:
                            f.write(f"file '{af}'\n")
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
    except Exception as e:
        logger.error(f"Error: {e}")
        jobs[jid]["status"] = "failed"
        jobs[jid]["error"] = str(e)

def get_html_ui():
    return '''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>NarrativeAI</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:"Segoe UI",Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}.container{background:white;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3);max-width:600px;width:100%;padding:40px}.header{text-align:center;margin-bottom:30px}.header h1{color:#667eea;font-size:2.5em;margin-bottom:10px}.header p{color:#666;font-size:1.1em}.file-label{display:flex;align-items:center;justify-content:center;width:100%;padding:40px 20px;border:2px dashed #667eea;border-radius:10px;background:#f8f9ff;cursor:pointer;transition:all 0.3s;font-size:1.1em;color:#667eea;font-weight:600}.file-label:hover{background:#e8ebff;border-color:#764ba2}.file-label.dragover{background:#e8ebff;border-color:#764ba2;transform:scale(1.02)}#file-input{display:none}.options{margin:20px 0;padding:15px;background:#f8f9ff;border-radius:10px}.option-group{display:flex;align-items:center;gap:10px}.option-group input[type="checkbox"]{width:20px;height:20px;cursor:pointer}.option-group label{cursor:pointer;flex:1;color:#333}.option-group small{color:#999;display:block;margin-left:30px}.btn{width:100%;padding:15px;border:none;border-radius:10px;font-size:1.1em;font-weight:600;cursor:pointer;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;transition:all 0.3s;margin-top:20px}.btn:hover:not(:disabled){transform:translateY(-2px);box-shadow:0 10px 25px rgba(102,126,234,0.4)}.btn:disabled{opacity:0.6;cursor:not-allowed}.status-section{margin-top:30px;display:none}.status-section.active{display:block}.job-card{background:#f8f9ff;padding:20px;border-radius:10px;border-left:4px solid #667eea}.job-card h3{color:#333;margin-bottom:10px;word-break:break-word}.job-info{display:flex;justify-content:space-between;margin:10px 0;font-size:0.95em;color:#666}.status-badge{display:inline-block;padding:5px 12px;border-radius:20px;font-size:0.9em;font-weight:600}.status-pending{background:#fff3cd;color:#856404}.status-processing{background:#cfe2ff;color:#084298}.status-completed{background:#d1e7dd;color:#0f5132}.status-failed{background:#f8d7da;color:#842029}.progress-bar{width:100%;height:8px;background:#e0e0e0;border-radius:10px;overflow:hidden;margin:15px 0}.progress-fill{height:100%;background:linear-gradient(90deg,#667eea 0%,#764ba2 100%);width:0%;transition:width 0.3s}.btn-download{background:#28a745;color:white;width:100%;padding:10px;border-radius:8px;text-decoration:none;text-align:center;font-weight:600;margin-top:10px;display:inline-block}.btn-download:hover{background:#218838;text-decoration:none}.error-message{background:#f8d7da;color:#842029;padding:12px;border-radius:8px;margin-top:10px}.features{margin-top:30px;padding-top:30px;border-top:2px solid #eee}.features h4{color:#667eea;margin-bottom:15px}.features ul{list-style:none;color:#666}.features li{padding:8px 0;padding-left:25px;position:relative}.features li:before{content:"✓";position:absolute;left:0;color:#667eea;font-weight:bold}</style></head><body><div class="container"><div class="header"><h1>🎙️ NarrativeAI</h1><p>Convert PDFs to Professional Audiobooks</p></div><div class="upload-section"><label for="file-input" class="file-label" id="file-label">📄 Click to upload PDF or drag and drop</label><input type="file" id="file-input" accept=".pdf"/><div class="options"><div class="option-group"><input type="checkbox" id="multi-voice" checked/><label for="multi-voice">Multi-Voice Narration<small>Use different voices for dialogue and characters</small></label></div></div><button class="btn" id="upload-btn">🚀 Upload & Convert</button></div><div class="status-section" id="status-section"><h3>📊 Conversion Status</h3><div class="job-card"><h3 id="job-name"></h3><div class="job-info"><span>Status:</span><span class="status-badge" id="job-status"></span></div><div class="job-info"><span>Progress:</span><span id="job-progress">0%</span></div><div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div><div id="error-container"></div><a href="#" class="btn-download" id="download-btn" style="display:none;">📥 Download Audiobook</a></div></div><div class="features"><h4>✨ Features</h4><ul><li>🎭 Multi-voice narration with character detection</li><li>😊 Emotional expression using Neural voices</li><li>🎵 Professional audio quality</li><li>📄 Support for large PDFs (up to 50MB)</li><li>⏱️ Real-time progress tracking</li></ul></div></div><script>let selectedFile=null;const fileInput=document.getElementById("file-input"),fileLabel=document.getElementById("file-label"),uploadBtn=document.getElementById("upload-btn"),statusSection=document.getElementById("status-section"),multiVoiceCheckbox=document.getElementById("multi-voice");fileInput.addEventListener("change",e=>{selectedFile=e.target.files[0];selectedFile&&(fileLabel.textContent=`✅ Selected: ${selectedFile.name}`)});fileLabel.addEventListener("dragover",e=>{e.preventDefault();fileLabel.classList.add("dragover")});fileLabel.addEventListener("dragleave",()=>{fileLabel.classList.remove("dragover")});fileLabel.addEventListener("drop",e=>{e.preventDefault();fileLabel.classList.remove("dragover");const t=e.dataTransfer.files;t.length>0&&t[0].name.endsWith(".pdf")?(selectedFile=t[0],fileLabel.textContent=`✅ Selected: ${selectedFile.name}`,fileInput.files=t):alert("Please select a PDF file")});uploadBtn.addEventListener("click",async()=>{selectedFile||alert("Please select a PDF file first")||uploadBtn||(uploadBtn.disabled=!0,uploadBtn.textContent="⏳ Uploading...");const e=new FormData;e.append("file",selectedFile),e.append("multi_voice",multiVoiceCheckbox.checked);try{const t=await fetch("/upload",{method:"POST",body:e}),a=await t.json();t.ok?(statusSection.classList.add("active"),document.getElementById("job-name").textContent=selectedFile.name,function(e){setInterval(async()=>{try{const t=await fetch(`/jobs/${e}`),a=await t.json();document.getElementById("job-status").textContent=a.status.toUpperCase(),document.getElementById("job-status").className=`status-badge status-${a.status}`,document.getElementById("job-progress").textContent=`${a.progress}%`,document.getElementById("progress-fill").style.width=`${a.progress}%`,"completed"===a.status&&(document.getElementById("download-btn").style.display="block",document.getElementById("download-btn").href=`/jobs/${e}/download`),"failed"===a.status&&(document.getElementById("error-container").innerHTML=`<div class="error-message">❌ Error: ${a.error||"Conversion failed"}</div>`)}catch(e){console.error("Monitoring error:",e)}},1000)}(a.job_id)):alert(`Error: ${a.detail||"Upload failed"}`)}catch(e){alert(`Error: ${e.message}`)}finally{uploadBtn.disabled=!1,uploadBtn.textContent="🚀 Upload & Convert"}});if(!selectedFile)return;</script></body></html>'''

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv('PORT', 8000)))
