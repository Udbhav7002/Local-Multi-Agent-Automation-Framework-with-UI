"""
Example tool for the Multi-Agent Automation Framework.
Tools are standalone utilities that can be invoked by agents or the framework directly.
"""
import asyncio
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: str
    metadata: Optional[Dict[str, Any]] = None


class BaseTool:
    """Base class for all tools."""
    
    name: str = "base_tool"
    description: str = "Base tool class"
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given arguments."""
        raise NotImplementedError


class FileReadTool(BaseTool):
    """Tool for reading files from the filesystem."""
    
    name = "file_read"
    description = "Read contents of a file from the filesystem"
    
    async def execute(self, path: str, encoding: str = "utf-8") -> ToolResult:
        """Read a file and return its contents."""
        try:
            import aiofiles
            async with aiofiles.open(path, mode='r', encoding=encoding) as f:
                content = await f.read()
            return ToolResult(success=True, output=content, metadata={"path": path})
        except FileNotFoundError:
            return ToolResult(success=False, output=f"File not found: {path}")
        except Exception as e:
            return ToolResult(success=False, output=f"Error reading file: {str(e)}")


class FileWriteTool(BaseTool):
    """Tool for writing files to the filesystem."""
    
    name = "file_write"
    description = "Write content to a file on the filesystem"
    
    async def execute(self, path: str, content: str, encoding: str = "utf-8") -> ToolResult:
        """Write content to a file."""
        try:
            import aiofiles
            import os
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            async with aiofiles.open(path, mode='w', encoding=encoding) as f:
                await f.write(content)
            return ToolResult(success=True, output=f"Written to {path}", metadata={"path": path, "bytes": len(content)})
        except Exception as e:
            return ToolResult(success=False, output=f"Error writing file: {str(e)}")


class WebSearchTool(BaseTool):
    """Tool for performing web searches."""
    
    name = "web_search"
    description = "Search the web using DuckDuckGo"
    
    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        """Perform a web search."""
        try:
            import aiohttp
            import urllib.parse
            
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    html = await response.text()
            
            # Simple HTML parsing for results
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            for result in soup.find_all('a', class_='result__snippet')[:max_results]:
                results.append(result.get_text(strip=True))
            
            output = "\n".join(results) if results else "No results found"
            return ToolResult(success=True, output=output, metadata={"query": query, "count": len(results)})
        except Exception as e:
            return ToolResult(success=False, output=f"Search error: {str(e)}")


class ToolRegistry:
    """Registry for managing available tools."""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """Register built-in tools."""
        self.register(FileReadTool())
        self.register(FileWriteTool())
        self.register(WebSearchTool())
    
    def register(self, tool: BaseTool):
        """Register a tool."""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute a tool by name."""
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(success=False, output=f"Tool not found: {tool_name}")
        return await tool.execute(**kwargs)


# Global registry instance
tool_registry = ToolRegistry()