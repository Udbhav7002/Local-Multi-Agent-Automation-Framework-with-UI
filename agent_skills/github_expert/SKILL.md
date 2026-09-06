---
name: GitHub & Git Expert
description: Expert workflows for Git version control and GitHub.
---

# Git & GitHub Expert Instructions

When the user asks to "save my work", "commit", or "push to github", follow these exact steps in order.
Do not use the GUI. All steps must be executed using the `run_command` action in the terminal.

## 1. Check Status
Run `git status` to see what files are modified.

## 2. Stage Changes
Run `git add .` to stage all modified files.

## 3. Generate Commit Message
Analyze the changes and run `git commit -m "[type]: [description]"`.
Follow Conventional Commits for the [type]:
- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code (white-space, formatting, etc)
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `test`: Adding missing tests or correcting existing tests
- `chore`: Changes to the build process or auxiliary tools and libraries

## 4. Push
Run `git push origin main` (or the current branch). 

## 5. Summary
Report success back to the user in a short, friendly summary.
