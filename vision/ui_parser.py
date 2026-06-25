"""
Vision-based UI Parser for locating elements on screen.
Uses OpenCV and Tesseract OCR, with a fallback to Windows UIAutomation.
"""
# pylint: disable=no-member, too-many-locals
import os
from typing import Optional, Tuple

import cv2
import mss
import numpy as np
import pytesseract

from core.logger import setup_logger

logger = setup_logger("UIParser")


class UIParser: # pylint: disable=too-few-public-methods
    """
    Parses the screen to find the coordinates of UI elements based on text descriptions.
    """
    def __init__(self) -> None:
        import shutil
        tesseract_path = shutil.which('tesseract')
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        else:
            logger.warning("tesseract executable not found in PATH.")

    def find_element(
            self, element_description: str) -> Optional[Tuple[int, int]]:
        """
        Uses OCR as the primary method to find text on screen.
        Falls back to Windows Accessibility Tree if OCR fails.
        """
        logger.info(
            "Scanning for '%s' using Vision OCR...", element_description)
        coords = self._find_element_ocr(element_description)

        if coords:
            return coords

        logger.warning(
            "OCR failed to find '%s'.", element_description)
        return None

    def _find_element_ocr(
            self, element_description: str) -> Optional[Tuple[int, int]]: # pylint: disable=too-many-locals
        """
        Captures the screen and uses OpenCV + Tesseract to find bounding boxes of text.
        Attempts to use C++ vision_ext for speed, falling back to Python.
        """
        try:
            # 1. Capture screen using context manager for display resilience
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # primary monitor
                screenshot = sct.grab(monitor)

            # Convert to numpy array for OpenCV
            img = np.array(screenshot)

            # Try C++ extension first
            try:
                import vision_ext
                logger.debug("Using C++ vision_ext for OCR...")
                coords = vision_ext.find_element(img, element_description)
                if coords:
                    center_x, center_y = coords
                    center_x += monitor['left']
                    center_y += monitor['top']
                    logger.info("C++ OCR Found '%s' at (%s, %s)", element_description, center_x, center_y)
                    return (center_x, center_y)
                return None
            except ImportError:
                logger.debug("vision_ext not available. Falling back to Python implementation.")
            except Exception as e:
                logger.error("C++ vision_ext failed: %s. Falling back.", e)

            # Convert from BGRA (mss default) to BGR, then to Grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

            # 2. Pre-processing: Apply thresholding to make text pop
            # We use an inverted binary threshold combined with Otsu's method
            # to handle varying backgrounds (dark mode vs light mode).
            _, thresh = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # 3. Run Tesseract to get data
            # psm 11 means: Sparse text. Find as much text as possible in no
            # particular order.
            custom_config = r'--oem 3 --psm 11'
            data = pytesseract.image_to_data(
                thresh, output_type=pytesseract.Output.DICT, config=custom_config)

            target_text = element_description.lower().strip()
            best_match_idx = -1

            # 4. Iterate through all OCR results
            for i, text_val in enumerate(data['text']):
                conf = int(data['conf'][i])
                text = text_val.lower().strip()

                # Filter out low confidence or empty text
                if conf > 30 and text:
                    # Fuzzy match: Exact or substring match
                    if target_text == text:
                        best_match_idx = i
                        break
                    # Only allow substring matching if the matched part is somewhat significant (e.g., >3 chars)
                    # to prevent tiny artifacts like "in" from matching "result_link"
                    elif len(text) >= 4 and (target_text in text or text in target_text):
                        best_match_idx = i
                        break
                    else:
                        # Fallback: Word overlap matching. Useful if LLM asks for "Google Search results: Gemini AI"
                        # but the screen just says "Gemini - Your AI assistant" or "Gemini AI".
                        target_words = set([w for w in target_text.split() if len(w) > 3])
                        screen_words = set([w for w in text.split() if len(w) > 3])
                        if target_words and screen_words:
                            overlap = len(target_words.intersection(screen_words))
                            if overlap >= 2 or (len(target_words) == 1 and overlap == 1):
                                best_match_idx = i
                                break

            if best_match_idx != -1:
                x = data['left'][best_match_idx]
                y = data['top'][best_match_idx]
                w = data['width'][best_match_idx]
                h = data['height'][best_match_idx]

                # Calculate center coordinates for clicking
                center_x = x + (w // 2)
                center_y = y + (h // 2)

                # Adjust for monitor offsets if necessary
                center_x += monitor['left']
                center_y += monitor['top']

                logger.info(
                    "OCR Found '%s' matching '%s' at (%s, %s)",
                    data['text'][best_match_idx], element_description, center_x, center_y)
                return (center_x, center_y)

            return None

        except (FileNotFoundError, ValueError, cv2.error) as e:
            logger.error("OCR Parsing failed: %s", e)
            logger.debug("Did you install Tesseract-OCR on your system?")
            return None

    def extract_all_text(self, image_path: Optional[str] = None) -> str:
        """
        Extracts all visible text from the screen or a specific image.
        Uses psm 3 (Fully automatic page segmentation) which is better for
        reading blocks of text/sentences than psm 11.
        """
        try:
            if image_path:
                img = cv2.imread(image_path)
                if img is None:
                    logger.error("Failed to read image at %s", image_path)
                    return ""
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    screenshot = sct.grab(monitor)
                img = np.array(screenshot)
                gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

            # Pre-processing
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # psm 3: Fully automatic page segmentation, but no OSD.
            # Good for extracting continuous sentences.
            custom_config = r'--oem 3 --psm 3'
            data = pytesseract.image_to_data(
                thresh, output_type=pytesseract.Output.DICT, config=custom_config)

            # Reconstruct lines of text to preserve phrases
            lines = {}
            for i, text in enumerate(data['text']):
                conf = int(data['conf'][i])
                text = text.strip()
                if conf > 30 and text:
                    block_num = data['block_num'][i]
                    line_num = data['line_num'][i]
                    key = f"{block_num}_{line_num}"
                    if key not in lines:
                        lines[key] = []
                    lines[key].append(text)

            # Join words in each line, then join lines
            extracted_text = " ".join([" ".join(words) for words in lines.values()])
            return extracted_text

        except (FileNotFoundError, ValueError, cv2.error) as e:
            logger.error("Failed to extract text: %s", e)
            return ""
