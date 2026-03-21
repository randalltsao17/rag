# RAG Notes Stack

A lightweight Retrieval-Augmented Generation (RAG) playground for personal notes. It bundles a FastAPI service for ingesting Markdown files, a Postgres+pgvector database for storage, optional n8n automations, and helper scripts for turning PDFs into Markdown before ingestion.

## Features
- **Markdown note ingestion** – `/ingest` hashes every Markdown file under the shared `/notes` volume and stores chunks plus OpenAI embeddings in Postgres.
- **Semantic querying** – `/query` embeds ad-hoc questions, retrieves the most similar note chunks, and asks OpenAI to synthesize an answer that cites the source files.
- **Containerized stack** – `docker-compose.yml` brings up pgvector, the FastAPI app, n8n, and Adminer for quick DB inspection.
- **Mission board** – `/mission/status` summarizes the Markdown task files stored in `backlog/`, `inbox/`, `doing/`, `done/`, and `failed/`, and `/mission-board` renders the same data as a simple HTML table for quick visibility without UI polish. New tasks are created in `backlog/` and can be promoted to `inbox/` when ready for execution.
- **Sample tooling** – scripts under `samples/` convert PDFs to Markdown (`pymupdf4llm`) and provide a CLI wrapper for querying the API.
- **Automation hooks** – `n8n_init.sh` prepares the persistent volume so n8n workflows can orchestrate ingestion/alerts later on.

## Architecture
```
+------------+        +-------------------+        +------------------+
| Markdown   |  -->   | FastAPI (app/)    |  -->   | Postgres +       |
| files in   | ingest | /ingest endpoint  |  store | pgvector (notes, |
| ./notes    |        | chunk + embed     |        | note_chunks)     |
+------------+        +-------------------+        +------------------+
        ^                         |
        |                         v
  helper scripts           /query endpoint
  convert PDFs             embeds questions and
  or raw docs              returns sourced answers
```
The stack optionally exposes:
- `n8n` at port `5678` for automations/webhooks.
- `Adminer` at port `8080` for manually inspecting the database.

## Requirements
- Docker + Docker Compose v2
- An OpenAI API key with access to `text-embedding-3-small` and `gpt-4.1-mini`
- Optional: `jq` for the sample CLI, `python3` + `pip` for PDF utilities

## Setup
1. **Clone & enter the repo**
   ```bash
   git clone <repo-url> && cd rag
   ```
2. **Create the notes folder** used by the app container (already mounted in compose):
   ```bash
   mkdir -p notes raw_files resources
   ```
3. **Configure environment variables** in a `.env` file at the repo root:
   ```bash
   OPENAI_API_KEY=sk-...
   DB_HOST=db
   DB_PORT=5432
   DB_NAME=ragdb
   DB_USER=raguser
   DB_PASSWORD=ragpass
   ```
   > The DB variables default to the compose values, so only `OPENAI_API_KEY` is strictly required for local dev.
4. **(Optional) Prepare n8n volume permissions** before bringing the stack up:
   ```bash
   ./n8n_init.sh
   ```
5. **Mission board path configuration** – the app reads the shared task files from the `TASK_WORKSPACE` environment variable (default `/workspace/shared/coding` in containers). When running inside Docker Compose the workspace is mounted into `/workspace/shared/coding` and the compose file exports `TASK_WORKSPACE`, so the mission board can read `backlog/`, `inbox/`, `doing/`, `done/`, and `failed/`. For other setups, set `TASK_WORKSPACE` to the host path that holds the shared workspace.

## Running the stack
```bash
docker compose up -d
```
Services:
- FastAPI app on <http://localhost:8000>
- Postgres/pgvector on `localhost:5432`
- n8n on <http://localhost:5678>
- Adminer on <http://localhost:8080>

> **Manual verification:** After `docker compose up -d`, run `docker compose ps`, then hit `GET http://localhost:8000/health` and `SELECT COUNT(*) FROM notes;` via Adminer or `psql` to confirm the API and database are reachable. Do not auto-start compose from scripts—you can copy/paste the command above manually.

> **Mission board path:** Docker Compose mounts the shared workspace at `/workspace/shared/coding` and sets `TASK_WORKSPACE` so `/mission/status` and `/mission-board` can read the markdown task files. If you run the app outside of Compose, make sure `TASK_WORKSPACE` points to the folder that contains `inbox/`, `doing/`, `done/`, and `failed/`.

## Ingest workflow
1. Drop Markdown files into the `notes/` directory (they are mounted into the container at `/notes`).
2. Call the ingest endpoint:
   ```bash
   curl -X POST http://localhost:8000/ingest
   ```
3. Response fields show how many files were processed, skipped (unchanged hash), and how many chunks were inserted.
4. The DB schema is defined in `init.sql` and consists of `notes` + `note_chunks` tables plus the `vector` extension.

### Converting PDFs to Markdown
- `samples/pdf.py` – quick single-file converter using `pymupdf4llm`.
- `samples/pdf2md/pdf2.py` – batch converter for an entire folder.
- Place converted Markdown into `notes/` (or staging `raw_files/` → manual review → `notes/`).

## Querying notes
- API: `POST /query` with JSON `{ "question": "...", "top_k": 3 }`
- Sample CLI: `samples/ragcli/ask.sh "What is the deployment plan?" 5`
- The endpoint returns the synthesized answer plus the list of matched chunks, their similarity scores, and source filenames.

## Mission board
The FastAPI app reads workspace task files from the `TASK_WORKSPACE` environment variable (default `/workspace/shared/coding` in containers). Docker Compose mounts the shared workspace into `/workspace/shared/coding` and sets `TASK_WORKSPACE` to that path. If `TASK_WORKSPACE` is missing or points to a non-existent directory, the mission board endpoints return a clear 500 error explaining the expected path.
- `GET /mission/status` returns counts, metadata, and last-updated timestamps for every markdown task file the project tracks.
- `GET /mission-board` renders that same information as a plain HTML table (state, status, priority, file, goal, and updated time) for easy visibility.
- `GET /mission/task` accepts a relative path to one of the state folders (`backlog/`, `inbox/`, `doing/`, `done/`, `failed/`), validates that it points to an existing `.md` file under the shared workspace, and renders the raw markdown content in a simple detail page so task owners can read the file without leaving the UI.

### Backlog workflow
New tasks are created in `backlog/` and progress through the following lifecycle:

```
backlog/ → inbox/ → doing/ → done/
                          ↘ failed/
```

- **Backlog → Inbox:** use the "Move to inbox" button on any backlog task. The task is ready for the next agent execution run.
- **Inbox → Backlog:** use the "Move to backlog" button to defer a task that is not yet ready.
- **Delete:** only tasks in `backlog/` may be deleted from the UI.

The `/mission-board` view surfaces a "Create a task" form that saves a new markdown file into `backlog/`. Only title, description, and priority are required — the form also accepts optional goal, acceptance criteria, files-to-modify, notes, and next-step hints. The filename is auto-generated as `YYYY-MM-DD-HHMMSS-short-title.md`. After submission the UI shows a short success message and reloads the page.

The mission board table includes a "View" action that navigates to `/mission/task?path=<state>/<filename>`, making it easy to read a task's markdown body without navigating the workspace directly.

### Move endpoint
`POST /mission/move-task` accepts a `path` form field (e.g. `backlog/my-task.md`) and moves the file to the target bucket (`backlog` ↔ `inbox`). Returns `409` if a file with the same name already exists in the target.
## App-only test compose
- `docker-compose.test.yml` spins up only the FastAPI app (no database or n8n) so you can debug mission board logic without touching the main stack.
- The test service uses `TASK_WORKSPACE=/workspace/shared/coding`, mounts the shared workspace read-only, binds the app code and notes, and exposes the app on port `18000` so it never conflicts with the running production port.
- Run it with `docker compose -f docker-compose.test.yml -p rag-test up --build`, then hit <http://localhost:18000/mission-board> to verify the UI, create-task flow, and health endpoints. When you’re done, tear it down with `docker compose -f docker-compose.test.yml -p rag-test down` so the container names stay isolated.

## Directory overview
```
app/                # FastAPI service (main.py) + requirements
notes/              # Markdown files to ingest (mounted into the app container)
raw_files/          # Optional staging area for original docs
resources/          # Spare folder for prompt templates/assets
samples/
  ├─ input.pdf      # Example source file
  ├─ pdf.py         # Single-file PDF → MD converter
  ├─ pdf2md/pdf2.py # Batch PDF → MD converter
  └─ ragcli/ask.sh  # Curl-based query helper
docker-compose.yml  # Defines db, app, n8n, adminer services
init.sql            # Database schema + pgvector setup
n8n_init.sh         # Fixes ownership for the n8n volume
restart_app.sh      # Convenience script to restart only the app container
```

## Development notes
- `app/main.py` and `app/main2.py` currently contain the FastAPI implementation (duplicate versions kept for experimentation).
- Embeddings use `text-embedding-3-small` (1536 dims), so the `note_chunks.embedding` column is declared as `VECTOR(1536)`.
- The ingestion process re-hashes file contents to skip unchanged notes and replaces chunks atomically per note.

## Manual validation checklist
- `curl http://localhost:8000/health` → returns `{"status": "healthy"...}`
- `curl -X POST http://localhost:8000/ingest` after placing at least one `.md` file into `notes/`
- `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":"test"}'`
- `curl http://localhost:8000/mission/status` (JSON task board summary)
- Browse http://localhost:8000/mission-board to see the mission board table
- Use the mission board form at http://localhost:8000/mission-board to create a task, then check that a new file appears in `backlog/` and the table refreshes so the entry is visible.
- On the mission board, use "Move to inbox" on a backlog task and confirm the row moves to the Inbox section.
- Use "Move to backlog" on an inbox task to defer it back.
- Use "Delete" on a backlog task and confirm the file is removed; verify that inbox tasks do not show a delete button.
- Inspect `notes` and `note_chunks` tables via Adminer or `psql` to ensure rows exist

## Next ideas
- Add Auth (API keys) for the HTTP endpoints
- Wire n8n workflows that ingest on file drops or schedule periodic refreshes
- Publish a Postman collection / OpenAPI schema for the FastAPI endpoints
