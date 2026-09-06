"""
Empirical Stress Test Suite for Vision UIParser Remediation.
Tests boundary conditions, empty/corrupted inputs, multi/single/empty monitor configurations,
and exception handling across pytesseract, cv2, mss, and built-in exceptions.
"""
import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest

# Skip tests if heavy dependencies are not available
cv2 = pytest.importorskip("cv2")
pytesseract = pytest.importorskip("pytesseract")
np = pytest.importorskip("numpy")

from vision.ui_parser import UIParser


class TestUIParserMonitorBounds:
    """Stress tests for monitor array indexing."""

    def test_single_monitor_find_element(self):
        """Single monitor (len == 1) should correctly pick monitors[0] without IndexError."""
        parser = UIParser()
        mock_sct = MagicMock()
        mock_sct.monitors = [{"top": 0, "left": 0, "width": 1920, "height": 1080}]
        mock_sct.grab.return_value = np.zeros((1080, 1920, 4), dtype=np.uint8)

        mock_mss = MagicMock()
        mock_mss.__enter__.return_value = mock_sct

        with patch("mss.mss", return_value=mock_mss), \
             patch("cv2.cvtColor", return_value=np.zeros((1080, 1920), dtype=np.uint8)), \
             patch("cv2.threshold", return_value=(0, np.zeros((1080, 1920), dtype=np.uint8))), \
             patch("pytesseract.image_to_data") as mock_tess:
            mock_tess.return_value = {
                'text': ['login'],
                'conf': [95],
                'left': [50],
                'top': [50],
                'width': [100],
                'height': [40]
            }
            result = parser.find_element("login")
            assert result == (100, 70)

    def test_empty_monitors_array_find_element(self):
        """Empty monitors array (len == 0) should raise IndexError internally, caught gracefully returning None."""
        parser = UIParser()
        mock_sct = MagicMock()
        mock_sct.monitors = []  # Empty list will trigger IndexError on monitors[0]

        mock_mss = MagicMock()
        mock_mss.__enter__.return_value = mock_sct

        with patch("mss.mss", return_value=mock_mss):
            result = parser.find_element("login")
            assert result is None

    def test_empty_monitors_array_extract_all_text(self):
        """Empty monitors array (len == 0) should trigger IndexError, caught gracefully returning empty string."""
        parser = UIParser()
        mock_sct = MagicMock()
        mock_sct.monitors = []

        mock_mss = MagicMock()
        mock_mss.__enter__.return_value = mock_sct

        with patch("mss.mss", return_value=mock_mss):
            result = parser.extract_all_text()
            assert result == ""


class TestUIParserExceptionHandling:
    """Stress tests for all required exception types raised during OCR and image parsing."""

    @pytest.mark.parametrize("exception_cls,exc_instance", [
        ("TesseractError", pytesseract.TesseractError(1, "OCR engine error")),
        ("RuntimeError", RuntimeError("Generic runtime failure")),
        ("IndexError", IndexError("List index out of range")),
        ("FileNotFoundError", FileNotFoundError("Missing file resource")),
        ("ValueError", ValueError("Invalid dimension or format")),
        ("cv2.error", cv2.error("OpenCV internal error")),
    ])
    def test_find_element_ocr_exceptions_caught(self, exception_cls, exc_instance):
        """Verify find_element catches exception gracefully and returns None."""
        parser = UIParser()
        with patch("mss.mss", side_effect=exc_instance):
            res = parser.find_element("Search")
            assert res is None, f"Failed for {exception_cls}: expected None, got {res}"

    @pytest.mark.parametrize("exception_cls,exc_instance", [
        ("TesseractError", pytesseract.TesseractError(1, "OCR engine error")),
        ("RuntimeError", RuntimeError("Generic runtime failure")),
        ("IndexError", IndexError("List index out of range")),
        ("FileNotFoundError", FileNotFoundError("Missing file resource")),
        ("ValueError", ValueError("Invalid dimension or format")),
        ("cv2.error", cv2.error("OpenCV internal error")),
    ])
    def test_extract_all_text_exceptions_caught(self, exception_cls, exc_instance):
        """Verify extract_all_text catches exception gracefully and returns empty string."""
        parser = UIParser()
        with patch("mss.mss", side_effect=exc_instance):
            res = parser.extract_all_text()
            assert res == "", f"Failed for {exception_cls}: expected '', got {res}"


class TestUIParserInputEdgeCases:
    """Stress tests for empty, corrupted, and whitespace inputs."""

    def test_whitespace_and_empty_target_descriptions(self):
        """Verify find_element returns None without invoking OCR for whitespace/empty targets."""
        parser = UIParser()
        with patch.object(parser, '_find_element_ocr') as mock_ocr:
            assert parser.find_element("") is None
            assert parser.find_element(" ") is None
            assert parser.find_element("   \t\n\r  ") is None
            assert parser.find_element(None) is None
            mock_ocr.assert_not_called()

    def test_extract_all_text_nonexistent_image(self):
        """extract_all_text with non-existent file path should return empty string."""
        parser = UIParser()
        res = parser.extract_all_text("/path/to/nonexistent/file_12345.png")
        assert res == ""

    def test_extract_all_text_empty_0byte_image_file(self):
        """extract_all_text with 0-byte corrupted image file should return empty string."""
        parser = UIParser()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_path = f.name
        try:
            res = parser.extract_all_text(temp_path)
            assert res == ""
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_extract_all_text_corrupted_image_content(self):
        """extract_all_text with corrupted binary text in image file should return empty string."""
        parser = UIParser()
        with tempfile.NamedTemporaryFile(suffix=".png", mode="wb", delete=False) as f:
            f.write(b"NOT_A_REAL_PNG_IMAGE_DATA_CORRUPTED_BYTES")
            temp_path = f.name
        try:
            res = parser.extract_all_text(temp_path)
            assert res == ""
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
