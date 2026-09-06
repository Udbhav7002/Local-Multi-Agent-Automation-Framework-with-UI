---
name: Headless Browser Automation
description: Integrate Playwright as a skill so agents can navigate single-page applications, click elements, and extract data dynamically.
---

# Headless Browser Automation Instructions

When a user asks you to extract data from a modern web app (React, Vue, SPA) where basic `curl` commands fail, DO NOT use GUI mouse clicks. Instead, use Playwright via Python.

## Workflow
1. Write a temporary Python script (`/tmp/playwright_script.py`) using `run_command` that imports playwright.
2. The script must launch a headless chromium browser.
3. Use Playwright's `page.goto()`, `page.wait_for_selector()`, and `page.locator().inner_text()` methods.
4. Print the extracted data to standard out (`print()`).
5. Run the script using `python3 /tmp/playwright_script.py`.

This guarantees robust data extraction without interfering with the user's active desktop environment.
