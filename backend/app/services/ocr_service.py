"""
OCR Service — ORION V2
=======================
Dedicated Optical Character Recognition (OCR) subsystem for document reading.
Complies with Specification Section 14:
  • Separate from the general VLM
  • Triggered by commands like "ORION, read this" / "what does this say"
  • OpenCV capture -> OCR extraction -> Ollama summarization -> TTS
"""

import cv2
import numpy as np
import asyncio
from typing import Optional, Tuple
from app.core.logging import get_logger

logger = get_logger()


class OCRService:
    """
    Extracts text from captured frames and prepares it for concise spoken reading.
    """

    def __init__(self):
        self._tesseract_available: Optional[bool] = None

    def _check_tesseract(self) -> bool:
        if self._tesseract_available is not None:
            return self._tesseract_available
        try:
            import pytesseract
            # Quick version check to verify tesseract binary
            pytesseract.get_tesseract_version()
            self._tesseract_available = True
        except Exception:
            self._tesseract_available = False
            logger.info("[OCR] pytesseract binary not detected. Fallback OCR logic active.")
        return self._tesseract_available

    async def extract_text(self, frame: np.ndarray) -> Tuple[bool, str]:
        """
        Preprocesses frame and extracts text.
        Returns: (success, extracted_text)
        """
        loop = asyncio.get_event_loop()

        def _do_ocr():
            try:
                # Preprocessing for OCR: Grayscale + CLAHE + Otsu Thresholding
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                enhanced = clahe.apply(gray)
                _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

                if self._check_tesseract():
                    import pytesseract
                    text = pytesseract.image_to_string(thresh, config="--psm 6")
                    cleaned = " ".join(text.split())
                    return True, cleaned

                # If Tesseract is not installed, return structured notification
                return False, "OCR engine binary (tesseract) is not installed on this system."

            except Exception as e:
                logger.error(f"[OCR] Text extraction failed: {e}")
                return False, str(e)

        return await loop.run_in_executor(None, _do_ocr)
