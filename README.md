# NarrativeAI 🎙️📚

Convert any PDF into a professionally narrated audiobook with character-specific voices using AWS Polly and FastAPI.

## Features ✨

- 📄 **PDF Upload**: Simple web interface to upload PDF files
- 🎤 **Text-to-Speech**: AWS Polly integration for high-quality audio
- 👥 **Character Recognition**: Detects and tracks characters in dialogue (MVP)
- ⚙️ **Background Processing**: Async job queue for PDF processing
- 📊 **Job Tracking**: Monitor conversion progress in real-time
- 🚀 **Auto-Deployment**: GitHub Actions CI/CD pipeline to AWS Lightsail
- 🏥 **Health Checks**: Built-in health monitoring endpoints

## Tech Stack

- **Backend**: FastAPI + Python 3.11
- **TTS Engine**: AWS Polly
- **PDF Processing**: pdfplumber
- **Cloud Hosting**: AWS Lightsail
- **CI/CD**: GitHub Actions
- **Containerization**: Docker
- **Testing**: Pytest

## Quick Start

### Prerequisites
- Python 3.11+
- AWS Account with Polly access
- Git

### Local Development

1. **Clone repository**
```bash
git clone https://github.com/karlondon/NarrativeAI.git
cd NarrativeAI
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure AWS credentials**
```bash
cp .env.example .env
# Edit .env with your AWS credentials
```

5. **Run locally**
```bash
python main.py
```

Visit `http://localhost:8000/docs` to access the Swagger UI.

## API Endpoints

### Health Check
```bash
GET /health
```

### Upload PDF
```bash
POST /upload
Content-Type: multipart/form-data

Response:
{
  "job_id": "job_1234567890_document",
  "status": "pending"
}
```

### Get Job Status
```bash
GET /jobs/{job_id}
```

### Download Audiobook
```bash
GET /jobs/{job_id}/download
```

## Project Structure

```
NarrativeAI/
├── main.py                    # FastAPI application
├── test_main.py              # Unit tests
├── requirements.txt          # Python dependencies
├── Dockerfile               # Docker image
├── docker-compose.yml       # Docker Compose config
├── .env.example             # Environment template
├── .gitignore              # Git ignore rules
├── .github/
│   └── workflows/
│       └── deploy.yml      # GitHub Actions CI/CD
└── README.md               # Documentation
```
# Deployment with proper AWS credentials
