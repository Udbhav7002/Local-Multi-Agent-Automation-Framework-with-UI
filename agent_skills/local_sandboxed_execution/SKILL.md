---
name: Local Sandboxed Execution
description: Execute bash scripts or Python code inside an isolated container to verify the solution safely.
---

# Local Sandboxed Execution Instructions

When asked to write and run code that might be destructive (e.g., deleting files, installing unknown packages, modifying system paths), DO NOT run it directly on the host machine.

Instead, execute the code inside an isolated Docker container.

## Workflow
1. Ensure Docker is running via CLI.
2. Write the untrusted code to a temporary file (e.g., `/tmp/untrusted_script.py`).
3. Execute the script inside an ephemeral container using the `run_command` action:
`docker run --rm -v /tmp/untrusted_script.py:/script.py python:3.9 python /script.py`
4. Capture the output and report it back to the user.
