from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

class Settings(BaseSettings):
    PROJECT_NAME: str = "ORION"
    VERSION: str = "2.0.0"
    API_PREFIX: str = "/api"
    
    # Groq — PRIMARY (free, ~500ms, get key at https://console.groq.com)
    GROQ_API_KEY: str = ""
    GROQ_API_KEYS: list[str] = []   # multiple keys for rotation
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # Ollama — CPU last resort fallback
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "phi3:latest"

    # Gemini — secondary fallback
    GEMINI_API_KEYS: list[str] = []
    
    # Voice Configuration
    SARVAM_API_KEYS: list[str] = []
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Default Rachel voice

    WAKE_WORDS: list[str] = ["orion", "hello orion", "hey orion"]
    SPEAKER_CARD_INDEX: int = 1
    MIC_INDEX: Optional[int] = None
    
    @field_validator("MIC_INDEX", mode="before")
    @classmethod
    def parse_mic_index(cls, v):
        if v is None or v == "" or (isinstance(v, str) and not v.strip()):
            return None
        return int(v)

    # Vision & VLM Configuration (Specification Section 32)
    HF_VISION_MODEL: str = "Qwen/Qwen2.5-VL-3B-Instruct"
    HF_TOKENS: list[str] = []
    HF_TOKEN_1: str = ""
    HF_TOKEN_2: str = ""
    HF_TOKEN_3: str = ""
    VISION_PROVIDER: str = "huggingface"
    VISION_FALLBACK_PROVIDER: str = "gemini"
    CAMERA_DEVICE: int = 0
    VISION_CAPTURE_DELAY: float = 1.5
    VISION_MAX_REQUESTS: int = 5
    VISION_TIMEOUT: float = 15.0

    # Gemini — Specialist & Fallback
    GEMINI_API_KEY: str = ""
    GEMINI_API_KEY_1: str = ""
    GEMINI_API_KEY_2: str = ""
    GEMINI_API_KEY_3: str = ""
    GEMINI_API_KEY_4: str = ""
    GEMINI_API_KEY_5: str = ""
    GEMINI_API_KEYS_1: str = ""
    GEMINI_API_KEYS_2: str = ""
    GEMINI_API_KEYS_3: str = ""
    GEMINI_API_KEYS_4: str = ""
    GEMINI_API_KEYS: list[str] = []
    
    # Vision Configuration
    FACE_MATCH_TOLERANCE: float = 0.50
    VISION_ENABLED: bool = True
    
    # Database
    DATABASE_URL: str = f"sqlite:///{os.path.join(PROJECT_ROOT, 'data', 'orion.db')}"
    
    model_config = SettingsConfigDict(
        env_file=os.path.join(PROJECT_ROOT, '.env'),
        case_sensitive=True,
        extra='ignore'
    )

settings = Settings()
