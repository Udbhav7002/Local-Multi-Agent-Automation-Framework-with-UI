"""
GUI execution strategy — screen-level automation via pyautogui + OCR.
"""
# pylint: disable=broad-exception-caught
import asyncio
import platform
from typing import Any, Optional, Tuple

from core.logger import setup_logger

logger = setup_logger("GUIExecutor")


class GUIExecutor:
    """
    Executes GUI actions (click, type, hotkey, search_start_menu) using
    pyautogui for input simulation and an optional UIParser for OCR-based
    element finding.
    """

    def __init__(self, ui_parser: Optional[Any] = None) -> None:
        self.ui_parser = ui_parser

    async def execute(self, action: str, target: str) -> Tuple[bool, str]:
        """Execute a GUI action."""
        try:
            import pyautogui  # pylint: disable=import-outside-toplevel
            pyautogui.FAILSAFE = True

            if action == "type":
                logger.info("Vision Typing: '%s'", target)
                pyautogui.write(target, interval=0.05)
                pyautogui.press('enter')
                return True, f"Typed '{target}' and pressed enter."

            if action == "hotkey":
                logger.info("Vision Hotkey: '%s'", target)
                key_map = {
                    'cmd': 'command', 'command': 'command',
                    'ctrl': 'ctrl', 'control': 'ctrl',
                    'alt': 'alt', 'option': 'alt',
                    'shift': 'shift',
                    'space': 'space', 'spacebar': 'space',
                    'enter': 'enter', 'return': 'enter',
                    'del': 'delete', 'delete': 'delete',
                    'esc': 'escape', 'escape': 'escape',
                    'win': 'win', 'windows': 'win',
                }
                keys = [
                    key_map.get(k.strip().lower(), k.strip().lower())
                    for k in target.split('+')
                ]
                pyautogui.hotkey(*keys)
                return True, f"Pressed hotkey {'+'.join(keys)}."

            if action == "search_start_menu":
                logger.info("Vision Spotlight Search: '%s'", target)
                if platform.system() == "Darwin":
                    pyautogui.hotkey('command', 'space')
                else:
                    pyautogui.press('win')
                await asyncio.sleep(1.0)
                pyautogui.write(target, interval=0.05)
                await asyncio.sleep(1.0)
                pyautogui.press('enter')
                return True, f"Searched Spotlight for '{target}' and pressed enter."

            # --- Actions that require OCR coordinate finding ---
            if self.ui_parser is None:
                return False, "UI Parser not initialized for coordinate finding."

            await asyncio.sleep(0.1) # Prevent race conditions in UI thread
            coords = self.ui_parser.find_element(target)
            if not coords:
                if action == "click" and "start" in target.lower():
                    if platform.system() == "Darwin":
                        logger.info("Falling back to Command+Space for Start/Spotlight.")
                        pyautogui.hotkey('command', 'space')
                        return True, "Pressed Command+Space as fallback for Start button."
                    else:
                        logger.info("Falling back to Windows key for Start menu.")
                        pyautogui.press('win')
                        return True, "Pressed Windows key as fallback for Start button."
                logger.warning("Could not find element '%s' on screen.", target)
                return False, f"Could not find element '{target}' on screen."

            if not isinstance(coords, (list, tuple)) or len(coords) != 2:
                logger.warning("Invalid coordinates returned by UI parser: %s", coords)
                return False, f"Invalid coordinates returned for '{target}'."

            x, y = coords

            if action == "click":
                logger.info("Vision Click at (%s, %s) for '%s'", x, y, target)
                pyautogui.moveTo(x, y, duration=0.5)
                pyautogui.click()
                return True, f"Clicked on '{target}' at ({x}, {y})."

            logger.warning("Unsupported GUI action: %s", action)
            raise ValueError(f"Unsupported GUI action: {action}")

        except Exception as e:
            logger.exception("GUI Execution Error: %s", e)
            return False, f"GUI Error: {e}"
