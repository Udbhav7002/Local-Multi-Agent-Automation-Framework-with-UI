---
name: Strict Output Formatting
description: Enforces strict JSON schemas for any data the agent outputs to ensure reliability across systems.
---

# Strict Output Formatting Instructions

Whenever you are tasked with analyzing data, extracting information, or providing a report that will be read by another script or system, YOU MUST output the final result as a strict, minified JSON object.

Do not include conversational filler text like "Here is the data you requested:".
Do not wrap the JSON in Markdown code blocks (e.g., ```json).

The output must start with `{` or `[` and end with `}` or `]`.

If the system fails to parse your output, you have failed the task.
