---
name: Session Continuity
description: Maintains state across multiple agent commands to handle complex, multi-step logins or navigate paginated dashboards.
---

# Session Continuity Instructions

When interacting with authenticated web services or multi-step processes via script, YOU MUST persist the session state.

## Implementation Guide
- If using `requests` in Python, ALWAYS instantiate a `requests.Session()` object instead of using `requests.get()` directly. This ensures cookies and authentication tokens are automatically passed to subsequent requests.
- If using Playwright, save the browser context state to a local file (`context.storage_state(path="state.json")`) after login, and load it upon the next script execution.

Do not attempt to re-authenticate on every single step of a multi-step task.
