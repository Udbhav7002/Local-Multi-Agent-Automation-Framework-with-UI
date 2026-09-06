---
name: Plan-Before-Code
description: A workflow that forces the agent to output a structured implementation plan and identify edge cases before writing any production code.
---

# Plan-Before-Code Instructions

When the user asks you to build a new feature or complex script, YOU MUST NOT immediately write the final code. Instead, follow this workflow to ensure engineering discipline.

## 1. Analyze & Identify
First, identify all potential edge cases, security vulnerabilities, and scalability concerns regarding the user's request.

## 2. Generate Implementation Plan
Output a structured plan using `run_command` with an `echo` statement (or simply output it to the user if you have a message action) containing:
- **Architecture**: How the code will be structured.
- **Edge Cases**: At least 3 edge cases that must be handled.
- **Dependencies**: Any external libraries required.

## 3. Await User Approval (Optional)
If the architecture is extremely complex, use the `ask_user_skill` (if available) or simply pause execution to let the user review the plan. Otherwise, proceed to implementation only after the plan is fully mapped out.
