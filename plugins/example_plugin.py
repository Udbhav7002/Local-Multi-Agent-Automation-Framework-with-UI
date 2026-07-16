"""
Example executor plugin for the Multi-Agent Automation Framework.
Place this file in the plugins/ directory to extend the framework with custom actions.

This plugin demonstrates how to add custom actions that can be invoked by the Worker agent.
"""
import asyncio
from typing import Any, Dict, List, Tuple
from core.executor.base import BaseExecutor


class ExamplePlugin:
    """
    Example plugin that adds custom actions for demonstration purposes.
    
    To use this plugin:
    1. Place this file in the plugins/ directory
    2. Restart the framework
    3. The Worker can now use actions like "custom_greet" and "custom_math"
    """
    
    # Required: The name of this plugin (for logging)
    PLUGIN_NAME = "ExamplePlugin"
    
    # Required: List of action names this plugin handles
    ACTIONS = ["custom_greet", "custom_math", "custom_echo"]
    
    def __init__(self) -> None:
        pass
    
    async def execute(self, action: str, target: str) -> Tuple[bool, str]:
        """
        Execute a custom action.
        
        Args:
            action: The action name (e.g., "custom_greet")
            target: The target parameter (e.g., "Alice" for greet)
            
        Returns:
            Tuple of (success: bool, output: str)
        """
        try:
            if action == "custom_greet":
                return await self._greet(target)
            elif action == "custom_math":
                return await self._math(target)
            elif action == "custom_echo":
                return await self._echo(target)
            else:
                return False, f"Unknown action: {action}"
        except Exception as e:
            return False, f"Plugin error: {str(e)}"
    
    async def _greet(self, name: str) -> Tuple[bool, str]:
        """Custom greeting action."""
        return True, f"Hello, {name}! This is a custom plugin action."
    
    async def _math(self, expression: str) -> Tuple[bool, str]:
        """Evaluate a simple math expression safely."""
        try:
            # Safe math evaluation using ast.literal_eval for numbers and basic operators
            import ast
            import operator
            
            # Only allow basic arithmetic
            allowed_operators = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Pow: operator.pow,
                ast.USub: operator.neg,
                ast.UAdd: operator.pos,
            }
            
            def eval_node(node):
                if isinstance(node, ast.Constant):
                    return node.value
                elif isinstance(node, ast.BinOp):
                    left = eval_node(node.left)
                    right = eval_node(node.right)
                    op_type = type(node.op)
                    if op_type in allowed_operators:
                        return allowed_operators[op_type](left, right)
                    raise ValueError(f"Unsupported operator: {op_type}")
                elif isinstance(node, ast.UnaryOp):
                    operand = eval_node(node.operand)
                    op_type = type(node.op)
                    if op_type in allowed_operators:
                        return allowed_operators[op_type](operand)
                    raise ValueError(f"Unsupported unary operator: {op_type}")
                else:
                    raise ValueError(f"Unsupported expression type: {type(node)}")
            
            tree = ast.parse(expression, mode='eval')
            result = eval_node(tree.body)
            return True, f"Result: {result}"
        except Exception as e:
            return False, f"Math error: {str(e)}"
    
    async def _echo(self, text: str) -> Tuple[bool, str]:
        """Echo back the input text."""
        return True, f"Echo: {text}"


# The framework auto-discovers classes with PLUGIN_NAME and ACTIONS attributes
# No additional registration needed!