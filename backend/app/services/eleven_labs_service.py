import requests
import os
from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger()

class ElevenLabsService:
    def __init__(self):
        self.api_key = settings.ELEVENLABS_API_KEY
        self.voice_id = settings.ELEVENLABS_VOICE_ID
        self.base_url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"

    def generate_tts(self, text: str, output_path: str) -> bool:
        if not self.api_key:
            return False

        try:
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            
            payload = {
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.5
                }
            }

            response = requests.post(self.base_url, json=payload, headers=headers, timeout=15)
            
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                return True
            else:
                logger.error(f"ElevenLabs API error ({response.status_code}): {response.text}")
                return False

        except Exception as e:
            logger.error(f"ElevenLabs request failed: {e}")
            return False
