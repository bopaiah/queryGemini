# -*- coding: utf-8 -*-
"""
Test Script: gemini_utils Image Operations
Author: Bopaiah Mekerira

Description:
    Integration tests for analyze_image() and edit_image() from gemini_utils.
    Uses a real image file (face.jpg) if present, or creates a minimal test image.

    - analyze_image: uploads the image and requests a text description using the GEO prefix.
    - edit_image: uploads the image and requests an edited version using the IMAGE prefix.

Usage:
    python test_image_ops.py
"""

# --- Standard library imports ---
import os
import sys
import json

# --- Third-party imports ---
from dotenv import load_dotenv

# --- Local imports ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from prompt_utils import getPrompt
from gemini_utils import analyze_image, edit_image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_test_image(path):
    """
    Creates a minimal test image at the given path.

    Tries PIL first (100x100 red square). Falls back to writing a raw
    1x1 red JPEG if PIL is not installed.

    Args:
        path (str): File path where the test image will be saved.
    """
    print(f"Creating a simple test image at {path}...")
    try:
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='red')
        img.save(path)
        print("Test image created with PIL.")
    except ImportError:
        import base64
        # Minimal 1x1 red dot JPEG (base64-encoded)
        red_dot = (
            b'/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U'
            b'HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN'
            b'DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy'
            b'MjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcI'
            b'CQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0Kxw'
            b'RVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZn'
            b'aGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXG'
            b'x8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAA'
            b'AAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMi'
            b'MoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RV'
            b'VldYWVpjZGVmZ2h1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5'
            b'usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oADAMBAAIRAxEA'
            b'PwD5/oooor/9k='
        )
        with open(path, "wb") as f:
            f.write(base64.b64decode(red_dot))
        print("Test image created with fallback bytes.")


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

def main():
    """
    Runs analyze_image and edit_image integration tests.

    Loads environment from .env, ensures a test image exists, then calls
    each function and prints the JSON result.
    """
    load_dotenv()

    test_img = "face.jpg"
    edited_img = "face_edited.jpg"

    if not os.path.exists(test_img):
        create_test_image(test_img)

    # --- Test analyze_image ---
    print("\n--- Testing analyze_image ---")
    try:
        result = analyze_image("GEO", "Tell me what you see in this image.", test_img)
        print("Analysis Result:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Analysis failed: {e}")

    # --- Test edit_image ---
    print("\n--- Testing edit_image ---")
    try:
        result = edit_image("IMAGE", getPrompt("img_edit"), test_img, edited_img)
        print("Edit Result:")
        print(json.dumps(result, indent=2))
        if os.path.exists(edited_img):
            print(f"Edited image saved to: {edited_img}")
    except Exception as e:
        print(f"Edit failed: {e}")


if __name__ == "__main__":
    main()
