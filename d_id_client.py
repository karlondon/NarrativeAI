"""D-ID API Client for Video Generation"""
import os
import requests
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class DIDClient:
    BASE_URL = "https://api.d-id.com/talks"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        logger.info(f"D-ID Client initialized with API key (first 20 chars): {api_key[:20] if api_key else 'None'}...")
    
    def create_video(self, audio_url: str, avatar: str = "morgan-png", name: str = "Video") -> Dict:
        """Create talking head video from audio"""
        payload = {
            "script": {"type": "audio", "audio_url": audio_url},
            "config": {"fluent": True, "pad_audio": 0.0},
            "presenter_id": avatar,
            "name": name
        }
        logger.info(f"D-ID: Sending POST to {self.BASE_URL}")
        logger.info(f"D-ID: Payload: {payload}")
        logger.info(f"D-ID: Headers: Authorization header present: {'Authorization' in self.headers}")
        
        try:
            r = requests.post(self.BASE_URL, headers=self.headers, json=payload, timeout=30)
            logger.info(f"D-ID: Response status code: {r.status_code}")
            logger.info(f"D-ID: Response body: {r.text}")
            r.raise_for_status()
            d = r.json()
            return {"success": True, "video_id": d.get("id"), "status": d.get("status")}
        except Exception as e:
            logger.error(f"D-ID: Exception occurred: {str(e)}")
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
