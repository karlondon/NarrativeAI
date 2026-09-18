"""D-ID API Client for Video Generation"""
import os
import requests
from typing import Dict, Optional

class DIDClient:
    BASE_URL = "https://api.d-id.com/talks"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def create_video(self, audio_url: str, avatar: str = "morgan-png", name: str = "Video") -> Dict:
        """Create talking head video from audio"""
        payload = {
            "script": {"type": "audio", "audio_url": audio_url},
            "config": {"fluent": True, "pad_audio": 0.0},
            "presenter_id": avatar,
            "name": name
        }
        try:
            r = requests.post(self.BASE_URL, headers=self.headers, json=payload, timeout=30)
            r.raise_for_status()
            d = r.json()
            return {"success": True, "video_id": d.get("id"), "status": d.get("status")}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_status(self, video_id: str) -> Dict:
        """Check video generation status"""
        try:
            r = requests.get(f"{self.BASE_URL}/{video_id}", headers=self.headers, timeout=10)
            r.raise_for_status()
            d = r.json()
            return {"success": True, "status": d.get("status"), "result_url": d.get("result_url")}
        except Exception as e:
            return {"success": False, "error": str(e)}

def get_did_client() -> Optional[DIDClient]:
    """Get D-ID client from environment variable"""
    key = os.getenv("D_ID_API_KEY")
    return DIDClient(key) if key else None
