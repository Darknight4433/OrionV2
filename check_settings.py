from backend.app.core.config import settings, PROJECT_ROOT
import os

print(f"PROJECT_ROOT: {PROJECT_ROOT}")
print(f".env exists: {os.path.exists(os.path.join(PROJECT_ROOT, '.env'))}")
print(f"GEMINI_API_KEYS: {settings.GEMINI_API_KEYS}")
print(f"Type: {type(settings.GEMINI_API_KEYS)}")
if settings.GEMINI_API_KEYS:
    print(f"First key length: {len(settings.GEMINI_API_KEYS[0])}")
