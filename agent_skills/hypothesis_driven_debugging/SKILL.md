---
name: Hypothesis-Driven Debugging
description: Enforces a structured, scientific approach to troubleshooting errors instead of making random code modifications.
---

# Hypothesis-Driven Debugging Instructions

When a script or application fails with an error, DO NOT immediately modify the source code to attempt a random fix.

Instead, execute the following workflow:

## 1. State the Hypothesis
Analyze the stack trace or error log. Formulate a specific hypothesis about why it failed. 
Write your hypothesis into a temporary file using `run_command` (e.g., `echo "Hypothesis: The database connection times out because the async event loop is blocked" > debug_log.txt`).

## 2. Write a Verification Test
Write a small, isolated script or unit test that specifically attempts to trigger the bug described in your hypothesis.
Run the test. If it does not reproduce the error, your hypothesis is wrong. Go back to Step 1.

## 3. Implement the Fix
Once your isolated test successfully reproduces the bug, implement a fix in the main codebase.

## 4. Verify
Run the exact same isolated test again. It should now pass. Only then can you declare the bug fixed.
