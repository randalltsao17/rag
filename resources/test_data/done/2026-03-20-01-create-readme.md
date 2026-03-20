# Task Template

## Title
Create initial README.md for project (repo: rag)

## Description
Create a clean and useful initial `README.md` for this small project based on the current repository structure and code.

## Priority
High

## Status
Done

## Goal
Produce a practical `README.md` that explains what the project does, how to set it up, how to run it, and where the key files are.

## Acceptance Criteria
- [x] A new `README.md` is created or the existing one is improved
- [x] The README explains the project purpose clearly
- [x] The README includes run instructions
- [x] The README includes key file or folder overview
- [x] The README is written in clear English unless otherwise specified

## Files to Create/Modify
- README.md

## Scope
- Inspect the repository structure and existing source files
- Infer the project purpose from code and configuration
- Write a practical first-version README
- Keep the content concise and useful

## Out of Scope
- Do not refactor application code
- Do not change runtime behavior
- Do not commit or push unless explicitly authorized in this task

## Notes
Project repository path:
- workspace/shared/coding/github/rag

Please prefer a practical README structure such as:
- Project overview
- Features
- Requirements
- Setup
- Run
- Project structure
- Notes

If some information is uncertain, state assumptions clearly instead of guessing too much.

## Validation
- Manual checklist (not executed during this run):
  1. `docker compose up -d` then `docker compose ps` to confirm containers start.
  2. `curl http://localhost:8000/health` to verify the FastAPI service responds.
  3. Drop at least one `.md` file into `notes/` and call `curl -X POST http://localhost:8000/ingest`.
  4. `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":"test"}'` to confirm answers are returned.
  5. Inspect `notes` / `note_chunks` in Adminer or via `psql` to ensure rows were created.
- No services were started automatically while drafting the README.

## Progress Log
- [2026-03-20] Inspected repo layout/code and drafted a comprehensive README covering architecture, setup, ingestion/query flows, and manual validation notes.
- [2026-03-20] Documented manual verification steps (health check, ingest, query, DB inspection) inside the README so future runs can validate without auto-starting services.

## Changed Files
- github/rag/README.md (new project overview + instructions)

## Blockers
- None

## Next Step
- None – task completed and ready for archive in `done/`.
