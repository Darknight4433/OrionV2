from loguru import logger
import sys
import os

if not os.path.exists("logs"):
    os.makedirs("logs")

logger.remove()

logger.add(sys.stderr, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>", level="INFO")

# Optimized for Accountability / PC Mode: Long retention
logger.add("logs/orion.log", rotation="20 MB", retention="30 days", level="INFO")
logger.add("logs/orion_errors.log", rotation="20 MB", retention="90 days", level="ERROR", backtrace=True, diagnose=True)

# --- ALSA/PortAudio Silencer ---
def silence_alsa():
    if os.name == 'posix': # Linux/Pi
        try:
            from ctypes import cdll, CFUNCTYPE, c_char_p, c_int
            
            # Define error handler callback
            ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
            def py_error_handler(filename, line, function, err, fmt):
                pass
            c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
            
            # Load asound library
            asound = None
            for lib in ['libasound.so', 'libasound.so.2']:
                try:
                    asound = cdll.LoadLibrary(lib)
                    asound.snd_lib_error_set_handler(c_error_handler)
                    break
                except:
                    pass
            if asound:
                logger.debug("ALSA Error suppression active.")
        except Exception:
            pass

# Initialize silencer
silence_alsa()

def get_logger():
    return logger
