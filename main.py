"""
Main entry point for the Local Multi-Agent Automation Framework.
Pure Terminal/CLI implementation with rich interactive dashboard.
"""
# pylint: disable=broad-exception-caught, line-too-long

import asyncio
import sys
import argparse
import signal
import os
import sqlite3
import platform
import json
import urllib.request
import re

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
from rich.panel import Panel
from rich import box
from rich.columns import Columns
from rich.align import Align

from core.config import config
from core.factory import FrameworkBuilder
from core.orchestrator import Orchestrator
from core.health_check import check_dependencies
from core.logger import setup_logger, console
from core.voice import VoiceInput

logger = setup_logger("Main")

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_JOBS_DB_PATH = os.path.join(_PROJECT_ROOT, "jobs.db")


def _get_ollama_status() -> tuple[bool, str]:
    """Check if Ollama server is responsive."""
    try:
        url = f"{config.ollama_base_url.rstrip('/')}/api/tags"
        req = urllib.request.Request(url, headers={"User-Agent": "LocalAgent/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                models = len(data.get("models", []))
                return True, f"Online ({models} local models available)"
    except Exception:
        pass
    return False, "Offline (http://localhost:11434 unreachable)"


def draw_splash_screen(router_model: str, planner_model: str, vision_model: str) -> None:
    """Draws a premium, practical terminal dashboard on startup."""

    ascii_art = """[bold cyan]
  ███████ ████████  █████  ██████  ████████ 
  ██         ██    ██   ██ ██   ██    ██    
  ███████    ██    ███████ ██████     ██    
       ██    ██    ██   ██ ██   ██    ██    
  ███████    ██    ██   ██ ██   ██    ██    
[/bold cyan]"""

    console.print(ascii_art)
    
    ollama_ok, ollama_msg = _get_ollama_status()
    status_pill = "[bold green]● SYSTEM READY[/bold green]" if ollama_ok else "[bold yellow]⚠ OLLAMA OFFLINE[/bold yellow]"
    os_name = f"{platform.system()} ({platform.machine()})"
    
    status_bar = f"  {status_pill}   |   [bold white]OS:[/bold white] {os_name}   |   [bold white]Ollama:[/bold white] {ollama_msg}"
    console.print(status_bar)
    console.print("  [#444444]" + "─" * 70 + "[/#444444]\n")

    # Left table: Active Models
    models_table = Table(title="🤖 Active Agent Army", box=box.ROUNDED, border_style="cyan", padding=(0, 2))
    models_table.add_column("Agent Role", style="bold white", width=14)
    models_table.add_column("Model Name", style="bold green")
    models_table.add_row("🧠 Manager", planner_model)
    models_table.add_row("⚡ Worker", config.worker_model)
    models_table.add_row("👀 Vision", vision_model)
    models_table.add_row("🧐 Critic", config.critic_model)

    # Right table: Slash Commands
    commands_table = Table(title="⚡ Quick Commands", box=box.ROUNDED, border_style="blue", padding=(0, 2))
    commands_table.add_column("Command", style="bold yellow", width=12)
    commands_table.add_column("Action", style="white")
    commands_table.add_row("/help", "Show detailed command guide")
    commands_table.add_row("/status", "Live system & health dashboard")
    commands_table.add_row("/skills", "View cached reusable skill plans")
    commands_table.add_row("/jobs", "Inspect background API jobs")
    commands_table.add_row("/cost", "Cloud vision cost summary")
    commands_table.add_row("/consent", "Cloud vision consent/settings")
    commands_table.add_row("/model", "Swap local LLM models on the fly")
    commands_table.add_row("/history", "View session task history")
    commands_table.add_row("/clear", "Reset & clear terminal display")
    commands_table.add_row("/quit | /stop", "Exit the framework cleanly")

    console.print(Columns([models_table, commands_table], padding=(0, 4)))
    console.print()

    # Practical Examples Box
    examples_text = (
        "[bold cyan]1.[/bold cyan] \"Open Safari and search for Tokyo weather forecast\"\n"
        "[bold cyan]2.[/bold cyan] \"Take a screenshot and summarize visible text on screen\"\n"
        "[bold cyan]3.[/bold cyan] \"Open Terminal, check disk space, and report available GB\"\n"
        "[bold cyan]4.[/bold cyan] \"List top 5 running processes by CPU usage and explain\""
    )
    console.print(Panel(
        examples_text,
        title="[bold green]💡 Try These Practical Commands[/bold green]",
        border_style="green",
        padding=(1, 2)
    ))
    console.print()


def _show_status(orchestrator: Orchestrator) -> None:
    """Displays a comprehensive diagnostic dashboard in the terminal."""
    ollama_ok, ollama_msg = _get_ollama_status()
    os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
    
    # Check Jobs DB stats
    total_jobs, completed_jobs, failed_jobs = 0, 0, 0
    if os.path.exists(_JOBS_DB_PATH):
        try:
            with sqlite3.connect(_JOBS_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM jobs")
                total_jobs = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM jobs WHERE status = 'COMPLETED'")
                completed_jobs = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM jobs WHERE status = 'FAILED'")
                failed_jobs = cursor.fetchone()[0]
        except Exception:
            pass

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 3))
    table.add_column("Metric", style="bold white", width=22)
    table.add_column("Value")
    table.add_row("Operating System", os_info)
    table.add_row("Ollama Connection", f"[green]{ollama_msg}[/green]" if ollama_ok else f"[red]{ollama_msg}[/red]")
    table.add_row("Manager Model", f"[cyan]{orchestrator.planner.model_name}[/cyan]")
    table.add_row("Worker Model", f"[cyan]{orchestrator.worker.model_name}[/cyan]")
    table.add_row("Vision Model", f"[cyan]{config.vision_model}[/cyan]")
    table.add_row("Critic Model", f"[cyan]{orchestrator.critic.model_name}[/cyan]")
    table.add_row("SQLite Job Tracker", f"{total_jobs} total jobs ({completed_jobs} completed, {failed_jobs} failed)")
    table.add_row("Session History", f"{len(orchestrator._conversation_history)} tasks in current session")

    console.print(Panel(table, title="[bold cyan]📊 System Status & Health Dashboard[/bold cyan]", border_style="cyan", padding=(1, 2)))
    console.print()


def _show_skills(orchestrator: Orchestrator) -> None:
    """Displays cached reusable skills in a Rich table."""
    table = Table(title="🧠 Reusable Learned Skills (SkillLibrary)", box=box.ROUNDED, border_style="magenta", padding=(0, 2))
    table.add_column("#", style="bold white", width=4)
    table.add_column("Task Pattern", style="bold cyan")
    table.add_column("Steps", style="green", width=10)
    table.add_column("Failures", style="yellow", width=10)

    try:
        skills_cache = getattr(orchestrator.skill_library, "_cache", {})
        if not skills_cache:
            console.print("  [#888888]No reusable skills cached yet. Complete successful tasks to automatically build skills![/#888888]\n")
            return
        idx = 1
        for task, data in skills_cache.items():
            plan_steps = data.get("plan", [])
            failures = data.get("failures", 0)
            table.add_row(str(idx), task, str(len(plan_steps)), str(failures))
            idx += 1
        console.print(table)
        console.print()
    except Exception as e:
        console.print(f"  [red]Error reading skill library: {e}[/red]\n")


def _show_jobs() -> None:
    """Displays recent background API jobs from SQLite jobs.db."""
    if not os.path.exists(_JOBS_DB_PATH):
        console.print("  [#888888]No jobs database found yet. Run tasks via API or './start.sh --api' to record jobs.[/#888888]\n")
        return

    table = Table(title="📋 Recent Background API Jobs (jobs.db)", box=box.ROUNDED, border_style="blue", padding=(0, 2))
    table.add_column("Job ID", style="bold yellow", width=10)
    table.add_column("Status", style="bold")
    table.add_column("Created At", style="dim", width=20)
    table.add_column("Result Summary", style="white")

    try:
        with sqlite3.connect(_JOBS_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 10").fetchall()
            if not rows:
                console.print("  [#888888]No jobs recorded yet.[/#888888]\n")
                return
            for row in rows:
                status = row["status"]
                style = "green" if status == "COMPLETED" else ("yellow" if status == "RUNNING" else ("red" if status == "FAILED" else "blue"))
                result_str = (row["result"] or "")[:60]
                if len(row["result"] or "") > 60:
                    result_str += "..."
                table.add_row(row["job_id"][:8], f"[{style}]{status}[/{style}]", (row["created_at"] or "")[:19].replace("T", " "), result_str)
        console.print(table)
        console.print()
    except Exception as e:
        console.print(f"  [red]Error querying jobs.db: {e}[/red]\n")


def _show_history(orchestrator: Orchestrator) -> None:
    """Displays current session task history."""
    history = getattr(orchestrator, "_conversation_history", [])
    if not history:
        console.print("  [#888888]No tasks executed in the current session yet.[/#888888]\n")
        return

    table = Table(title="📜 Current Session Task History", box=box.ROUNDED, border_style="green", padding=(0, 2))
    table.add_column("#", style="bold white", width=4)
    table.add_column("Prompt / Command", style="bold cyan")
    table.add_column("Outcome", style="white")

    for idx, item in enumerate(history, 1):
        table.add_row(str(idx), str(item.get("prompt", "")), str(item.get("outcome", "")))
    console.print(table)
    console.print()


def _handle_model_command(orchestrator: Orchestrator, parts: list[str]) -> None:
    """Handles the /model CLI command to swap AI models on the fly."""
    if len(parts) == 1:
        table = Table(title="🤖 Active Agent Models", box=box.ROUNDED, border_style="cyan", padding=(0, 3))
        table.add_column("Agent", style="bold white", width=15)
        table.add_column("Model Name", style="bold green")
        table.add_row("Manager", orchestrator.planner.model_name)
        table.add_row("Worker", orchestrator.worker.model_name)
        table.add_row("Vision", config.vision_model)
        table.add_row("Critic", orchestrator.critic.model_name)
        console.print(table)
        console.print("  [#888888]Usage: /model [manager|worker|vision|critic] [new_model][/#888888]\n")
    elif len(parts) >= 3:
        target_agent = parts[1].lower()
        new_model = parts[2]

        if target_agent == 'manager':
            orchestrator.router.model_name = new_model
            orchestrator.planner.model_name = new_model
            orchestrator.critic.model_name = new_model
            config.manager_model = new_model
            config.save()
            console.print(f"  [#00ff00]✓[/#00ff00] [#888888]Manager models changed to[/#888888] [bold #ffffff]{new_model}[/bold #ffffff]")
        elif target_agent == 'worker':
            orchestrator.worker.model_name = new_model
            config.worker_model = new_model
            config.save()
            console.print(f"  [#00ff00]✓[/#00ff00] [#888888]Worker model changed to[/#888888] [bold #ffffff]{new_model}[/bold #ffffff]")
        elif target_agent == 'vision':
            config.vision_model = new_model
            config.save()
            console.print(f"  [#00ff00]✓[/#00ff00] [#888888]Vision model changed to[/#888888] [bold #ffffff]{new_model}[/bold #ffffff]")
        elif target_agent == 'critic':
            orchestrator.critic.model_name = new_model
            config.critic_model = new_model
            config.save()
            console.print(f"  [#00ff00]✓[/#00ff00] [#888888]Critic model changed to[/#888888] [bold #ffffff]{new_model}[/bold #ffffff]")
        else:
            console.print("  [#ff0000]x Invalid agent. Use manager, worker, vision, or critic.[/#ff0000]")
    else:
        console.print("  [#ff0000]x Usage: /model [manager|worker|vision|critic] [new_model][/#ff0000]")


def _show_cost(orchestrator: Orchestrator) -> None:
    """Displays current session cloud vision cost summary."""
    try:
        verifier = getattr(orchestrator.step_runner, 'verifier', None)
        if verifier and hasattr(verifier, 'get_cost_summary'):
            summary = verifier.get_cost_summary()
        else:
            from core.cost_tracker import get_cost_tracker
            summary = get_cost_tracker().get_session_summary()

        if summary["request_count"] == 0:
            console.print("  [#888888]No cloud vision requests in this session yet.[/#888888]\n")
            return

        table = Table(title="💰 Cloud Vision Cost Summary", box=box.ROUNDED, border_style="yellow", padding=(0, 2))
        table.add_column("Metric", style="bold white", width=28)
        table.add_column("Value", style="bold green")

        table.add_row("Total Cost", f"${summary['total_cost_usd']:.6f}")
        table.add_row("Total Tokens", f"{summary['total_tokens']:,}")
        table.add_row("  Input Tokens", f"{summary['total_input_tokens']:,}")
        table.add_row("  Output Tokens", f"{summary['total_output_tokens']:,}")
        table.add_row("Request Count", str(summary['request_count']))

        console.print(table)
        console.print()

        # By model
        if summary.get('by_model'):
            model_table = Table(title="By Model", box=box.SIMPLE, padding=(0, 2))
            model_table.add_column("Model", style="bold cyan")
            model_table.add_column("Cost", style="green")
            model_table.add_column("Input", style="white")
            model_table.add_column("Output", style="white")
            model_table.add_column("Requests", style="yellow")
            for model, data in summary['by_model'].items():
                model_table.add_row(model, f"${data['cost']:.6f}", f"{data['input']:,}", f"{data['output']:,}", str(data['count']))
            console.print(model_table)
            console.print()

        # By operation
        if summary.get('by_operation'):
            op_table = Table(title="By Operation", box=box.SIMPLE, padding=(0, 2))
            op_table.add_column("Operation", style="bold cyan")
            op_table.add_column("Cost", style="green")
            op_table.add_column("Requests", style="yellow")
            for op, data in summary['by_operation'].items():
                op_table.add_row(op, f"${data['cost']:.6f}", str(data['count']))
            console.print(op_table)
            console.print()

        # Budget status
        from core.config import config
        session_pct = (summary['total_cost_usd'] / config.max_vision_cost_per_session_usd) * 100 if config.max_vision_cost_per_session_usd > 0 else 0
        bar = "█" * int(session_pct / 5) + "░" * (20 - int(session_pct / 5))
        color = "green" if session_pct < 50 else ("yellow" if session_pct < 80 else "red")
        console.print(f"  Session Budget: [{color}]{bar}[/{color}] {session_pct:.1f}% (${summary['total_cost_usd']:.4f} / ${config.max_vision_cost_per_session_usd:.2f})")
        console.print()

    except Exception as e:
        console.print(f"  [red]Error getting cost summary: {e}[/red]\n")


def _handle_consent(orchestrator: Orchestrator, user_text: str) -> None:
    """Handles /consent command for cloud vision."""
    parts = user_text.split()
    if len(parts) == 1:
        console.print(f"  Cloud Vision Enabled: {'[green]Yes[/green]' if config.cloud_vision_enabled else '[red]No[/red]'}")
        console.print(f"  Consent Given: {'[green]Yes[/green]' if config.cloud_vision_consent_given else '[red]No[/red]'}")
        console.print(f"  Session Budget: ${config.max_vision_cost_per_session_usd:.2f}")
        console.print(f"  Per-Request Limit: ${config.max_vision_cost_per_request_usd:.4f}")
        console.print("  Usage: /consent grant | revoke | enable | disable")
        console.print()
        return

    action = parts[1].lower()
    if action == 'grant':
        config.cloud_vision_consent_given = True
        config.save()
        console.print("  [green]✓[/green] Cloud vision consent granted.")
    elif action == 'revoke':
        config.cloud_vision_consent_given = False
        config.save()
        console.print("  [yellow]⚠[/yellow] Cloud vision consent revoked.")
    elif action == 'enable':
        config.cloud_vision_enabled = True
        config.save()
        console.print("  [green]✓[/green] Cloud vision enabled.")
    elif action == 'disable':
        config.cloud_vision_enabled = False
        config.save()
        console.print("  [yellow]⚠[/yellow] Cloud vision disabled.")
    else:
        console.print("  [red]x Usage: /consent grant | revoke | enable | disable[/red]")
    console.print()


async def async_main(args: argparse.Namespace) -> None:
    """
    Asynchronous main loop.
    This is the COMPOSITION ROOT — the only place where concrete
    implementations are wired to their abstract interfaces.
    """
    if not check_dependencies():
        logger.critical("Critical dependencies missing - aborting launch")
        sys.exit(1)

    orchestrator = FrameworkBuilder.build_orchestrator()
    console.clear()

    draw_splash_screen(orchestrator.router.model_name, orchestrator.planner.model_name, config.vision_model)
    
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        console.print("\n  [#888888]Shutdown signal received...[/#888888]")
        shutdown_event.set()

    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, signal_handler)
        loop.add_signal_handler(signal.SIGTERM, signal_handler)

    async def input_loop():
        while not shutdown_event.is_set():
            try:
                user_text = (
                    await asyncio.to_thread(
                        Prompt.ask, "\n[bold cyan]agent[/bold cyan] [dim]❯[/dim]"
                    )
                ).strip()
    
                if not user_text:
                    continue
                
                # Natural Language Model Swap: "use llama3 for/to check the weather"
                nlp_model_match = re.match(r'^(?:use|change(?: model)? to)\s+(?:this\s+)?(?:model\s+)?([a-zA-Z0-9\.\-:]+)(?:\s+(?:for|to)\s+(.+))?$', user_text, re.IGNORECASE)
                if nlp_model_match:
                    new_model = nlp_model_match.group(1)
                    extracted_task = nlp_model_match.group(2).strip() if nlp_model_match.group(2) else ""
                    
                    console.clear()
                    
                    if extracted_task.lower() in ["manager and worker", "manager", "worker", "vision", "critic", "all"]:
                        if "manager" in extracted_task.lower() or "all" in extracted_task.lower():
                            orchestrator.router.model_name = new_model
                            orchestrator.planner.model_name = new_model
                            config.manager_model = new_model
                        if "worker" in extracted_task.lower() or "all" in extracted_task.lower():
                            orchestrator.worker.model_name = new_model
                            config.worker_model = new_model
                        if "vision" in extracted_task.lower() or "all" in extracted_task.lower():
                            config.vision_model = new_model
                        if "critic" in extracted_task.lower() or "all" in extracted_task.lower():
                            orchestrator.critic.model_name = new_model
                            config.critic_model = new_model
                        config.save()
                        draw_splash_screen(orchestrator.router.model_name, orchestrator.planner.model_name, config.vision_model)
                        console.print(f"\n  [#00ff00]✓[/#00ff00] [#888888]Auto-switched models to:[/#888888] [bold cyan]{new_model}[/bold cyan]")
                        continue
                    else:
                        orchestrator.router.model_name = new_model
                        orchestrator.planner.model_name = new_model
                        orchestrator.critic.model_name = new_model
                        config.manager_model = new_model
                        orchestrator.worker.model_name = new_model
                        config.worker_model = new_model
                        config.save()
                        
                        draw_splash_screen(orchestrator.router.model_name, orchestrator.planner.model_name, config.vision_model)
                        console.print(f"\n  [#00ff00]✓[/#00ff00] [#888888]Auto-switched models to:[/#888888] [bold cyan]{new_model}[/bold cyan]")
                        
                        if extracted_task:
                            user_text = extracted_task
                            console.print(f"  [#888888]Proceeding with task:[/#888888] {user_text}\n")
                        else:
                            continue

                if user_text.lower() in ['quit', 'exit', '/quit', '/exit', 'stop', '/stop', './stop.sh', 'stop.sh', 'q']:
                    console.print("\n  [#888888]Shutting down cleanly...[/#888888]")
                    if hasattr(orchestrator.step_runner, "executor"):
                        await orchestrator.step_runner.executor.shutdown()
                    break
    
                if user_text.lower() == '/help':
                    help_table = Table(title="⚡ Available Commands & Shortcuts", box=box.ROUNDED, border_style="blue", padding=(0, 2))
                    help_table.add_column("Command", style="bold yellow", width=14)
                    help_table.add_column("Description", style="white")
                    help_table.add_row("/help", "Show this help table")
                    help_table.add_row("/status", "Display system health, Ollama status, and database metrics")
                    help_table.add_row("/skills", "View reusable skills learned in SkillLibrary")
                    help_table.add_row("/jobs", "Inspect recent background API jobs from sqlite")
                    help_table.add_row("/history", "Show task history in current session")
                    help_table.add_row("/cost", "Show cloud vision cost summary")
                    help_table.add_row("/consent", "Manage cloud vision consent & settings")
                    help_table.add_row("/model", "Swap models on the fly (e.g., /model worker qwen2.5-coder:14b)")
                    help_table.add_row("/voice", "Dictate task using voice recognition")
                    help_table.add_row("/clear", "Clear terminal and re-draw dashboard")
                    help_table.add_row("/save", "Persist session state")
                    help_table.add_row("/quit | /stop", "Exit the framework cleanly")
                    console.print(help_table)
                    console.print()
                    continue
    
                if user_text.lower() == '/status':
                    _show_status(orchestrator)
                    continue

                if user_text.lower() == '/skills':
                    _show_skills(orchestrator)
                    continue

                if user_text.lower() == '/jobs':
                    _show_jobs()
                    continue

                if user_text.lower() == '/history':
                    _show_history(orchestrator)
                    continue

                if user_text.lower() == '/clear':
                    console.clear()
                    draw_splash_screen(orchestrator.router.model_name, orchestrator.planner.model_name, config.vision_model)
                    continue
     
                if user_text.lower() == '/save':
                    console.print("  [#00ff00]✓[/#00ff00] [#888888]Session state saved.[/#888888]")
                    continue
     
                if user_text.lower() == '/cost':
                    _show_cost(orchestrator)
                    continue

                if user_text.lower().startswith('/consent'):
                    _handle_consent(orchestrator, user_text)
                    continue
     
                if user_text.lower().startswith('/model'):
                    parts = user_text.split()
                    _handle_model_command(orchestrator, parts)
                    continue
    
                if user_text.lower() == '/voice':
                    voice_input = VoiceInput()
                    user_text = await asyncio.to_thread(voice_input.listen)
                    if not user_text:
                        continue
                    console.print(f"  [bold white]You said:[/bold white] {user_text}")
    
                await orchestrator.process_prompt(user_text)
    
            except (KeyboardInterrupt, EOFError):
                shutdown_event.set()
            except Exception as e:
                logger.error("System Error: %s", e)
    
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
