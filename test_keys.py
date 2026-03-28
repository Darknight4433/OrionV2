import os
import google.generativeai as genai
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GEMINI_API_KEYS: list[str] = []
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()
print(f"Loaded Keys: {settings.GEMINI_API_KEYS}")

for i, key in enumerate(settings.GEMINI_API_KEYS):
    print(f"\nTesting Key #{i}: {key[:10]}...")
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Say 'Key working'")
        print(f"Success: {response.text}")
    except Exception as e:
        print(f"Failed: {e}")
