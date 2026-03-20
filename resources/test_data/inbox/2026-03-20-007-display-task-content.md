# Task: Display task markdown content in mission board

## Title
Display task markdown content in mission board

## Description
Add a simple view in the mission board so Randall can open a task and read its markdown content directly from the web UI.

The first version does not need to be pretty.
It only needs to be clear and readable.

## Priority
Low

## Status
Inbox

## Goal
Allow viewing the full content of task markdown files from the shared coding workspace through the mission board UI.

## Acceptance Criteria
- [ ] The mission board can display the content of a selected task markdown file
- [ ] The feature works for tasks in `inbox/`, `doing/`, `done/`, and `failed/`
- [ ] The displayed content is readable in plain text or simple preformatted markdown view
- [ ] Invalid filenames or path traversal attempts are rejected
- [ ] A clear error message is shown if the file does not exist
- [ ] Manual test steps are documented

## Files to Modify
- github/rag/app/main.py
- github/rag/README.md
- related HTML/template files if needed
- this task file
- logs/2026-03-20.md

## Scope
- add a simple task detail view in the mission board
- allow viewing markdown task files from the shared coding workspace
- keep the implementation minimal and readable

## Out of Scope
- no markdown editor
- no live preview enhancements
- no authentication changes
- no file modification in this task
- no docker compose lifecycle changes
- no automatic service startup

## Runtime Context
- The application runs inside Docker
- The app should use the mounted shared coding workspace path
- Task paths should be resolved from the configured task workspace path, not from relative source file traversal

## Safety Requirements
- Only read files under the shared coding workspace task directories
- Only allow `.md` files
- Reject path traversal or invalid filenames
- Fail clearly if the target file does not exist

## Notes
Shared coding workspace:
- workspace/shared/coding/

Target directories:
- workspace/shared/coding/inbox/
- workspace/shared/coding/doing/
- workspace/shared/coding/done/
- workspace/shared/coding/failed/

Suggested implementation:
- add a "view" link or button next to each task
- render the file content in a simple detail page
- plain text or preformatted markdown is acceptable for the first version

## Validation
- safe static validation only
- do not start services automatically
- do not run docker compose up/down/restart/build
- provide manual steps for testing task content display from the mission board

## Progress Log
- [2026-03-20] Task created

## Changed Files
- None yet

## Blockers
- None

## Next Step
- Inspect the current mission board task list view and add the smallest useful task content display feature
