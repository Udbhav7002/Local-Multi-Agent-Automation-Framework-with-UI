# Executor Plugins

Drop a `.py` file into this directory and it will be automatically discovered and loaded by the framework at startup.

## How to Write a Plugin

Each plugin file must define a class with:
1. An `async def execute(self, action: str, target: str) -> tuple[bool, str]` method
2. A `PLUGIN_NAME: str` class attribute (used for logging)
3. An `ACTIONS: list[str]` class attribute listing the action names it handles

### Example: `spotify_plugin.py`

```python
from core.executor.base import BaseExecutor

class SpotifyExecutor(BaseExecutor):
    PLUGIN_NAME = "spotify"
    ACTIONS = ["play_music", "pause_music", "next_track"]

    async def execute(self, action: str, target: str) -> tuple[bool, str]:
        import subprocess
        if action == "play_music":
            script = f'tell application "Spotify" to play track "{target}"'
            subprocess.run(["osascript", "-e", script], check=False)
            return True, f"Playing {target} on Spotify"
        if action == "pause_music":
            subprocess.run(["osascript", "-e", 'tell application "Spotify" to pause'], check=False)
            return True, "Paused Spotify"
        return False, f"Unknown spotify action: {action}"
```

### How it works

1. On startup, `ExecutorDispatcher._load_plugins()` scans this directory.
2. For each `.py` file, it imports the module and looks for classes with an `execute` method.
3. If the class has an `ACTIONS` list, each action name is registered as a route.
4. When the Worker produces a step with a matching action, the plugin handles it automatically.

### Notes
- Plugin classes are instantiated with no arguments. If you need constructor args, override `__init__`.
- Plugins can optionally define `async def shutdown(self)` for cleanup.
- The framework logs which plugins are loaded at startup.
