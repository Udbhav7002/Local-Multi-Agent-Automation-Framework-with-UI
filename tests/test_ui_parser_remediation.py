"""
Unit tests for UIParser single-monitor bounds check and exception handling remediation.
"""
from unittest.mock import MagicMock, patch

import pytest

# Skip tests if heavy dependencies are not available
pytesseract = pytest.importorskip("pytesseract")
cv2 = pytest.importorskip("cv2")

from vision.ui_parser import UIParser  # noqa: E402  (must follow importorskip guards)


def test_ui_parser_single_monitor_bounds():
    """Verify single monitor system (len(monitors) == 1) does not raise IndexError."""
    parser = UIParser()
    mock_sct = MagicMock()
    mock_sct.monitors = [{"top": 0, "left": 0, "width": 1920, "height": 1080}]
    mock_sct.grab.return_value = MagicMock()

    mock_mss = MagicMock()
    mock_mss.__enter__.return_value = mock_sct

    with patch("mss.mss", return_value=mock_mss), \
         patch("cv2.cvtColor", return_value=MagicMock()), \
         patch("cv2.threshold", return_value=(0, MagicMock())), \
         patch("pytesseract.image_to_data") as mock_tess:
        mock_tess.return_value = {
            'text': ['submit'],
            'conf': [90],
            'left': [10],
            'top': [10],
            'width': [50],
            'height': [20]
        }
        result = parser._find_element_ocr("submit")
        assert result == (35, 20)


def test_ui_parser_extract_all_text_single_monitor():
    """Verify extract_all_text on single monitor system does not raise IndexError."""
    parser = UIParser()
    mock_sct = MagicMock()
    mock_sct.monitors = [{"top": 0, "left": 0, "width": 1920, "height": 1080}]
    mock_sct.grab.return_value = MagicMock()

    mock_mss = MagicMock()
    mock_mss.__enter__.return_value = mock_sct

    with patch("mss.mss", return_value=mock_mss), \
         patch("cv2.cvtColor", return_value=MagicMock()), \
         patch("cv2.threshold", return_value=(0, MagicMock())), \
         patch("pytesseract.image_to_data") as mock_tess:
        mock_tess.return_value = {
            'text': ['hello', 'world'],
            'conf': [90, 90],
            'block_num': [1, 1],
            'line_num': [1, 1]
        }
        text = parser.extract_all_text()
        assert text == "hello world"


def test_ui_parser_ocr_uncaught_exceptions_graceful_fallback():
    """Verify TesseractError, IndexError, and RuntimeError are caught in _find_element_ocr."""
    parser = UIParser()

    for exc in [
        pytesseract.TesseractError(1, "tesseract error"),
        IndexError("list index out of range"),
        RuntimeError("runtime error"),
        cv2.error("cv2 error"),
        FileNotFoundError("file not found"),
        ValueError("value error")
    ]:
        with patch("mss.mss", side_effect=exc):
            result = parser._find_element_ocr("test")
            assert result is None, f"Expected None when catching {type(exc)}, got {result}"


def test_ui_parser_extract_text_uncaught_exceptions_graceful_fallback():
    """Verify TesseractError, IndexError, and RuntimeError are caught in extract_all_text."""
    parser = UIParser()

    for exc in [
        pytesseract.TesseractError(1, "tesseract error"),
        IndexError("list index out of range"),
        RuntimeError("runtime error"),
        cv2.error("cv2 error"),
        FileNotFoundError("file not found"),
        ValueError("value error")
    ]:
        with patch("mss.mss", side_effect=exc):
            text = parser.extract_all_text()
            assert text == "", f"Expected empty string when catching {type(exc)}, got {text}"


def test_ui_parser_find_element_empty_input():
    """Verify find_element with empty/whitespace input returns None."""
    parser = UIParser()
    assert parser.find_element("") is None
    assert parser.find_element("   ") is None
    assert parser.find_element(None) is None
