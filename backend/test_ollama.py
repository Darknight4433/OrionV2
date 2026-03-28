import requests
import json

def test_ollama():
    url = "http://localhost:11434/api/tags"
    try:
        response = requests.get(url)
        print("--- Ollama Server Status ---")
        if response.status_code == 200:
            models = response.json().get('models', [])
            print(f"Ollama is online!")
            print(f"Loaded models: {[m['name'] for m in models]}")
            
            # Check for gemma3:4b
            if any(m['name'] == 'gemma3:4b' or 'gemma3:4b' in m['name'] for m in models):
                print("SUCCESS: gemma3:4b is installed and ready.")
            else:
                print("WARNING: gemma3:4b not found in Ollama tags. Did you run 'ollama pull gemma3:4b'?")
        else:
            print(f"Ollama returned status code {response.status_code}")
            
    except Exception as e:
        print(f"Ollama Connection Error: {e}")
        print("Is Ollama running (check your taskbar for the icon)?")

if __name__ == "__main__":
    test_ollama()
