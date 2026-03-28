# ORION - Personal Executive AI Assistant

## Architecture

ORION is designed as a modular, API-first system.

### 1. Core (The Brain)
- **Framework**: FastAPI (Python)
- **Role**: Central controller, Intent Engine, Action Engine, Memory System.

### 2. Services
- **Gemini Service**: Handles complex reasoning and natural language generation.
- **Memory Service**: Manages Short-term (Context) and Long-term (SQLite) memory.
- **Browser Service**: Handles "attentive" data gathering via browser emulation.

### 3. Input Layers (Clients)
- **Web Interface**: React-based dashboard.
- **Voice/Vision Client**: Python script for Mic/Camera input (runs on Pi or local machine).

## Setup

1. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   playwright install
   ```

2. Run Backend:
   ```bash
   uvicorn backend.app.main:app --reload
   ```

## API Endpoints

- `POST /chat`: Main interaction endpoint (Text/Voice-to-Text).
- `POST /vision/face`: specific face recognition endpoint.
- `POST /vision/object`: Object detection endpoint.
- `POST /action/schedule`: Meeting/Task management.
