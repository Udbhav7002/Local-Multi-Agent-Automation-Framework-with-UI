"""
ExecutorDispatcher — routes each ActionStep to the correct strategy executor.
Includes the SystemExecutor for sleep/open_app/close_browser actions.
Supports auto-discovery of plugins from the plugins/ directory.
"""
import asyncio
import importlib.util
import inspect
import os
import traceback
from typing import Any, Dict, Tuple, Union

from core.logger import setup_logger
from core.models import ActionStep, MethodType
from core.config import config

from .base import BaseExecutor

logger = setup_logger("ExecutorDispatcher")


class SystemExecutor:
    """
    Handles system-level actions (sleep, close_browser, open_app)
    that don't fit into CLI/GUI/Browser strategies.
    """

    def __init__(self, cli_executor: BaseExecutor, browser_executor: Any) -> None:
        self._cli = cli_executor
        self._browser = browser_executor

    async def execute(self, action: str, target: str) -> Tuple[bool, str]:
        """Execute a system-level action."""
        if action == "sleep":
            try:
                duration = float(target)
            except (ValueError, TypeError):
                logger.warning(
                    "Could not parse sleep duration '%s', defaulting to 5s.", target
                )
                duration = 5.0
            logger.info("System sleeping for %s seconds...", duration)
            await asyncio.sleep(duration)
            return True, f"Slept for {duration} seconds."

        if action == "close_browser":
            logger.info("Closing browser...")
            await self._browser.shutdown()
            return True, "Closed the browser."

        if action == "open_app":
            app_name = os.path.basename(target)
            if app_name.lower().endswith('.app') or app_name.lower().endswith('.exe'):
                app_name = os.path.splitext(app_name)[0]

            logger.info("Opening application: %s...", app_name)
            
            import platform
            system = platform.system()
            if system == "Darwin":
                cmd = f'open -a "{app_name}"'
            elif system == "Windows":
                cmd = f'start "" "{app_name}"'
            else: # Linux
                cmd = f'gtk-launch "{app_name}" || xdg-open "{app_name}"'
                
            return await self._cli.execute("run_command", cmd)

        error_msg = f"Unknown system action: {action}"
        logger.warning(error_msg)
        return False, error_msg


class ExecutorDispatcher:
    """
    Central dispatcher that routes each step to the appropriate strategy
    executor based on the step's method field.

    Backward compatible: ``Executor(ui_parser)`` still works.
    """

    def __init__(
        self,
        ui_parser: Any = None,
        *,
        strategies: Dict[MethodType, BaseExecutor] | None = None,
    ) -> None:
        if strategies is not None:
            self._strategies: Dict[MethodType, Any] = dict(strategies)
        else:
            # Build default strategies — matches original Executor(ui_parser) API
            from .cli_executor import CLIExecutor  # pylint: disable=import-outside-toplevel
            from .gui_executor import GUIExecutor  # pylint: disable=import-outside-toplevel
            from .browser_executor import BrowserExecutor  # pylint: disable=import-outside-toplevel

            cli = CLIExecutor()
            browser = BrowserExecutor()
            gui = GUIExecutor(ui_parser=ui_parser)
            system = SystemExecutor(cli_executor=cli, browser_executor=browser)

            self._strategies = {
                MethodType.CLI: cli,
                MethodType.GUI: gui,
                MethodType.BROWSER: browser,
                MethodType.SYSTEM: system,
            }

        # Action-based plugin registry (action_name -> plugin_instance)
        self._action_plugins: Dict[str, Any] = {}
        self._load_plugins()

    async def execute_step(
        self, step: Union[Dict[str, Any], ActionStep]
    ) -> Tuple[bool, str]:
        """
        Execute a single planned step.

        Args:
            step: Either a raw dict (backward compat) or an ActionStep dataclass.
        """
        try:
            if isinstance(step, dict):
                action_step = ActionStep.from_dict(step)
            else:
                action_step = step

            from enum import Enum
            method = action_step.method.value if isinstance(action_step.method, Enum) else action_step.method
            action = action_step.action.value if isinstance(action_step.action, Enum) else action_step.action
            target = action_step.target

            logger.debug(
                "Executing step - Action: %s, Target: %s, Method: %s",
                action, target, method,
            )

            # Check action-based plugins first
            plugin = self._action_plugins.get(action)
            
            # Fallback to standard method strategy - convert method string to MethodType enum
            try:
                method_enum = MethodType(method) if isinstance(method, str) else method
            except ValueError:
                method_enum = MethodType.CLI  # fallback
            strategy = self._strategies.get(method_enum)
            
            if plugin is None and strategy is None:
                error_msg = f"Unknown execution method: {method}"
                logger.warning(error_msg)
                return False, error_msg

            # Apply configurable timeout
            timeout = config.action_timeouts.get(action, config.cli_timeout_seconds)

            try:
                if plugin is not None:
                    return await asyncio.wait_for(plugin.execute(action, target), timeout=timeout)
                assert strategy is not None, "Strategy should not be None here"
                return await asyncio.wait_for(strategy.execute(action, target), timeout=timeout)
            except asyncio.TimeoutError:
                error_msg = f"Action '{action}' timed out after {timeout} seconds."
                logger.error(error_msg)
                return False, error_msg

        except Exception:
            err_msg = traceback.format_exc()
            logger.error("Exception during execution: %s", err_msg)
            return False, f"Exception during execution:\n{err_msg}"

    async def shutdown(self) -> None:
        """Shuts down all strategies and plugins that have a shutdown method."""
        all_executors = list(self._strategies.values()) + list(set(self._action_plugins.values()))
        for executor in all_executors:
            if hasattr(executor, 'shutdown') and callable(executor.shutdown):
                await executor.shutdown()

    def _load_plugins(self) -> None:
        """Auto-discover and register executor plugins from the plugins/ directory."""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        plugins_dir = os.path.join(project_root, "plugins")

        if not os.path.isdir(plugins_dir):
            return

        for filename in sorted(os.listdir(plugins_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            module_name = filename[:-3]
            module_path = os.path.join(plugins_dir, filename)

            try:
                spec = importlib.util.spec_from_file_location(
                    f"plugins.{module_name}", module_path
                )
                if spec is None or spec.loader is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Find classes with an execute method
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if not hasattr(obj, 'execute') or not callable(getattr(obj, 'execute')):
                        continue
                    # Skip the BaseExecutor protocol itself
                    if obj.__name__ == 'BaseExecutor':
                        continue

                    plugin_name = getattr(obj, 'PLUGIN_NAME', module_name)
                    actions = getattr(obj, 'ACTIONS', [])

                    try:
                        instance = obj()
                    except (ImportError, AttributeError, SyntaxError) as init_err:
                        logger.warning("Failed to instantiate plugin '%s': %s", plugin_name, init_err)
                        continue

                    for action_name in actions:
                        self._action_plugins[action_name] = instance

                    if actions:
                        logger.info(
                            "Loaded plugin '%s' (actions: %s)",
                            plugin_name, ", ".join(actions)
                        )

            except (ImportError, AttributeError, SyntaxError) as e:
                logger.warning("Failed to load plugin '%s': %s", filename, e)
