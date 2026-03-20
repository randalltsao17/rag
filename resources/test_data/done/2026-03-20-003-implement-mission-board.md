# Task: Implement a minimal mission board

## Title
Implement a minimal mission board

## Description
Implement a very simple mission board for the shared coding workspace.

The goal is to make current task status visible from the existing project without focusing on UI polish.

A minimal acceptable solution is:
- a JSON API that returns task status across inbox, doing, done, and failed

A better first version is:
- the JSON API
- plus a simple HTML page that displays the same information

## Priority
High

## Status
Done

## Goal
Create a minimal read-only mission board that shows the current coding task state from the shared workspace.

## Acceptance Criteria
- [ ] The app can read task files from the shared coding workspace
- [ ] The app exposes a simple API endpoint that returns task status
- [ ] The API includes tasks from `inbox`, `doing`, `done`, and `failed`
- [ ] The API output is understandable and usable for debugging
- [ ] If practical, add a simple HTML page to display the same status
- [ ] The implementation is documented briefly in README or task notes

## Files to Modify
- github/rag/app/
- github/rag/README.md
- other related files only if needed

## Scope
- inspect the existing Flask project
- add a minimal read-only mission board feature
- read shared task state from the filesystem
- implement a simple API endpoint
- optionally implement a simple HTML page

## Out of Scope
- no major UI work
- no authentication system
- no database redesign
- no websocket or real-time updates
- no docker compose lifecycle changes
- no automatic service startup

## Notes
Shared coding workspace:
- workspace/shared/coding/

Target directories to read:
- workspace/shared/coding/inbox/
- workspace/shared/coding/doing/
- workspace/shared/coding/done/
- workspace/shared/coding/failed/

Suggested minimal API response shape:
- counts by status
- task filenames
- basic task metadata if easily available
- last updated information if easily available

Suggested HTML page:
- plain list or table is enough
- no styling requirement
- readability is more important than appearance

Possible endpoint examples:
- `/mission/status`
- `/mission`
- `/tasks/status`

Possible HTML page examples:
- `/mission-board`
- `/tasks`

Prefer the smallest useful implementation first.

## Validation
- Manual steps (not executed):
  1. Run `curl http://localhost:8000/mission/status` to see the JSON task counts and metadata.
  2. Browse `http://localhost:8000/mission-board` to verify the simple HTML view renders current task data.
  3. Confirm service endpoints still respond via `/health`, `/ingest`, and `/query` as needed (no automated scripts run).
- No services or docker compose commands were started during this work.

## Progress Log
- [2026-03-20] Task created
- [2026-03-20] Moved the task into `doing/` and scoped the mission board feature against the existing FastAPI app and repo layout.
- [2026-03-20] Added filesystem helpers, the `/mission/status` JSON endpoint, and the `/mission-board` HTML view, and documented the new workflow in the README.
- [2026-03-20] Confirmed manual validation steps and prepared to commit/push the mission board update.
- [2026-03-20] Committed `feat: add mission board` (hash `a9d2195`) and pushed `main` → `origin/main`, making the mission board endpoints live upstream.

## Changed Files
- github/rag/app/main.py (mission board helpers + endpoints)
- github/rag/README.md (documented mission board feature + verification steps)
- logs/2026-03-20.md (daily log entry for the mission board work)

## Blockers
- None

## Next Step
- None – mission board work complete and committed.
