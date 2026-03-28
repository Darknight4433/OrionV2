import face_recognition
import os
import pickle
import sys
from PIL import Image, ImageOps
import numpy as np
import cv2

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACES_DIR = os.path.join(PROJECT_ROOT, "data", "faces")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "data", "encoded_file.p")

def reencode():
    print("--- ORION Face Re-Encoding System ---")
    if not os.path.exists(FACES_DIR):
        print(f"Error: Faces directory not found at {FACES_DIR}")
        return

    known_encodings = []
    known_names = []

    image_files = [f for f in os.listdir(FACES_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if not image_files:
        print("No images found in data/faces/")
        return

    print(f"Found {len(image_files)} images. Starting encoding...")

    for filename in image_files:
        name = os.path.splitext(filename)[0]
        img_path = os.path.join(FACES_DIR, filename)
        
        try:
            # Load and convert to RGB
            image = face_recognition.load_image_file(img_path)
            
            # --- PRE-PROCESSING: CLAHE (Contrast Enhancement) ---
            # Most accuracy issues are lighting-related. CLAHE fixes this.
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            equalized_gray = clahe.apply(gray)
            # Reconstruct RGB for face_recognition
            equalized_image = cv2.merge([equalized_gray, equalized_gray, equalized_gray])

            # --- DATA AUGMENTATION: Mirroring ---
            # Flips the face to handle users looking slightly left/right
            mirrored_image = cv2.flip(equalized_image, 1)

            variants = [
                ("Original (Enhanced)", equalized_image),
                ("Mirrored (Enhanced)", mirrored_image)
            ]

            for variant_name, img in variants:
                print(f"  Encoding {name} ({variant_name})...", end=" ", flush=True)
                # Use high-quality jitter (num_jitters=20 is the sweet spot)
                encodings = face_recognition.face_encodings(img, num_jitters=20, model="hog")
                
                if encodings:
                    known_encodings.append(encodings[0])
                    known_names.append(name)
                    print("[OK]")
                else:
                    print("[FAILED]")
                
        except Exception as e:
            print(f"[ERROR] {e}")

    if known_encodings:
        print(f"\nSaving {len(known_encodings)} encodings to {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'wb') as f:
            pickle.dump((known_encodings, known_names), f)
        print("Success! Restart ORION to apply changes.")
    else:
        print("\nFailed: No valid encodings generated.")

if __name__ == "__main__":
    reencode()
