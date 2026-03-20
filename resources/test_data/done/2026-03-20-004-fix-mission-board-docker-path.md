# Task: Fix mission board Docker path handling

## Title
Fix mission board Docker path handling

## Description
Fix the mission board implementation so it works correctly when the app runs inside Docker.

The current implementation appears to assume a host-like filesystem path by inferring the shared workspace location from `Path(__file__)` parent traversal.
This is not reliable in the container runtime.

## Priority
High

## Status
Done

## Goal
Make the mission board read task status from a clearly configured shared workspace path inside Docker.

## Acceptance Criteria
- [x] The app no longer relies on `Path(__file__).resolve().parents[...]` to locate the shared coding workspace
- [x] The shared coding workspace path is read from an explicit environment variable such as `TASK_WORKSPACE`
- [x] Docker compose includes a volume mapping for the shared coding workspace
- [x] The app can read `inbox`, `doing`, `done`, and `failed` from the mounted path
- [x] Manual test steps are documented
- [x] No services are auto-started by the agent

## Files to Modify
- github/rag/app/main.py
- github/rag/docker-compose.yml
- github/rag/README.md
- this task file
- logs/2026-03-20.md

## Scope
- inspect the current mission board implementation
- replace path guessing with explicit path configuration
- update docker compose volume mapping if needed
- use environment-based configuration for the task workspace
- document manual verification steps

## Out of Scope
- no UI redesign
- no authentication
- no websocket or real-time refresh
- no docker compose up/down/restart/build by the agent
- no changes to unrelated application logic

## Runtime Context
- The application runs inside Docker
- The app should not assume host filesystem paths from `__file__`
- Shared task state should be accessed through an explicit mounted path
- Prefer environment-variable based path configuration over relative parent path guessing

## Implementation Preference
- Use docker compose volume mapping for shared coding workspace access
- Use an environment variable such as `TASK_WORKSPACE`
- Prefer a stable container path such as `/workspace/shared/coding`
- Avoid relying on `Path(__file__).resolve().parents[...]`

## Notes
Shared coding workspace on host:
- workspace/shared/coding/

Expected directories:
- workspace/shared/coding/inbox/
- workspace/shared/coding/doing/
- workspace/shared/coding/done/
- workspace/shared/coding/failed/

Suggested approach:
- mount the shared coding workspace into the container as read-only if practical
- read the path from `TASK_WORKSPACE`
- fail clearly if the path does not exist

## Validation
- Manual steps (not executed):
  1. Run `docker compose up -d` manually, `docker compose exec app ls /workspace/shared/coding` to ensure the mount is present, and check `/workspace/shared/coding/inbox` exists.
  2. `curl http://localhost:8000/mission/status` and `curl http://localhost:8000/mission-board` to verify the endpoints return the workspace-based data.
  3. Inspect `docker compose exec app env | grep TASK_WORKSPACE` or similar to confirm the variable points to `/workspace/shared/coding`.
- Services and docker compose commands were not started automatically by this agent.

## Progress Log
- [2026-03-20] Task created
- [2026-03-20] Replaced the workspace-guessing logic with the `TASK_WORKSPACE` env var, added `/workspace/shared/coding` configuration, and ensured the mission board helpers skip missing directories while surfacing a clear error if the path is unavailable.
- [2026-03-20] Mounted the shared workspace into Docker Compose, exported `TASK_WORKSPACE` for the app, documented the configuration in the README, and committed/pushed `fix: docker-friendly mission board path` (hash `2cd5750`).
- [2026-03-20] Task is held in review while Randall manually verifies the mission-board create-task workflow.
- [2026-03-20] Marked the task as done per the latest instruction so the mission board path fix can be archived.

## Changed Files
- github/rag/app/main.py
- github/rag/docker-compose.yml
- github/rag/README.md
- logs/2026-03-20.md
- doing/2026-03-20-004-fix-mission-board-docker-path.md

## Blockers
- None

## Next Step
- None – mission board path fix is complete and archived.
