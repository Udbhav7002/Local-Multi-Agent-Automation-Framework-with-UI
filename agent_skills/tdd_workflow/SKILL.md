---
name: TDD (Test-Driven Development) Workflow
description: Enforces a strict Test-Driven Development workflow for new features and bug fixes.
---

# TDD Workflow Instructions

When the user asks to implement a new feature or fix a bug in Python, YOU MUST strictly follow this TDD workflow in order:

## 1. Write the Test First
Identify the file that needs to be created or modified. 
Create a corresponding test file (e.g., `tests/test_<feature>.py`).
Write a unit test that defines the expected behavior of the feature or reproduces the bug.
Use the `run_command` action with a terminal command (e.g., `cat << 'EOF' > ...`) to write the test file.

## 2. Run the Test (It should fail)
Execute the test using `run_command` with `python3 -m pytest <test_file>`.
The expected outcome is that the test will FAIL. 

## 3. Implement the Code
Write the minimum amount of code necessary in the actual source file to make the test pass. Use CLI commands to write or modify the file.

## 4. Run the Test (It should pass)
Execute the test again using `python3 -m pytest <test_file>`.
If it fails, fix the code and repeat this step until it passes.

## 5. Refactor
Once passing, review the code and refactor for cleanliness, readability, and performance. Re-run the tests to ensure you didn't break anything.

CRITICAL: Never write the implementation code before the test. The test must exist and fail first.
