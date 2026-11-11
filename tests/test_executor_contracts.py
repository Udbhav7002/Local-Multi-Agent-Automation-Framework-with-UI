import importlib
import inspect
import os

# Assuming plugins are in plugins/ directory
PLUGIN_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins")

def test_all_plugins_conform_to_contract():
    """Contract test: Ensure all python files in plugins/ correctly implement PluginExecutor."""
    if not os.path.exists(PLUGIN_DIR):
        return

    for filename in os.listdir(PLUGIN_DIR):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = f"plugins.{filename[:-3]}"
            module = importlib.import_module(module_name)

            plugin_classes = []
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Check if it implements execute (the core of PluginExecutor)
                # Ensure it's not the Protocol itself
                if hasattr(obj, "execute") and hasattr(obj, "ACTIONS") and name != "PluginExecutor":
                    plugin_classes.append(obj)

            for cls in plugin_classes:
                # Ensure the class signature matches the protocol
                assert hasattr(cls, "PLUGIN_NAME"), f"{cls.__name__} missing PLUGIN_NAME"
                assert hasattr(cls, "ACTIONS"), f"{cls.__name__} missing ACTIONS"
                assert hasattr(cls, "execute"), f"{cls.__name__} missing execute"

                # Check signature of execute
                sig = inspect.signature(cls.execute)
                assert "action" in sig.parameters, f"{cls.__name__}.execute must take 'action'"
                assert "target" in sig.parameters, f"{cls.__name__}.execute must take 'target'"
