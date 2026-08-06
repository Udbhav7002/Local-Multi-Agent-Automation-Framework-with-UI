import asyncio
import sys
import time
from unittest.mock import MagicMock, patch
import pytest

from core.executor.gui_executor import GUIExecutor
from core.executor.cli_executor import CLIExecutor
from core.executor.browser_executor import BrowserExecutor


class TestGUIConcurrency:
    @pytest.mark.asyncio
    async def test_gui_execution_serialized(self):
        """Verify concurrent GUIExecutor calls are serialized via GUI_LOCK."""
        mock_pyautogui = MagicMock()
        mock_pyautogui.FAILSAFE = True
        
        active_count = 0
        max_active = 0
        execution_order = []

        def mock_write(target, interval=0.05):
            nonlocal active_count, max_active
            active_count += 1
            if active_count > max_active:
                max_active = active_count
            execution_order.append(f"start_{target}")
            time.sleep(0.01)

        def mock_press(key):
            nonlocal active_count
            execution_order.append(f"end_{key}")
            active_count -= 1

        mock_pyautogui.write.side_effect = mock_write
        mock_pyautogui.press.side_effect = mock_press

        gui = GUIExecutor()

        with patch.dict(sys.modules, {"pyautogui": mock_pyautogui}):
            tasks = [gui.execute("type", f"text_{i}") for i in range(5)]
            results = await asyncio.gather(*tasks)

        assert max_active == 1, f"Expected max concurrent GUI tasks to be 1, got {max_active}"
        assert all(r[0] is True for r in results)
        assert len(execution_order) == 10

    @pytest.mark.asyncio
    async def test_cli_and_browser_executors_lock_free(self):
        """Verify CLI and Browser executors execute without acquiring GUI_LOCK."""
        gui = GUIExecutor()
        cli = CLIExecutor()
        browser = BrowserExecutor()

        assert not hasattr(cli, "lock")
        assert not hasattr(browser, "lock")

        # Acquire GUI_LOCK manually to simulate GUI task holding the lock
        async with gui.lock:
            # While GUI_LOCK is held, CLI task should run immediately without blocking
            cli_result, _ = await cli.execute("run_command", "echo hello")
            assert cli_result is True

    @pytest.mark.asyncio
    async def test_custom_lock_injection(self):
        """Verify custom lock parameter is respected."""
        custom_lock = asyncio.Lock()
        gui = GUIExecutor(lock=custom_lock)
        assert gui.lock is custom_lock

    @pytest.mark.asyncio
    async def test_shared_lock_across_gui_executor_instances(self):
        """Verify multiple GUIExecutor instances share the class-level GUI_LOCK."""
        gui1 = GUIExecutor()
        gui2 = GUIExecutor()
        assert gui1.lock is gui2.lock
        assert gui1.lock is GUIExecutor.GUI_LOCK
