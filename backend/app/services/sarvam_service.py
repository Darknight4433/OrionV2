import requests
import os
import uuid
from typing import Optional
from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger()

class SarvamService:
    def __init__(self):
        self.api_keys = settings.SARVAM_API_KEYS
        self.current_key_index = 0
        self.base_url = "https://api.sarvam.ai/text-to-speech"

    def _rotate_key(self):
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)

    def generate_tts(self, text: str, output_path: str) -> bool:
        if not self.api_keys:
            return False

        max_retries = len(self.api_keys)
        retries = 0

        while retries < max_retries:
            key = self.api_keys[self.current_key_index]
            try:
                payload = {
                    "inputs": [text],
                    "target_language_code": "en-IN",
                    "speaker": "priya",
                    "pitch": 0,
                    "pace": 1.0,
                    "loudness": 1.5,
                    "speech_sample_rate": 8000,
                    "enable_preprocessing": True,
                    "model": "bulbul:v2"
                }
                headers = {
                    "api-subscription-key": key,
                    "Content-Type": "application/json"
                }

                response = requests.post(self.base_url, json=payload, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    import base64
                    data = response.json()
                    audio_base64 = data.get("audios", [])[0]
                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(audio_base64))
                    return True
                
                elif response.status_code in [429, 401]:
                    logger.warning(f"Sarvam Key #{self.current_key_index} exhausted or invalid. Rotating...")
                    self._rotate_key()
                    retries += 1
                else:
                    logger.error(f"Sarvam API error ({response.status_code}): {response.text}")
                    return False

            except Exception as e:
                logger.error(f"Sarvam request failed: {e}")
                self._rotate_key()
                retries += 1

        return False
