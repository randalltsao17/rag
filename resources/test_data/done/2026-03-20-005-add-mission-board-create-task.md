# Task: Add create-task form to mission board

## Title
Add create-task form to mission board

## Description
Add a simple task creation feature to the mission board so a new coding task can be created directly from the web UI and written into the shared coding workspace inbox.

The feature should use a template so the user does not need to manually write a full markdown task file each time.

## Priority
High

## Status
Done

## Goal
Allow Randall to create a new task from the mission board UI and save it as a markdown file in `workspace/shared/coding/inbox/`.

## Acceptance Criteria
- [ ] The mission board has a simple page or section for creating a new task
- [ ] The form writes a new markdown file into `workspace/shared/coding/inbox/`
- [ ] The created file follows a consistent task template
- [ ] The user only needs to fill a minimal set of fields
- [ ] Filename is generated automatically in a predictable format
- [ ] Default values are provided where practical
- [ ] Manual test steps are documented

## Files to Modify
- github/rag/app/main.py
- github/rag/README.md
- related template or HTML files if needed
- this task file
- logs/2026-03-20.md

## Scope
- add a simple create-task form to the mission board
- create markdown task files in the inbox directory
- use a built-in template or template file
- auto-generate a filename
- keep implementation simple and readable

## Out of Scope
- no authentication system
- no rich text editor
- no drag-and-drop UI
- no database storage
- no automatic task assignment
- no docker compose lifecycle changes
- no automatic service startup

## Runtime Context
- The application runs inside Docker
- The app should use the mounted shared coding workspace path
- Task files should be created under `workspace/shared/coding/inbox/` through the configured mounted path
- Prefer explicit environment-based path configuration

## Template Requirements
The form should require only a minimal set of fields, such as:
- title
- description
- priority

The app should auto-fill or default the following where practical:
- status = Inbox
- progress log initial entry
- changed files = None yet
- blockers = None
- next step = Review task and begin implementation

Suggested optional fields:
- files to modify
- notes
- acceptance criteria

## Filename Rules
Use a predictable filename format such as:
- `YYYY-MM-DD-XXX-short-title.md`

If automatic numbering is difficult, a timestamp-based filename is acceptable.

## Suggested Template Structure
A minimal generated task file should include:
- Title
- Description
- Priority
- Status
- Goal
- Acceptance Criteria
- Files to Modify
- Notes
- Validation
- Progress Log
- Changed Files
- Blockers
- Next Step

## Validation
- Manual verification (confirmed by Randall): the mission board form successfully created a markdown task in `inbox/`, the page reloaded and the new row appeared in the table, and the generated file uses the shared template sections.
- Services or docker compose commands were not started automatically during this work.

## Progress Log
- [2026-03-20] Task created
- [2026-03-20] Added mission board form, template, and create-task endpoint to write inbox files.
- [2026-03-20] Updated the form to reload after a successful submission and documented the refreshed table behavior in the README.
- [2026-03-20] Task completed (commit `1bdd1da`) after Randall confirmed the mission-board create-task flow, so it can move into `done/`.

## Changed Files
- github/rag/app/main.py
- github/rag/README.md
- logs/2026-03-20.md
- doing/2026-03-20-005-add-mission-board-create-task.md

## Blockers
- None

## Next Step
- None – the mission board create-task workflow is now complete and archived.
