import os
import time
import base64
from app.core.logging import get_logger

logger = get_logger()

try:
    from google.cloud import vision
except ImportError:
    vision = None


class VisionService:
    def __init__(self):
        self.client = vision.ImageAnnotatorClient() if vision else None
        if not self.client:
            logger.warning("Google Cloud Vision not available. Check installation.")
            
        self.daily_calls = 0
        self.last_call_time = 0
        self.daily_reset_time = time.time()
        self.last_seen_objects = []

    def analyze_image(self, image_data_b64: str) -> str:
        """Analyze a base64 encoded image with cost & quality filters."""
        if not self.client:
            return "Google Cloud Vision client is not initialized."

        now = time.time()
        
        # Reset daily quota
        if now - self.daily_reset_time > 86400:
            self.daily_calls = 0
            self.daily_reset_time = now

        # Constraints
        if self.daily_calls >= 50:
            return "Vision API daily quota reached."
            
        if now - self.last_call_time < 10:
            if self.last_seen_objects:
                return "I see: " + ", ".join(self.last_seen_objects)
            return "Vision cooldown active (Wait 10s)."

        try:
            content = base64.b64decode(image_data_b64.split(",")[-1] if "," in image_data_b64 else image_data_b64)
            image = vision.Image(content=content)

            # Label & Text detection
            features = [
                vision.Feature(type_=vision.Feature.Type.LABEL_DETECTION, max_results=10),
                vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION)
            ]
            request = vision.AnnotateImageRequest(image=image, features=features)
            response = self.client.annotate_image(request)
            
            self.daily_calls += 1
            self.last_call_time = now

            if response.error.message:
                return f"Vision API error: {response.error.message}"

            # Filter labels (confidence >= 0.70, top 3)
            valid_labels = [l.description for l in response.label_annotations if getattr(l, 'score', 0) >= 0.70][:3]
            
            text_detected = ""
            if response.text_annotations:
                # Get the first text annotation which contains the entire detected text
                text_detected = f" (Text detected: '{response.text_annotations[0].description.replace('\n', ' ')[:50]}...')"
                
            self.last_seen_objects = valid_labels

            if not valid_labels and not text_detected:
                return "I couldn't identify anything specific."

            return "I see: " + ", ".join(valid_labels) + text_detected
            
        except Exception as e:
            logger.error(f"Error in vision analysis: {e}")
            return f"Error analyzing image: {str(e)}"
