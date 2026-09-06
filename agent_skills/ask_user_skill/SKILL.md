---
name: Ask User (Grill Me)
description: A workflow to interview the user or ask for clarification using a native macOS dialog before making risky decisions.
---

# Ask User Instructions

If you are asked to implement a large, ambiguous feature, or if you encounter a decision that requires human intuition, DO NOT GUESS. 

Instead, you must use a native macOS dialog box to ask the user for clarification.

## Workflow

1. Formulate a short, clear question for the user.
2. Output a `run_command` action with the following AppleScript command to pop up a dialog box:

`osascript -e 'set theResponse to display dialog "[YOUR QUESTION HERE]" default answer "" with title "AI Agent Question"' -e 'text returned of theResponse'`

3. The StepRunner will execute this, the user will see a popup on their screen, type their answer, and the StepRunner will feed that text back to you.
4. Use the user's answer to adjust your plan and proceed.

CRITICAL: Do not overuse this. Only use it for critical ambiguities that would cause the automation to fail if guessed incorrectly.
