import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "0.3.0"

def test_root():
    """Test root endpoint - returns HTML UI"""
    response = client.get("/")
    assert response.status_code == 200
    assert "NarrativeAI" in response.text

def test_upload_pdf_missing():
    """Test upload with no file"""
    response = client.post("/upload")
    assert response.status_code == 422

def test_upload_wrong_type():
    """Test upload with wrong file type"""
    response = client.post("/upload", files={"file": ("test.txt", b"text content")})
    assert response.status_code == 400

def test_job_not_found():
    """Test getting non-existent job"""
    response = client.get("/jobs/nonexistent")
    assert response.status_code == 200
    assert "error" in response.json()
