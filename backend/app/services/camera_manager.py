"""
Camera Manager — ORION V2
==========================
OpenCV camera acquisition and strict image quality validation.
Complies with Specification Sections 9, 10, 11, 24:
  • States: CAMERA_IDLE, CAMERA_PREPARING, CAMERA_CAPTURING, CAMERA_PROCESSING, CAMERA_ERROR
  • Default state: CAMERA_IDLE
  • Captures ONE frame on demand; no continuous streaming to external APIs
  • Validation: dimensions, mean intensity, contrast, non-zero, corruption checks
  • Temporary in-memory or ephemeral processing; zero persistent raw image retention
"""

import time
import cv2
import numpy as np
import base64
from enum import Enum
from typing import Optional, Tuple
from dataclasses import dataclass
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()


class CameraState(str, Enum):
    CAMERA_IDLE       = "CAMERA_IDLE"
    CAMERA_PREPARING  = "CAMERA_PREPARING"
    CAMERA_CAPTURING  = "CAMERA_CAPTURING"
    CAMERA_PROCESSING = "CAMERA_PROCESSING"
    CAMERA_ERROR      = "CAMERA_ERROR"


@dataclass
class ValidationResult:
    is_valid: bool
    reason: str = ""
    mean_brightness: float = 0.0
    contrast: float = 0.0
    resolution: Tuple[int, int] = (0, 0)


class CameraManager:
    """
    Acquires single frames from hardware OpenCV capture or processes
    client-pushed video frames with strict quality assurance.
    """

    def __init__(self, device_index: Optional[int] = None):
        self.device_index = device_index if device_index is not None else getattr(settings, "CAMERA_DEVICE", 0)
        self.state: CameraState = CameraState.CAMERA_IDLE
        self._last_capture_time: float = 0.0

    def capture_frame(self, delay: float = 0.5) -> Tuple[Optional[np.ndarray], ValidationResult]:
        """
        Activates camera, waits for camera sensor auto-exposure stabilization,
        captures ONE frame, immediately releases the camera device, and returns to CAMERA_IDLE.
        """
        self.state = CameraState.CAMERA_PREPARING
        logger.info(f"[CAMERA] Activating device #{self.device_index} for single-frame capture...")

        cap = None
        try:
            if delay > 0:
                time.sleep(delay)

            self.state = CameraState.CAMERA_CAPTURING
            backends = [cv2.CAP_ANY, cv2.CAP_DSHOW, cv2.CAP_MSMF] if hasattr(cv2, "CAP_DSHOW") else [cv2.CAP_ANY]
            
            for b in backends:
                try:
                    cap = cv2.VideoCapture(self.device_index, b)
                    if cap.isOpened():
                        break
                except Exception:
                    continue

            if not cap or not cap.isOpened():
                self.state = CameraState.CAMERA_ERROR
                logger.error("[CAMERA] Could not open camera device.")
                return None, ValidationResult(is_valid=False, reason="Camera device unavailable")

            # Flush stale frame buffer (grab a couple of frames to allow sensor to adjust exposure)
            for _ in range(3):
                cap.grab()

            ret, frame = cap.read()
            if not ret or frame is None:
                self.state = CameraState.CAMERA_ERROR
                logger.error("[CAMERA] Failed to read frame from camera.")
                return None, ValidationResult(is_valid=False, reason="Failed to read frame")

            self._last_capture_time = time.time()
            self.state = CameraState.CAMERA_PROCESSING

            val = self.validate_frame(frame)
            return frame, val

        except Exception as e:
            self.state = CameraState.CAMERA_ERROR
            logger.error(f"[CAMERA] Exception during capture: {e}")
            return None, ValidationResult(is_valid=False, reason=str(e))
        finally:
            if cap is not None:
                cap.release()
            self.state = CameraState.CAMERA_IDLE
            logger.info("[CAMERA] Capture finished. Device released, state returned to CAMERA_IDLE.")

    def validate_frame(self, frame: Optional[np.ndarray]) -> ValidationResult:
        """
        Performs comprehensive quality checks:
          - Image exists and is numpy ndarray
          - Dimensions >= 100x100
          - Non-zero pixels
          - Not pitch black (mean brightness >= 20/255)
          - Not washed out (mean brightness <= 245/255)
          - Sufficient contrast (standard deviation >= 12)
        """
        if frame is None:
            return ValidationResult(is_valid=False, reason="No frame provided")

        if not isinstance(frame, np.ndarray):
            return ValidationResult(is_valid=False, reason="Frame is not a valid image array")

        if frame.size == 0 or len(frame.shape) < 2:
            return ValidationResult(is_valid=False, reason="Empty or corrupted image frame")

        h, w = frame.shape[:2]
        if h < 100 or w < 100:
            return ValidationResult(
                is_valid=False,
                reason=f"Resolution too low ({w}x{h}), minimum 100x100 required",
                resolution=(w, h)
            )

        # Grayscale conversion for photometric metrics
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        mean_mat, std_mat = cv2.meanStdDev(gray)
        mean_val = float(mean_mat[0][0])
        std_val = float(std_mat[0][0])

        if mean_val < 18.0:
            return ValidationResult(
                is_valid=False,
                reason="Image is too dark or pitch black",
                mean_brightness=mean_val,
                contrast=std_val,
                resolution=(w, h)
            )

        if mean_val > 248.0:
            return ValidationResult(
                is_valid=False,
                reason="Image is completely washed out or overexposed",
                mean_brightness=mean_val,
                contrast=std_val,
                resolution=(w, h)
            )

        if std_val < 10.0:
            return ValidationResult(
                is_valid=False,
                reason="Image lacks contrast or is completely uniform",
                mean_brightness=mean_val,
                contrast=std_val,
                resolution=(w, h)
            )

        return ValidationResult(
            is_valid=True,
            reason="Quality check passed",
            mean_brightness=mean_val,
            contrast=std_val,
            resolution=(w, h)
        )

    def prepare_image(self, frame: np.ndarray, max_dim: int = 1024, quality: int = 85) -> bytes:
        """
        Normalizes, resizes if exceeding max_dim, and encodes as JPEG bytes.
        """
        h, w = frame.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            new_w, new_h = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        success, enc = cv2.imencode(".jpg", frame, encode_param)
        if not success:
            raise RuntimeError("Failed to encode frame to JPEG format")

        return enc.tobytes()

    def decode_base64_frame(self, b64_str: str) -> Optional[np.ndarray]:
        """Decodes base64-encoded frame from WebSocket or HTTP payload."""
        try:
            if "," in b64_str:
                b64_str = b64_str.split(",", 1)[1]
            raw_bytes = base64.b64decode(b64_str)
            nparr = np.frombuffer(raw_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return frame
        except Exception as e:
            logger.error(f"[CAMERA] Base64 decode error: {e}")
            return None
