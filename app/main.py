import os
import hashlib
import html as html_lib
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from openai import OpenAI
import psycopg

app = FastAPI()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "db"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "ragdb"),
    "user": os.getenv("DB_USER", "raguser"),
    "password": os.getenv("DB_PASSWORD", "ragpass"),
}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4.1-mini"
NOTES_DIR = Path("/notes")

TASK_WORKSPACE = Path(os.getenv("TASK_WORKSPACE", "/workspace/shared/coding"))
TASK_STATES = ["inbox", "doing", "done", "failed"]


def _extract_section(content: str, heading: str) -> str:
    marker = f"## {heading}"
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == marker:
            section_lines = []
            for next_line in lines[index + 1 :]:
                if next_line.startswith("## "):
                    break
                section_lines.append(next_line)
            return "\n".join(section_lines).strip()
    return ""



def _clean_text_block(block: str) -> str:
    if not block:
        return ""
    cleaned_lines = []
    for line in block.splitlines():
        trimmed = line.rstrip()
        if trimmed:
            cleaned_lines.append(trimmed)
    return "\n".join(cleaned_lines).strip()


def _ensure_task_workspace() -> None:
    if not TASK_WORKSPACE.exists() or not TASK_WORKSPACE.is_dir():
        raise HTTPException(
            status_code=500,
            detail=f"TASK_WORKSPACE path not found: {TASK_WORKSPACE}"
        )


def _describe_task(task_path: Path, state: str) -> dict:
    content = task_path.read_text(encoding="utf-8")
    title = _extract_section(content, "Title") or task_path.stem
    priority = _extract_section(content, "Priority") or "Unknown"
    status_field = _extract_section(content, "Status")
    status = status_field or state.capitalize()
    goal = _clean_text_block(_extract_section(content, "Goal"))
    description = _clean_text_block(_extract_section(content, "Description"))
    updated = datetime.fromtimestamp(task_path.stat().st_mtime, timezone.utc).isoformat()
    try:
        relative_path = task_path.relative_to(TASK_WORKSPACE)
    except ValueError:
        relative_path = task_path
    return {
        "filename": task_path.name,
        "title": title,
        "status": status,
        "state": state,
        "priority": priority,
        "goal": goal,
        "description": description,
        "last_updated": updated,
        "path": str(relative_path),
    }



def _collect_tasks() -> List[dict]:
    _ensure_task_workspace()
    tasks = []
    for state in TASK_STATES:
        directory = TASK_WORKSPACE / state
        if not directory.exists():
            continue
        for task_file in sorted(directory.glob("*.md")):
            tasks.append(_describe_task(task_file, state))
    return tasks



def _counts_for_tasks(tasks: List[dict]) -> dict:
    counts = {state: 0 for state in TASK_STATES}
    for task in tasks:
        state = task.get("state", "")
        if state in counts:
            counts[state] += 1
        else:
            counts[state] = counts.get(state, 0) + 1
    return counts





class QueryRequest(BaseModel):
    question: str
    top_k: int = 3


def get_conn():
    return psycopg.connect(**DB_CONFIG)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunks.append(text[start:end])
        if end == text_len:
            break
        start = end - overlap

    return chunks


def get_openai_client():
    return OpenAI(api_key=OPENAI_API_KEY)


def embed_texts(texts: List[str]) -> List[List[float]]:
    client = get_openai_client()
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def embed_query(text: str) -> List[float]:
    client = get_openai_client()
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=[text],
    )
    return response.data[0].embedding


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "db_host": os.getenv("DB_HOST", "not-set"),
        "notes_dir": str(NOTES_DIR),
    }


@app.get("/mission/status")
def mission_status():
    tasks = _collect_tasks()
    counts = _counts_for_tasks(tasks)
    return {
        "status": "ok",
        "total_tasks": sum(counts.values()),
        "counts": counts,
        "tasks": tasks,
    }


@app.get("/mission-board", response_class=HTMLResponse)
def mission_board():
    tasks = _collect_tasks()
    counts = _counts_for_tasks(tasks)
    total_tasks = sum(counts.values())
    table_rows = []
    for task in tasks:
        goal_text = task.get("goal") or "—"
        goal_html = html_lib.escape(goal_text).replace("\n", "<br />")
        table_rows.append(
            "<tr>"
            f"<td>{html_lib.escape(task['state']).capitalize()}</td>"
            f"<td>{html_lib.escape(task['status'])}</td>"
            f"<td>{html_lib.escape(task['priority'])}</td>"
            f"<td>{html_lib.escape(task['title'])}</td>"
            f"<td>{html_lib.escape(task['last_updated'])}</td>"
            f"<td><code>{html_lib.escape(task['path'])}</code></td>"
            f"<td>{goal_html}</td>"
            "</tr>"
        )
    if not table_rows:
        table_rows.append('<tr><td colspan="7">No tasks found.</td></tr>')

    count_items = []
    for state in TASK_STATES:
        count_items.append(
            f"<li>{html_lib.escape(state.capitalize())}: {counts.get(state, 0)}</li>"
        )
    for state, count in counts.items():
        if state not in TASK_STATES:
            count_items.append(
                f"<li>{html_lib.escape(state)}: {count}</li>"
            )

    html_content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Mission Board</title>
  <style>
    body {{font-family: system-ui, sans-serif; margin: 1.5rem;}}
    table {{width: 100%; border-collapse: collapse;}}
    th, td {{border: 1px solid #d0d0d0; padding: 0.4rem 0.6rem; text-align: left;}}
    th {{background: #f3f3f3;}}
    code {{background: #f9f9f9; padding: 0.1rem 0.3rem; border-radius: 3px;}}
  </style>
</head>
<body>
  <h1>Mission Board</h1>
  <p>Total tasks tracked: <strong>{total_tasks}</strong></p>
  <h2>Counts by bucket</h2>
  <ul>
    {"\n    ".join(count_items)}
  </ul>
  <table>
    <thead>
      <tr><th>State</th><th>Status</th><th>Priority</th><th>Title</th><th>Last Updated (UTC)</th><th>File</th><th>Goal</th></tr>
    </thead>
    <tbody>
      {"\n      ".join(table_rows)}
    </tbody>
  </table>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@app.post("/ingest")
def ingest():
    if not OPENAI_API_KEY:
        return {"status": "error", "message": "OPENAI_API_KEY is not set"}

    if not NOTES_DIR.exists():
        return {"status": "error", "message": f"Notes dir not found: {NOTES_DIR}"}

    files = sorted(NOTES_DIR.glob("*.md"))
    if not files:
        return {"status": "ok", "message": "No markdown files found", "processed": 0}

    processed = 0
    skipped = 0
    total_chunks = 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            for file_path in files:
                content = file_path.read_text(encoding="utf-8").strip()
                if not content:
                    skipped += 1
                    continue

                file_hash = sha256_text(content)
                source_id = file_path.name
                title = file_path.stem

                cur.execute(
                    "SELECT id, hash FROM notes WHERE source_id = %s",
                    (source_id,),
                )
                row = cur.fetchone()

                if row and row[1] == file_hash:
                    skipped += 1
                    continue

                if row:
                    note_id = row[0]
                    cur.execute("DELETE FROM note_chunks WHERE note_id = %s", (note_id,))
                    cur.execute(
                        """
                        UPDATE notes
                        SET title = %s, content = %s, hash = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (title, content, file_hash, note_id),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO notes (source_id, title, content, source, hash, updated_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        RETURNING id
                        """,
                        (source_id, title, content, "manual", file_hash),
                    )
                    note_id = cur.fetchone()[0]

                chunks = chunk_text(content)
                if not chunks:
                    skipped += 1
                    continue

                embeddings = embed_texts(chunks)

                for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                    cur.execute(
                        """
                        INSERT INTO note_chunks (note_id, chunk_index, chunk_text, embedding)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (note_id, idx, chunk, embedding),
                    )

                processed += 1
                total_chunks += len(chunks)

        conn.commit()

    return {
        "status": "ok",
        "processed_files": processed,
        "skipped_files": skipped,
        "total_chunks": total_chunks,
    }


@app.post("/query")
def query_notes(req: QueryRequest):
    if not OPENAI_API_KEY:
        return {"status": "error", "message": "OPENAI_API_KEY is not set"}

    question_embedding = embed_query(req.question)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    n.source_id,
                    n.title,
                    c.chunk_index,
                    c.chunk_text,
                    1 - (c.embedding <=> %s::vector) AS similarity
                FROM note_chunks c
                JOIN notes n ON n.id = c.note_id
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (question_embedding, question_embedding, req.top_k),
            )
            rows = cur.fetchall()

    matches = []
    context_parts = []

    for row in rows:
        source_id, title, chunk_index, chunk_text, similarity = row
        matches.append(
            {
                "source_id": source_id,
                "title": title,
                "chunk_index": chunk_index,
                "similarity": float(similarity),
                "chunk_text": chunk_text,
            }
        )
        context_parts.append(
            f"[Source: {source_id} | chunk {chunk_index}]\n{chunk_text}"
        )

    if not matches:
        return {"status": "ok", "matches": [], "answer": "No matching notes found."}

    context = "\n\n".join(context_parts)

    client = get_openai_client()
    response = client.responses.create(
        model=CHAT_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "Answer the user's question using only the provided note context. "
                    "If the answer is not in the context, say you could not find it in the notes. "
                    "Be concise and mention the source file name when relevant."
                ),
            },
            {
                "role": "user",
                "content": f"Question:\n{req.question}\n\nContext:\n{context}",
            },
        ],
    )

    answer = response.output_text

    return {
        "status": "ok",
        "matches": matches,
        "answer": answer,
    }
