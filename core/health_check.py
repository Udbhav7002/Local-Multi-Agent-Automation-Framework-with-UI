"""
Startup health checks for the Multi-Agent Automation Framework.
Verifies that all critical dependencies are available before
the REPL loop starts, providing human-readable error messages.
"""
import sys
import shutil

from core.logger import setup_logger, console

logger = setup_logger("HealthCheck")


def check_dependencies() -> bool:
    """
    Verifies all critical dependencies are installed and accessible.
    Returns True if all checks pass, False otherwise.
    """
    all_ok = True

    # --- Required Python packages ---
    required_packages = {
        "ollama": "pip install ollama",
        "chromadb": "pip install chromadb",
        "mss": "pip install mss",
        "rich": "pip install rich",
    }

    optional_packages = {
        "pyautogui": "pip install pyautogui  (needed for GUI automation)",
        "pytesseract": "pip install pytesseract  (needed for OCR element finding)",
        "cv2": "pip install opencv-python  (needed for vision UI parsing)",
        "playwright": "pip install playwright && playwright install chromium  (needed for browser automation)",
    }

    for package, install_cmd in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            logger.error(f"Missing required package '{package}'. {install_cmd}")
            all_ok = False

    for package, install_cmd in optional_packages.items():
        try:
            __import__(package)
        except ImportError:
            logger.warning(f"Optional package '{package}' not installed - {install_cmd}")

    # --- System tools ---
    if not shutil.which("tesseract"):
        console.print(
            "  [#ffaa00]![/#ffaa00] [#888888]Tesseract OCR not found in PATH. "
            "OCR-based element finding will be disabled.[/#888888]"
        )
        console.print(
            "    [#888888]Install: brew install tesseract[/#888888]"
        )

    # --- Ollama connectivity ---
    try:
        import ollama  # pylint: disable=import-outside-toplevel
        ollama.list()
    except ImportError:
        pass  # Already caught above
    except Exception:
        console.print("  [#ffaa00]![/#ffaa00] [#888888]Ollama not running. Starting it in the background...[/#888888]")
        import subprocess
        import time
        if not shutil.which("ollama"):
            console.print("  [#ff0000]✗[/#ff0000] [bold]Ollama executable not found in PATH.[/bold]")
            console.print("    [#888888]Please install Ollama from https://ollama.com[/#888888]")
            return False
        try:
            # Start ollama serve in the background
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            time.sleep(3)  # Give it a moment to bind to the port
            ollama.list()  # Try again
            console.print("  [#00ff00]✓[/#00ff00] [#888888]Ollama started successfully.[/#888888]")
        except Exception as e:
            console.print(
                "  [#ff0000]✗[/#ff0000] [bold]Cannot connect to or start Ollama.[/bold]"
            )
            console.print(
                "    [#888888]Please run 'ollama serve' manually.[/#888888]"
            )
            all_ok = False

    if all_ok:
        logger.debug("All dependency checks passed.")

    return all_ok
