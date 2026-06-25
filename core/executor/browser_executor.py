"""
Browser execution strategy — Playwright-based DOM automation with persistent context.
"""
# pylint: disable=broad-exception-caught
import os
from typing import Any, Optional, Tuple

from core.logger import setup_logger

logger = setup_logger("BrowserExecutor")


class BrowserExecutor:
    """
    Manages a Playwright browser lifecycle and executes DOM-level actions
    (goto, click_dom, type_dom) with smart URL detection and error recovery.
    """

    def __init__(self) -> None:
        self._pw: Any = None
        self._browser: Any = None
        self._page: Any = None

    async def __aenter__(self):
        await self._init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def _get_browser_path(browser_name: str) -> Optional[str]:
        """Dynamically finds the browser executable path across OSes."""
        import sys
        import shutil
        import os
        
        b_name = browser_name.lower()
        
        # Windows
        if sys.platform == 'win32':
            if b_name == 'brave':
                path = os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe")
                return path if os.path.exists(path) else None
            elif b_name == 'chrome':
                path = os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe")
                return path if os.path.exists(path) else None
                
        # macOS
        elif sys.platform == 'darwin':
            if b_name == 'brave':
                path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
                return path if os.path.exists(path) else None
            elif b_name == 'chrome':
                path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                return path if os.path.exists(path) else None
                
        # Linux
        elif sys.platform.startswith('linux'):
            if b_name == 'brave':
                return shutil.which('brave-browser') or shutil.which('brave')
            elif b_name == 'chrome':
                return shutil.which('google-chrome') or shutil.which('chrome')
                
        return None

    async def _init_browser(self) -> None:
        """Lazily initialize Playwright and launch a persistent browser context."""
        if not self._pw:
            try:
                from playwright.async_api import async_playwright  # pylint: disable=import-outside-toplevel

                self._pw = await async_playwright().start()

                # __file__ is core/executor/browser_executor.py, so 3 levels up
                _project_root = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
                profile_dir = os.path.join(_project_root, "browser_profile")
                if not os.path.exists(profile_dir):
                    os.makedirs(profile_dir)

                brave_path = self._get_browser_path("brave")
                if brave_path and os.path.exists(brave_path):
                    logger.info("Launching Brave Browser with Persistent Context...")
                    self._browser = await self._pw.chromium.launch_persistent_context(
                        user_data_dir=profile_dir,
                        headless=False,
                        executable_path=brave_path,
                        no_viewport=True,
                    )
                else:
                    logger.info("Brave not found. Launching default Chromium with Persistent Context...")
                    self._browser = await self._pw.chromium.launch_persistent_context(
                        user_data_dir=profile_dir,
                        headless=False,
                        no_viewport=True,
                    )

                if self._browser.pages:
                    self._page = self._browser.pages[0]
                else:
                    self._page = await self._browser.new_page()
            except (ImportError, OSError, RuntimeError) as e:
                logger.error("Failed to initialize browser: %s", e)
                raise

    async def shutdown(self) -> None:
        """Shuts down the Playwright browser and stops the engine."""
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
            logger.debug("Browser shutdown successful.")
        except (OSError, RuntimeError) as e:
            logger.error("Error during browser shutdown: %s", e)
        finally:
            self._pw = None
            self._browser = None
            self._page = None

    # ------------------------------------------------------------------
    # Strategy interface
    # ------------------------------------------------------------------

    async def execute(self, action: str, target: str) -> Tuple[bool, str]:
        """Execute a browser action (goto, click_dom, type_dom)."""
        return await self._execute_browser(action, target, retry=True)

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    async def _execute_browser(
        self, action: str, target: str, retry: bool = True
    ) -> Tuple[bool, str]:
        """Executes a browser action directly in the DOM using Playwright."""
        try:
            await self._init_browser()

            if not self._page:
                return False, "Browser page not initialized."

            if action == "goto":
                return await self._handle_goto(target)

            if action == "click_dom":
                logger.info("Browser Click DOM: '%s'", target)
                await self._page.click(target, timeout=10000)
                return True, f"Clicked element matching '{target}'."

            if action == "type_dom":
                if ":::" not in target:
                    return False, "Target for type_dom must be in format 'selector:::text'."
                selector, text = target.split(":::", 1)
                logger.info("Browser Type DOM: '%s' into '%s'", text, selector)
                await self._page.fill(selector, text, timeout=10000)
                return True, f"Typed text into '{selector}'."

            logger.warning("Unsupported browser action: %s", action)
            return False, f"Unsupported browser action: {action}"

        except (ValueError, TypeError, OSError) as e:
            err_str = str(e)
            logger.error("Browser execution failed: %s", err_str)
            if retry and (
                "Connection closed" in err_str
                or "Target closed" in err_str
                or "has been closed" in err_str
            ):
                logger.warning("Connection dead. Restarting Playwright instance...")
                await self.shutdown()
                return await self._execute_browser(action, target, retry=False)
            return False, f"Browser execution failed: {err_str}"

    async def _handle_goto(self, target: str) -> Tuple[bool, str]:
        """Navigate to a URL with smart URL detection and DuckDuckGo fallback."""
        import re as _re  # pylint: disable=import-outside-toplevel

        if not target:
            target = "https://google.com"
        if not target.startswith("http"):
            target = "https://" + target

        # Smart URL detection
        url_body = target.replace("https://", "").replace("http://", "")
        if " " in url_body or not _re.match(r'^[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}', url_body):
            search_query = url_body.replace("/", " ").strip()
            target = f"https://duckduckgo.com/?q={search_query}"
            logger.info("Target doesn't look like a URL. Searching DuckDuckGo for: %s", search_query)

        logger.info("Browser Navigating: %s", target)
        try:
            await self._page.goto(target, wait_until="load")
            return True, f"Navigated to {target}."
        except (ValueError, TypeError, OSError) as e:
            if "ERR_NAME_NOT_RESOLVED" in str(e) or "ERR_CONNECTION_REFUSED" in str(e):
                logger.warning("Domain not resolved. Falling back to DuckDuckGo Search...")
                search_query = target.replace("https://", "").replace("http://", "").replace("/", " ")
                search_url = f"https://duckduckgo.com/?q={search_query}"
                await self._page.goto(search_url, wait_until="load")
                return True, f"Could not resolve {target}. Executed a DuckDuckGo search instead."
            raise
