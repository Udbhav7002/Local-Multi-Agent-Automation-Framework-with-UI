"""
Main entry point for the Local Multi-Agent Automation Framework.
Pure Terminal/CLI implementation.
"""
# pylint: disable=broad-exception-caught, line-too-long

import asyncio
import sys
import argparse
import signal

def _hide_dock_icon():
    if sys.platform == 'darwin':
        try:
            import AppKit
            # NSApplicationActivationPolicyProhibited = 2
            # Completely hides the dock icon and menu bar for the Python process
            app = AppKit.NSApplication.sharedApplication()
            app.setActivationPolicy_(2)
        except ImportError:
            pass

from rich.prompt import Prompt
from rich.table import Table

from core.config import config
from core.factory import FrameworkBuilder
from core.orchestrator import Orchestrator
from core.health_check import check_dependencies
from core.logger import setup_logger, console
from core.voice import VoiceInput

logger = setup_logger("Main")


def draw_splash_screen(router_model: str, planner_model: str, vision_model: str) -> None:
    """Draws the ultra-minimalist 'opencode' style terminal splash screen."""

    # Blocky, solid ASCII Art
    ascii_art = """[#444444]
█      ██████  ██████  █████  
█      
█     ██    ██ ██     ██   ██ █      
█     ██    ██ ██     ███████ █      
█     ██    ██ ██     ██   ██ █      
█████  ██████   ██████ ██   ██ █████ 

 █████   ██████  ███████ ███    
██ ████████ 
██   ██ ██       ██      ████   ██    ██    
███████ ██   ███ █████   ██ ██  ██    ██    
██   ██ ██    ██ ██      ██  ██ ██    ██    
██   ██  ██████  ███████ ██   ████    ██    
[/#444444]"""

    # Print logo and status
    console.print(ascii_art)
    console.print("  [#00ff00]●[/#00ff00] [#888888]Local Agent Terminal[/#888888]\n")

    # Models table (clean, no borders, lots of padding)
    models_table = Table.grid(padding=(0, 4))
    models_table.add_column(style="bold #ffffff", width=15)
    models_table.add_column(style="#888888")

    models_table.add_row("Manager", planner_model)
    models_table.add_row("Worker", config.worker_model)
    models_table.add_row("Vision", vision_model)

    # Commands table
    commands_table = Table.grid(padding=(0, 4))
    commands_table.add_column(style="bold #ffffff", width=15)
    commands_table.add_column(style="#888888")

    commands_table.add_row("/model", "Change agent models (e.g., /model manager qwen2.5-coder:14b)")
    commands_table.add_row("/clear", "Clear the terminal screen")
    commands_table.add_row("/save", "Save current session state")
    commands_table.add_row("/quit", "Exit the framework")

    # Layout sections with headers
    console.print("  [bold #ffffff]Models[/bold #ffffff]")
    console.print("  [#444444]──────────────[/#444444]")
    console.print(models_table)
    console.print()

    console.print("  [bold #ffffff]Commands[/bold #ffffff]")
    console.print("  [#444444]──────────────[/#444444]")
    console.print(commands_table)
    console.print("\n")


def _handle_model_command(orchestrator: Orchestrator, parts: list[str]) -> None:
    """Handles the /model CLI command to swap AI models on the fly."""
    if len(parts) == 1:
        console.print("\n  [bold #ffffff]Current Models[/bold #ffffff]")
        console.print("  [#444444]──────────────[/#444444]")

        table = Table.grid(padding=(0, 4))
        table.add_column(style="bold #ffffff", width=15)
        table.add_column(style="#888888")
        table.add_row("Manager", orchestrator.planner.model_name)
        table.add_row("Worker", orchestrator.worker.model_name)
        table.add_row("Vision", config.vision_model)
        console.print(table)
        console.print("\n  [#888888]Usage: /model [manager|worker|vision] [new_model][/#888888]\n")
    elif len(parts) >= 3:
        target_agent = parts[1].lower()
        new_model = parts[2]

        if target_agent == 'manager':
            orchestrator.router.model_name = new_model
            orchestrator.planner.model_name = new_model
            orchestrator.critic.model_name = new_model
            config.manager_model = new_model
            config.save()
            console.print(f"  [#00ff00]*[/#00ff00] [#888888]Manager models changed to[/#888888] [bold #ffffff]{new_model}[/bold #ffffff]")
        elif target_agent == 'worker':
            orchestrator.worker.model_name = new_model
            config.worker_model = new_model
            config.save()
            console.print(f"  [#00ff00]*[/#00ff00] [#888888]Worker model changed to[/#888888] [bold #ffffff]{new_model}[/bold #ffffff]")
        elif target_agent == 'vision':
            config.vision_model = new_model
            config.save()
            console.print(f"  [#00ff00]*[/#00ff00] [#888888]Vision model changed to[/#888888] [bold #ffffff]{new_model}[/bold #ffffff]")
        else:
            console.print("  [#ff0000]x Invalid agent. Use manager, worker, or vision.[/#ff0000]")
    else:
        console.print("  [#ff0000]x Usage: /model [manager|worker|vision] [new_model][/#ff0000]")


async def async_main(args: argparse.Namespace) -> None:
    """
    Asynchronous main loop.
    This is the COMPOSITION ROOT — the only place where concrete
    implementations are wired to their abstract interfaces.
    """
    # Startup health check
    if not check_dependencies():
        logger.critical("Critical dependencies missing - aborting launch")
        sys.exit(1)

    # === Composition Root via Factory ===
    orchestrator = FrameworkBuilder.build_orchestrator()

    # Clear terminal before drawing to enforce the clean look
    console.clear()

    # Draw the premium splash screen
    draw_splash_screen(orchestrator.router.model_name, orchestrator.planner.model_name, config.vision_model)
    
    # Graceful shutdown handler
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        console.print("\n  [#888888]Shutdown signal received...[/#888888]")
        shutdown_event.set()

    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, signal_handler)
        loop.add_signal_handler(signal.SIGTERM, signal_handler)

    # Input loop task
    async def input_loop():
        while not shutdown_event.is_set():
            try:
                # Minimalist prompt
                user_text = Prompt.ask("[bold #ffffff]/[/bold #ffffff]").strip()
    
                if not user_text:
                    continue
                if user_text.lower() in ['quit', 'exit', '/quit']:
                    console.print("\n  [#888888]Shutting down...[/#888888]")
                    if hasattr(orchestrator.step_runner, "executor"):
                        await orchestrator.step_runner.executor.shutdown()
                    break
    
                if user_text.lower() == '/help':
                    console.print("\n  [bold #ffffff]Commands[/bold #ffffff]")
                    console.print("  [#444444]────────[/#444444]")
                    help_table = Table.grid(padding=(0, 4))
                    help_table.add_column(style="bold #ffffff", width=15)
                    help_table.add_column(style="#888888")
                    help_table.add_row("/help", "Show this message")
                    help_table.add_row("/model", "Manage AI models")
                    help_table.add_row("/voice", "Use voice to dictate a command")
                    help_table.add_row("/clear", "Clear the terminal screen")
                    help_table.add_row("/save", "Save current session state")
                    help_table.add_row("/quit", "Exit the framework")
                    console.print(help_table)
                    console.print()
                    continue
    
                if user_text.lower() == '/clear':
                    console.clear()
                    draw_splash_screen(orchestrator.router.model_name, orchestrator.planner.model_name, config.vision_model)
                    continue
    
                if user_text.lower() == '/save':
                    console.print("  [#00ff00]*[/#00ff00] [#888888]Session state saved.[/#888888]")
                    continue
    
                if user_text.lower().startswith('/model'):
                    parts = user_text.split()
                    _handle_model_command(orchestrator, parts)
                    continue
    
                if user_text.lower() == '/voice':
                    voice_input = VoiceInput()
                    user_text = voice_input.listen()
                    if not user_text:
                        continue
                    console.print(f"  [bold #ffffff]You said:[/bold #ffffff] {user_text}")
    
                await orchestrator.process_prompt(user_text)
    
            except (KeyboardInterrupt, EOFError):
                shutdown_event.set()
            except Exception as e:
                logger.error("System Error: %s", e)
    
    # Run the input loop until shutdown
    try:
        input_task = asyncio.create_task(input_loop())
        await asyncio.wait([input_task, asyncio.create_task(shutdown_event.wait())], return_when=asyncio.FIRST_COMPLETED)
    finally:
        console.print("\n  [#888888]Cleaning up resources...[/#888888]")
        if hasattr(orchestrator, "shutdown"):
            await orchestrator.shutdown()
        elif hasattr(orchestrator.step_runner, "executor"):
            await orchestrator.step_runner.executor.shutdown()
            
def main() -> None:
    """Synchronous entry point."""
    import sys  # pylint: disable=import-outside-toplevel
    import warnings  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(description="Local Multi-Agent Automation Framework (Terminal Edition)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    if args.debug:
        import os
        os.environ["DEBUG"] = "True"

    # Suppress ugly internal asyncio Proactor pipe warnings on Windows shutdown
    warnings.filterwarnings("ignore", category=ResourceWarning)

    if sys.platform == 'win32':
        try:
            from asyncio.proactor_events import _ProactorBasePipeTransport  # type: ignore
            def _silence_closed_pipe(self):  # type: ignore
                pass
            _ProactorBasePipeTransport.__del__ = _silence_closed_pipe  # type: ignore
        except Exception:
            pass

    _hide_dock_icon()

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
