# Task: Add delete action for inbox markdown tasks

## Title
Add delete action for inbox markdown tasks

## Description
Add a simple delete action to the mission board so Randall can remove markdown task files that are still in `inbox/` and have not been processed yet.

The first version does not need to be pretty.
It only needs to be safe and clear.

## Priority
Medium

## Status
Inbox

## Goal
Allow deletion of unprocessed task markdown files from `workspace/shared/coding/inbox/` through the mission board UI.

## Acceptance Criteria
- [ ] The mission board shows a delete action for tasks in `inbox/`
- [ ] The delete action only applies to tasks still in `inbox/`
- [ ] Tasks in `doing/`, `done/`, and `failed/` cannot be deleted by this feature
- [ ] The delete action removes the selected markdown file from `inbox/`
- [ ] The UI shows a clear success or failure message
- [ ] Manual test steps are documented

## Files to Modify
- github/rag/app/main.py
- github/rag/README.md
- related HTML/template files if needed
- this task file
- logs/2026-03-20.md

## Scope
- add a simple delete action in the mission board
- only allow deletion for files in `inbox/`
- keep the implementation minimal and readable
- add basic safety checks before deleting files

## Out of Scope
- no deletion from `doing/`
- no deletion from `done/`
- no deletion from `failed/`
- no bulk delete
- no authentication changes
- no docker compose lifecycle changes
- no automatic service startup

## Runtime Context
- The application runs inside Docker
- The app should use the mounted shared coding workspace path
- The inbox path should be resolved from the configured task workspace path, not from relative source file traversal

## Safety Requirements
- Only delete files under `workspace/shared/coding/inbox/`
- Only delete `.md` files
- Reject path traversal or invalid filenames
- Prefer explicit file selection from listed inbox tasks
- Fail clearly if the target file does not exist

## Notes
Shared coding workspace:
- workspace/shared/coding/

Target directory:
- workspace/shared/coding/inbox/

Suggested implementation:
- add a delete button or link next to inbox tasks
- require a simple confirmation step if practical
- keep the feature minimal

## Validation
- safe static validation only
- do not start services automatically
- do not run docker compose up/down/restart/build
- provide manual steps for testing deletion from the mission board

## Progress Log
- [2026-03-20] Task created

## Changed Files
- None yet

## Blockers
- None

## Next Step
- Inspect the current mission board task list view and add the smallest safe delete flow for inbox markdown files
