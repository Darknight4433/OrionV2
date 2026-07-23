from pydantic_settings import BaseSettings, SettingsConfigDict
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

class Settings(BaseSettings):
    PROJECT_NAME: str = "ORION"
    VERSION: str = "2.0.0"
    API_PREFIX: str = "/api"
    
    # Ollama Configuration — PRIMARY AI (runs locally)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma3"

    # Gemini Configuration — FALLBACK only (cloud, when Ollama is down)
    GEMINI_API_KEYS: list[str] = []
    
    # Voice Configuration
    SARVAM_API_KEYS: list[str] = []
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Default Rachel voice

    WAKE_WORDS: list[str] = ["orion", "hello orion", "hey orion"]
    SPEAKER_CARD_INDEX: int = 1
    MIC_INDEX: int | None = None
    
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
