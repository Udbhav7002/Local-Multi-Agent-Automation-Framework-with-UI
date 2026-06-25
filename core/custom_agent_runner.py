import json
from rich.panel import Panel
from core.logger import setup_logger, console
from core.agent_loader import CustomAgent

logger = setup_logger("CustomAgentRunner")

class CustomAgentRunner:
    """Executes a task via a custom YAML-defined agent."""
    def __init__(self, planner_llm, step_runner, default_model_name: str) -> None:
        self.llm = planner_llm
        self.step_runner = step_runner
        self.default_model_name = default_model_name

    async def run_custom_agent(self, user_text: str, agent: CustomAgent) -> bool:
        """Returns True if successful, False otherwise."""
        logger.info("[magenta]Custom agent '%s' generating plan...[/magenta]", agent.name)

        try:
            model = agent.model if agent.model else self.default_model_name
            prompt = f"{agent.system_prompt}\n\nUser request: {user_text}\n\nGenerate a step-by-step plan as a JSON array of objects with 'task' keys. Example: [{{'task': 'Step 1'}}, {{'task': 'Step 2'}}]"

            content = await self.llm.chat(
                model=model,
                messages=[
                    {"role": "system", "content": agent.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                format='json',
            )

            from core.response_parser import ResponseParser
            plan_json = ResponseParser.clean_and_extract_json(content, shape='array')
            steps = json.loads(plan_json)

            if not isinstance(steps, list):
                raise ValueError("Custom agent did not return a valid plan array.")

            normalized = []
            for s in steps:
                if isinstance(s, dict) and "task" in s:
                    normalized.append(s)
                else:
                    normalized.append({"task": str(s), "parallel": False})

            console.print(Panel(
                "\n".join(f"[bold]{i+1}.[/bold] {s['task']}" for i, s in enumerate(normalized)),
                title=f"[magenta]{agent.name} Plan ({len(normalized)} steps)[/magenta]",
                border_style="magenta"
            ))

            success, _, _ = await self.step_runner.run([s["task"] for s in normalized])
            if success:
                logger.info("[bold green]Custom agent '%s' completed task.[/bold green]", agent.name)
                return True
            else:
                logger.warning("[bold red]Custom agent '%s' failed.[/bold red]", agent.name)
                return False

        except Exception as e:
            logger.error("Custom agent '%s' error: %s", agent.name, e)
            return False
