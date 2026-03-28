# ✅ TELEGRAM INTEGRATION PRE-FLIGHT CHECKLIST

Before running the test suite, verify these essentials:

## 🔑 Configuration Check

```
Location: orion/config.py
```

- [ ] `BOT_TOKEN` is set and valid (must start with numbers)
- [ ] `CHAT_ID` is set to your Telegram chat ID (numeric)
- [ ] `DEV_ID` is set to your user ID for admin commands

**How to find your Chat ID:**
1. Message the bot: `/start`
2. Check `data/logs.txt` for your user ID
3. Or: Use bot API with: `https://api.telegram.org/botYOUR_TOKEN/getUpdates`

## 🤖 System Check

### Backend Status
```bash
# Terminal 1: Start backend (FastAPI)
cd e:\PROJECT-ORION\backend
python -m uvicorn app.main:app --reload
# Should print: "Application startup complete"
```

### Check Services
- [ ] **Ollama**: Running locally? 
  ```bash
  # Terminal 2: Check Ollama
  ollama serve
  # Check at: http://localhost:11434/api/tags
  ```

- [ ] **Gemini API**: Credentials configured?
  ```bash
  # Check if .env has GEMINI_API_KEY
  # or Google credentials file exists
  ```

### Telegram Bot Check
```bash
# Terminal 3: Start Telegram bot + scheduler
cd e:\PROJECT-ORION\orion
python main.py
# Should print: "ORION SYSTEM BOOT"
#               "Scheduler thread started"
#               "Telegram bot started and polling"
```

## 📡 Connectivity Verification

From your machine, can you reach:
- [ ] Telegram API: `curl https://api.telegram.org/bot<TOKEN>/getMe`
- [ ] Google Vision API (if camera): Check credentials
- [ ] Ollama: `curl http://localhost:11434/api/tags`
- [ ] Gemini API: Test with `/debug` command

## 📁 Files Verified

- [ ] `orion/config.py` exists with BOT_TOKEN, CHAT_ID, DEV_ID
- [ ] `orion/main.py` runs without errors
- [ ] `orion/integrations/telegram_bot.py` has all handlers:
  - `/start`, `/add`, `/today`, `/status`, `/health`, `/dnd`, `/logs`, `/see`, `/debug`
- [ ] `orion/telegram_test_suite.py` exists
- [ ] `TELEGRAM_TEST_GUIDE.md` exists

## 🧪 Quick System Test

Before running full test suite:

```bash
# Test 1: Can you message the bot?
# Send: /start
# Expect: Command list appears in <2s

# Test 2: Check scheduler is running
# Try: /status
# Expect: State shown, no crashes

# Test 3: Check AI routing is working
# Send: "hello"
# Expect: AI response within 3 seconds (Ollama or Gemini)
```

## 🚀 Ready to Test?

If ALL checks pass:

```bash
# Run full 7-phase test (20 minutes)
cd e:\PROJECT-ORION\orion
python telegram_test_suite.py

# Then provide results:
# - Which phases passed/failed
# - Any delays or errors
# - System state after testing
```

---

## ⚠️ If Something Is Missing

| Missing | Fix |
|---------|-----|
| No Telegram response | Check BOT_TOKEN, restart python main.py |
| Delays in commands | Kill process, check for hanging handlers |
| /debug fails | Ensure you're DEV_ID (check config.py) |
| /see crashes | Install: `pip install opencv-python` |
| Scheduler doesn't fire | Check main.py send() function wiring |
| Not receiving notifications | Verify CHAT_ID matches your Telegram chat |

---

**Status:** Ready for testing? Let me know! 🚀
