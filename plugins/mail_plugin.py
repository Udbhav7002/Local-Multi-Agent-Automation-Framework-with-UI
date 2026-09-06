import asyncio
from typing import Tuple
from core.executor.base import BaseExecutor

class MailPlugin:
    """
    Mail plugin that adds custom actions for reading Apple Mail invisibly in the background.
    """
    PLUGIN_NAME = "MailPlugin"
    ACTIONS = ["check_mail", "read_important_mail"]

    def __init__(self) -> None:
        pass

    async def execute(self, action: str, target: str) -> Tuple[bool, str]:
        if action == "check_mail":
            return await self._check_mail()
        elif action == "read_important_mail":
            return await self._check_mail(limit=int(target) if target.isdigit() else 5)
        return False, f"Unknown action: {action}"

    async def _check_mail(self, limit: int = 5) -> Tuple[bool, str]:
        script = f"""
        tell application "Mail"
            try
                set unreadMsgs to (messages of inbox whose read status is false)
                if (count of unreadMsgs) = 0 then
                    return "No unread emails."
                end if
                
                set output to "📬 Recent Unread Emails:\\n\\n"
                set msgCount to 0
                
                repeat with msg in unreadMsgs
                    if msgCount >= {limit} then exit repeat
                    set output to output & "From: " & sender of msg & "\\n"
                    set output to output & "Subject: " & subject of msg & "\\n"
                    set output to output & "Date: " & date received of msg & "\\n"
                    set output to output & "----------------------------------------\\n"
                    set msgCount to msgCount + 1
                end repeat
                
                return output
            on error errMsg
                return "Error accessing Mail: " & errMsg
            end try
        end tell
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                result = stdout.decode().strip()
                return True, result
            else:
                return False, stderr.decode().strip()
        except Exception as e:
            return False, f"Plugin error: {str(e)}"
