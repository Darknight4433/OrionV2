import os
import time
import re
import sys
from colorama import init, Fore, Style

# Initialize colorama for Windows support
init()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "orion_errors.log")

# Error Signatures & Explanations
ERROR_MAP = {
    r"429": "Rate limit exceeded (API). Rotating keys...",
    r"401": "Invalid API Key. Please check your .env file.",
    r"TimeoutError": "Request timed out. Check your internet connection.",
    r"ALSA": "Audio driver warning (Linux/Pi). Usually safe to ignore.",
    r"PortAudio": "Audio interface error. Check your microphone connection.",
    r"face_recognition": "Face detection lag. Consider reducing resolution.",
    r"sqlite3": "Database lock. System is busy writing memory.",
    r"Permission denied": "Security block. Check file permissions.",
    r"Gemini": "Google AI service hiccup. Switching to local Ollama...",
    r"bulbul": "Sarvam AI Voice error. Checking fallback...",
}

def monitor_errors():
    print(f"{Fore.CYAN}{Style.BRIGHT}═══════════════════════════════════════════════")
    print(f"   ORION LIVE DEBUGGER & ERROR ANALYZER")
    print(f"═══════════════════════════════════════════════{Style.RESET_ALL}")
    print(f"Project Target: {PROJECT_ROOT}")
    print(f"Monitoring: {LOG_FILE}\n")

    if not os.path.exists(LOG_FILE):
        print(f"{Fore.YELLOW}[WARN]{Fore.RESET} Waiting for log file to be created...")
        while not os.path.exists(LOG_FILE):
            time.sleep(2)

    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            # Start at the end
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                
                # Check for signatures
                found_match = False
                current_explanation = ""
                
                for pattern, explanation in ERROR_MAP.items():
                    if re.search(pattern, line, re.IGNORECASE):
                        current_explanation = explanation
                        found_match = True
                        break
                
                # Visual output
                timestamp = line.split("|")[0].strip() if "|" in line else "LIVE"
                message = line.split("-")[-1].strip() if "-" in line else line.strip()
                
                if found_match:
                    print(f"{Fore.RED}{Style.BRIGHT}[CRITICAL]{Style.RESET_ALL} {Fore.WHITE}{timestamp}{Fore.RESET}")
                    print(f"  » {Fore.YELLOW}{message}{Fore.RESET}")
                    print(f"  {Fore.GREEN}INFO: {current_explanation}{Fore.RESET}\n")
                else:
                    print(f"{Fore.BLUE}[INFO]{Fore.RESET} {timestamp} - {message}")

    except KeyboardInterrupt:
        print(f"\n{Fore.CYAN}Debugger detached.{Fore.RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"{Fore.RED}Debugger Crashed: {e}{Fore.RESET}")

if __name__ == "__main__":
    monitor_errors()
