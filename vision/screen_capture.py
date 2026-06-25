"""
Screen capture utility using the `mss` library.
Provides extremely fast, native screenshot capabilities.

Refactored to:
- Use context manager per capture (resilient to display config changes)
- Support timestamped filenames for debugging vision trails
"""
import os
import time

import mss
import mss.tools

from core.logger import setup_logger

logger = setup_logger("ScreenCapture")

# Resolve screenshots directory relative to project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCREENSHOTS_DIR = os.path.join(_PROJECT_ROOT, "screenshots")


class ScreenCapture:  # pylint: disable=too-few-public-methods
    """
    Handles taking fullscreen screenshots of the primary monitor.
    Uses a fresh mss instance per capture for resilience to display changes.
    """

    def __init__(self, save_dir: str | None = None) -> None:
        self._save_dir = save_dir or _SCREENSHOTS_DIR
        os.makedirs(self._save_dir, exist_ok=True)

    def capture_fullscreen(
        self, output_filename: str = "screenshot.png"
    ) -> str:
        """
        Captures the entire screen and saves it to a PNG file.
        Returns the absolute path to the saved image.
        """
        try:
            # Use context manager for resilience to display changes
            # (clamshell mode, external monitor plug/unplug)
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                output = sct.grab(monitor)

                # Generate timestamped filename for debugging trail
                base, ext = os.path.splitext(output_filename)
                timestamp = int(time.time())
                timestamped_name = f"{base}_{timestamp}{ext}"

                output_path = os.path.join(self._save_dir, timestamped_name)
                mss.tools.to_png(
                    output.rgb, output.size, output=output_path
                )

                # Also save a "latest" copy for quick access
                latest_path = os.path.join(self._save_dir, output_filename)
                mss.tools.to_png(
                    output.rgb, output.size, output=latest_path
                )

                logger.debug(
                    "Captured screenshot to %s", output_path
                )
                
                self.cleanup()
                return latest_path

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to capture screen: %s", e)
            raise e

    def capture_region(
        self, x: int, y: int, width: int, height: int, output_filename: str = "region.png"
    ) -> str:
        """
        Captures a specific region of the screen and saves it to a PNG file.
        Returns the absolute path to the saved image.
        """
        try:
            with mss.mss() as sct:
                # The bounding box of the monitor
                monitor = sct.monitors[1]
                
                # Define the region to capture, offset by the monitor's top/left
                region = {
                    "top": monitor["top"] + y,
                    "left": monitor["left"] + x,
                    "width": width,
                    "height": height
                }
                
                output = sct.grab(region)

                base, ext = os.path.splitext(output_filename)
                timestamp = int(time.time())
                timestamped_name = f"{base}_{timestamp}{ext}"

                output_path = os.path.join(self._save_dir, timestamped_name)
                mss.tools.to_png(output.rgb, output.size, output=output_path)

                latest_path = os.path.join(self._save_dir, output_filename)
                mss.tools.to_png(output.rgb, output.size, output=latest_path)

                logger.debug("Captured region to %s", output_path)
                
                self.cleanup()
                return latest_path

        except Exception as e:
            logger.error("Failed to capture screen region: %s", e)
            raise e

    def cleanup(self, max_files: int = 10) -> None:
        """
        Cleans up old timestamped screenshots to prevent disk space bloat.
        Keeps only the most recent `max_files` images.
        """
        try:
            files = []
            for filename in os.listdir(self._save_dir):
                if filename.endswith(".png") and "screenshot" not in filename and "region" not in filename:
                    pass # We only want to sort the timestamped ones
                
                # Gather all timestamped files
                if filename.endswith(".png") and ("_" in filename):
                    filepath = os.path.join(self._save_dir, filename)
                    if os.path.isfile(filepath):
                        files.append((filepath, os.path.getmtime(filepath)))
            
            # Sort by modification time, newest first
            files.sort(key=lambda x: x[1], reverse=True)
            
            # Delete older files
            if len(files) > max_files:
                for file_path, _ in files[max_files:]:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
        except Exception as e:
            logger.debug("Failed to cleanup old screenshots: %s", e)
