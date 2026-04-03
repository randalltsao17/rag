import os
import hashlib
import html as html_lib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException
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
TASK_STATES = ["backlog", "inbox", "doing", "done", "failed"]

RESEARCH_TOPICS_PATH = Path(os.getenv("RESEARCH_TOPICS_PATH", "/workspace/shared/research/topics.md"))
MOVE_ALLOWED = {
    "backlog": "inbox",
    "inbox": "backlog",
}


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


def _slugify_title(text: str) -> str:
    normalized = text.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    if not normalized:
        return "task"
    return normalized[:40]



def _describe_task(task_path: Path, state: str) -> dict:
    content = task_path.read_text(encoding="utf-8")
    title = _extract_section(content, "Title") or task_path.stem
    priority = _extract_section(content, "Priority") or "Unknown"
    status_field = _extract_section(content, "Status")
    status = status_field or state.capitalize()
    goal = _clean_text_block(_extract_section(content, "Goal"))
    description = _clean_text_block(_extract_section(content, "Description"))
    updated = datetime.fromtimestamp(task_path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M")
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



def _read_latest_log() -> tuple[str, str]:
    """Find and read the latest daily log from TASK_WORKSPACE/logs/.

    Returns a tuple of (filename, content). Both are empty strings when no log
    file is found or the directory is missing/unreadable.
    """
    try:
        logs_dir = TASK_WORKSPACE / "logs"
        if not logs_dir.exists() or not logs_dir.is_dir():
            return ("", "")
        candidates = sorted(
            (f for f in logs_dir.glob("*.md") if f.name != "LOG_TEMPLATE.md"),
            key=lambda f: f.name,
        )
        if not candidates:
            return ("", "")
        latest = candidates[-1]
        content = latest.read_text(encoding="utf-8").strip()
        return (latest.name, content)
    except OSError:
        return ("", "")


def _read_research_topics() -> str:
    """Read the research topics file and return its content.

    Returns an empty string if the file does not exist, is not readable,
    or is empty. The caller renders a fallback message when the result is falsy.
    """
    try:
        if not RESEARCH_TOPICS_PATH.exists():
            return ""
        content = RESEARCH_TOPICS_PATH.read_text(encoding="utf-8").strip()
        return content
    except OSError:
        return ""


def _write_research_topics(content: str) -> None:
    """Write the research topics file.

    Raises HTTPException if the path is not the expected research topics file
    or if the file cannot be written.
    """
    resolved = RESEARCH_TOPICS_PATH.resolve()
    expected = RESEARCH_TOPICS_PATH.resolve()
    if resolved != expected:
        raise HTTPException(status_code=400, detail="Invalid research topics path.")
    try:
        RESEARCH_TOPICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESEARCH_TOPICS_PATH.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to write research topics: {exc}")


def _generate_task_filename(title_slug: str) -> str:
    now = datetime.now(timezone.utc)
    date_prefix = now.strftime("%Y-%m-%d")
    time_suffix = now.strftime("%H%M%S")
    base = f"{date_prefix}-{time_suffix}-{title_slug}"
    backlog_dir = TASK_WORKSPACE / "backlog"
    candidate = base
    index = 1
    while (backlog_dir / f"{candidate}.md").exists():
        candidate = f"{base}-{index}"
        index += 1
    return f"{candidate}.md"



DEFAULT_EXECUTION_REQUEST = (
    "Do not stop early after a partial implementation if the next step can be continued safely in the same run. "
    "Only stop early if the task is completed, blocked, runtime validation is not authorized or not available, "
    "or a clear safe checkpoint has been reached and no further safe progress can be made. "
    "Make small, safe, incremental changes. "
    "Update the task file with progress, changed files, blockers, validation, and next step. "
    "Write a daily log. "
    "If the task is documentation-only and acceptance criteria are satisfied, move it to done. "
    "Do not run docker compose lifecycle commands against the active environment. "
    "If the current task explicitly authorizes isolated test validation, you may continue using the isolated test compose setup only. "
    "Do not use the main compose file. "
    "Commit and push the code when the task is done."
)


def _task_template(
    title: str,
    description: str,
    priority: str,
    goal: str,
    acceptance_criteria: str,
    files_to_modify: str,
    notes: str,
    next_step: str,
) -> str:
    created_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    validation = (
        "- Submit this form on the mission board at `/mission-board`.\n"
        "- Confirm the new file appears under `backlog/` inside the shared workspace.\n"
        "- Reload `/mission-board` to ensure the task shows up in the Backlog section.\n"
        "- Use the 'Move to inbox' action to promote the task when ready.\n"
    )

    return f"""# Task: {title}

## Title
{title}

## Description
{description}

## Priority
{priority}

## Status
Backlog

## Goal
{goal or "Review task and begin implementation"}

## Acceptance Criteria
{acceptance_criteria or "- [ ] The feature works as expected\n- [ ] Validation is recorded clearly\n- [ ] The task file and daily log are updated"}

## Files to Modify
{files_to_modify or "- github/rag/app/main.py\n- related HTML/template files if needed"}

## Notes
{notes or "None."}

## Execution Request
{DEFAULT_EXECUTION_REQUEST}

## Validation
{validation.strip()}

## Progress Log
- [{created_date}] Created via mission board form.

## Changed Files
None yet

## Blockers
None

## Next Step
{next_step or "Inspect the current implementation and apply the smallest safe change first."}
""".strip()


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


def _resolve_task_file(relative_path: str) -> Path:
    normalized = (relative_path or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Task path is required.")
    requested = Path(normalized)
    if requested.is_absolute():
        raise HTTPException(status_code=400, detail="Absolute paths are not allowed.")
    if requested.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only Markdown (.md) task files can be displayed.")
    if not requested.parts:
        raise HTTPException(status_code=400, detail="Invalid task path.")
    if requested.parts[0] not in TASK_STATES:
        raise HTTPException(status_code=400, detail="Task path must begin with a valid state directory.")
    workspace_root = TASK_WORKSPACE.resolve()
    candidate = (TASK_WORKSPACE / requested).resolve(strict=False)
    if not (candidate == workspace_root or workspace_root in candidate.parents):
        raise HTTPException(status_code=400, detail="Task path must reside under the shared workspace.")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Task file not found.")
    if not candidate.is_file():
        raise HTTPException(status_code=400, detail="Task path must point to a file.")
    return candidate


def _resolve_task_file_no_exist_check(relative_path: str) -> Path:
    """Like _resolve_task_file but skips the exists check (for destination path validation)."""
    normalized = (relative_path or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Task path is required.")
    requested = Path(normalized)
    if requested.is_absolute():
        raise HTTPException(status_code=400, detail="Absolute paths are not allowed.")
    if requested.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only Markdown (.md) task files can be resolved.")
    if not requested.parts:
        raise HTTPException(status_code=400, detail="Invalid task path.")
    if requested.parts[0] not in TASK_STATES:
        raise HTTPException(status_code=400, detail="Task path must begin with a valid state directory.")
    workspace_root = TASK_WORKSPACE.resolve()
    candidate = (TASK_WORKSPACE / requested).resolve(strict=False)
    if not (candidate == workspace_root or workspace_root in candidate.parents):
        raise HTTPException(status_code=400, detail="Task path must reside under the shared workspace.")
    return candidate


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


def _simple_md_to_html(md: str) -> str:
    """Convert a small subset of markdown to HTML for display purposes.

    Handles: headings (h1-h3), bold, inline code, fenced code blocks,
    unordered list items, horizontal rules, and paragraphs.
    No external dependency required.
    """
    import re
    lines = md.splitlines()
    out: list[str] = []
    in_code_block = False
    para_buf: list[str] = []

    def flush_para() -> None:
        text = " ".join(para_buf).strip()
        if text:
            out.append(f"<p>{text}</p>")
        para_buf.clear()

    def inline(text: str) -> str:
        # Bold **text**
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # Inline code `text`
        text = re.sub(r"`([^`]+)`", lambda m: f"<code>{html_lib.escape(m.group(1))}</code>", text)
        return text

    for line in lines:
        if line.startswith("```"):
            if in_code_block:
                out.append("</code></pre>")
                in_code_block = False
            else:
                flush_para()
                out.append('<pre><code>')
                in_code_block = True
            continue
        if in_code_block:
            out.append(html_lib.escape(line))
            continue
        # Headings
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            flush_para()
            lvl = len(m.group(1)) + 1  # h2-h4 (h1 reserved for page title)
            lvl = min(lvl, 4)
            out.append(f"<h{lvl}>{html_lib.escape(m.group(2))}</h{lvl}>")
            continue
        # HR
        if re.match(r"^[-*_]{3,}\s*$", line):
            flush_para()
            out.append("<hr>")
            continue
        # Unordered list
        m2 = re.match(r"^[\*\-]\s+(.*)", line)
        if m2:
            flush_para()
            out.append(f"<li>{inline(html_lib.escape(m2.group(1)))}</li>")
            continue
        # Blank line → paragraph break
        if not line.strip():
            flush_para()
            continue
        para_buf.append(inline(html_lib.escape(line)))

    flush_para()
    if in_code_block:
        out.append("</code></pre>")

    # Wrap consecutive <li> in <ul>
    result = "\n".join(out)
    result = re.sub(r"((?:<li>.*?</li>\n?)+)", lambda m: f"<ul>{m.group(0)}</ul>", result)
    return result


@app.get("/mission-board", response_class=HTMLResponse)
def mission_board():
    research_content = _read_research_topics()
    latest_log_filename, latest_log_content = _read_latest_log()
    tasks = _collect_tasks()
    counts = _counts_for_tasks(tasks)
    total_tasks = sum(counts.values())

    # Group tasks by state
    tasks_by_state: dict[str, list] = {state: [] for state in TASK_STATES}
    for task in tasks:
        s = task.get("state", "")
        if s in tasks_by_state:
            tasks_by_state[s].append(task)

    def _priority_badge(priority: str) -> str:
        p = priority.strip().lower()
        if p == "high":
            color = "#dc2626"; bg = "#fee2e2"
        elif p == "medium":
            color = "#d97706"; bg = "#fef3c7"
        elif p == "low":
            color = "#16a34a"; bg = "#dcfce7"
        else:
            color = "#6b7280"; bg = "#f3f4f6"
        return (
            f'<span style="display:inline-block;padding:0.1rem 0.45rem;border-radius:9999px;'
            f'font-size:0.78rem;font-weight:700;color:{color};background:{bg};">'
            f'{html_lib.escape(priority)}</span>'
        )

    def _build_table(state_tasks: list, state_val: str) -> str:
        if not state_tasks:
            return f'<p style="color:#9ca3af;font-style:italic;">No tasks in {state_val}.</p>'
        rows = []
        for task in state_tasks:
            goal_text = task.get("goal") or "—"
            goal_html = html_lib.escape(goal_text).replace("\n", "<br />")
            view_link = f"/mission/task?path={quote(task['path'])}"
            escaped_path = html_lib.escape(task["path"])
            filename_only = html_lib.escape(task.get("filename", task["path"]))
            actions = [f'<a href="{html_lib.escape(view_link)}">View</a>']
            if state_val == "backlog":
                actions.append(
                    f'<button type="button" class="move-task-button" data-path="{escaped_path}" data-label="Move to inbox">→ Inbox</button>'
                )
                actions.append(
                    f'<button type="button" class="delete-task-button" data-path="{escaped_path}">Delete</button>'
                )
            elif state_val == "inbox":
                actions.append(
                    f'<button type="button" class="move-task-button" data-path="{escaped_path}" data-label="Move to backlog">← Backlog</button>'
                )
            actions_html = " ".join(actions)
            rows.append(
                "<tr>"
                f"<td>{_priority_badge(task['priority'])}</td>"
                f"<td>{html_lib.escape(task['title'])}</td>"
                f"<td>{html_lib.escape(task['last_updated'])}</td>"
                f'<td><code title="{escaped_path}">{filename_only}</code></td>'
                f"<td>{goal_html}</td>"
                f"<td>{actions_html}</td>"
                "</tr>"
            )
        return (
            '<table>'
            '<thead><tr>'
            '<th>Priority</th><th>Title</th><th>Updated (UTC)</th>'
            '<th>File</th><th>Goal</th><th>Actions</th>'
            '</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody>'
            '</table>'
        )

    state_sections_html = []
    for state in TASK_STATES:
        state_tasks = tasks_by_state.get(state, [])
        count = len(state_tasks)
        table_html = _build_table(state_tasks, state)
        state_sections_html.append(
            f'<section class="state-section">'
            f'<h2>{html_lib.escape(state.capitalize())} <span class="count-badge">{count}</span></h2>'
            f'{table_html}'
            f'</section>'
        )

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

    if research_content:
        research_html = _simple_md_to_html(research_content)
    else:
        research_html = "<p><em>No research topics found. Add content to the topics file to display it here.</em></p>"

    if latest_log_filename and latest_log_content:
        latest_log_html = (
            f"<p><strong>File:</strong> <code>{html_lib.escape(latest_log_filename)}</code></p>"
            + _simple_md_to_html(latest_log_content)
        )
    elif latest_log_filename:
        latest_log_html = (
            f"<p><strong>File:</strong> <code>{html_lib.escape(latest_log_filename)}</code></p>"
            "<p><em>Log file is empty.</em></p>"
        )
    else:
        latest_log_html = "<p><em>No daily log found. Logs are written to <code>logs/</code> inside the shared workspace.</em></p>"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task_template_default = html_lib.escape(
        f"# Task: short-descriptive-title\n"
        f"\n"
        f"## Title\n"
        f"Short descriptive title\n"
        f"\n"
        f"## Description\n"
        f"Describe the task clearly.\n"
        f"\n"
        f"## Priority\n"
        f"Medium\n"
        f"\n"
        f"## Status\n"
        f"Backlog\n"
        f"\n"
        f"## Goal\n"
        f"What outcome does this task achieve?\n"
        f"\n"
        f"## Acceptance Criteria\n"
        f"- [ ] The feature works as expected\n"
        f"- [ ] Validation is recorded clearly\n"
        f"- [ ] The task file and daily log are updated\n"
        f"\n"
        f"## Files to Modify\n"
        f"- list relevant files here\n"
        f"\n"
        f"## Notes\n"
        f"Any extra context, constraints, or background information.\n"
        f"\n"
        f"## Progress Log\n"
        f"- [{today}] Task created\n"
        f"\n"
        f"## Next Step\n"
        f"Inspect the current implementation and apply the smallest safe change first.\n"
    )

    html_content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Mission Board</title>
  <style>
    *, *::before, *::after {{box-sizing: border-box;}}
    body {{font-family: system-ui, sans-serif; margin: 0; padding: 1.5rem; background: #f9fafb; color: #111;}}
    .container {{max-width: 1100px; margin: 0 auto;}}
    h1 {{margin-top: 0; font-size: 1.75rem;}}
    h2 {{font-size: 1.2rem; margin-top: 0;}}
    table {{width: 100%; border-collapse: collapse; margin-top: 0.6rem; background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.07);}}
    th, td {{border: 1px solid #e5e7eb; padding: 0.4rem 0.65rem; text-align: left; vertical-align: top;}}
    th {{background: #f3f4f6; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.03em; color: #374151;}}
    td {{font-size: 0.9rem;}}
    code {{background: #f1f5f9; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.82rem; word-break: break-all;}}
    pre {{background: #f1f5f9; padding: 0.75rem 1rem; border-radius: 5px; overflow-x: auto; font-size: 0.85rem; margin: 0.5rem 0;}}
    pre code {{background: transparent; padding: 0; font-size: inherit;}}
    a {{color: #2563eb; text-decoration: none;}}
    a:hover {{text-decoration: underline;}}
    button {{cursor: pointer; border: none; border-radius: 4px; font-size: 0.82rem; font-weight: 600; padding: 0.25rem 0.6rem; transition: background 0.15s ease; margin-right: 0.25rem; margin-bottom: 0.2rem;}}
    .move-task-button {{background: #e0f2fe; color: #0369a1;}}
    .move-task-button:hover {{background: #bae6fd;}}
    .delete-task-button {{background: #fee2e2; color: #b91c1c;}}
    .delete-task-button:hover {{background: #fecaca;}}
    .count-badge {{display: inline-block; background: #e5e7eb; color: #374151; border-radius: 9999px; font-size: 0.72rem; font-weight: 700; padding: 0.05rem 0.5rem; vertical-align: middle; margin-left: 0.35rem;}}
    .state-section {{background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05);}}
    .state-section table {{box-shadow: none; border-radius: 0; margin-top: 0.5rem;}}
    .info-card {{background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.85rem 1.15rem 1rem; margin-bottom: 1.25rem;}}
    .info-card h2 {{margin-bottom: 0.5rem;}}
    .info-card ul {{margin: 0.25rem 0; padding-left: 1.4rem;}}
    .info-card li {{margin: 0.15rem 0;}}
    .info-card p {{margin: 0.3rem 0;}}
    .divider {{border: none; border-top: 2px solid #e5e7eb; margin: 2rem 0;}}
    .form-card {{background: #fefefe; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem 1.25rem 1.5rem; box-shadow: 0 1px 4px rgba(0,0,0,0.05);}}
    #create-task-form {{display: grid; gap: 0.75rem; max-width: 720px;}}
    #create-task-form label {{display: flex; flex-direction: column; font-weight: 600; gap: 0.3rem;}}
    #create-task-form input,
    #create-task-form textarea,
    #create-task-form select {{font-family: inherit; font-size: 1rem; padding: 0.45rem 0.55rem; border: 1px solid #c0c0c0; border-radius: 4px; background: #fff;}}
    #create-task-form textarea {{resize: vertical; min-height: 60px;}}
    #create-task-form button {{align-self: flex-start; padding: 0.55rem 1.1rem; border: none; border-radius: 4px; background: #2563eb; color: #fff; font-weight: 600; cursor: pointer; font-size: 1rem; transition: background 0.2s ease;}}
    #create-task-form button:hover {{background: #1d4ed8;}}
    #research-edit-form textarea {{font-family: inherit; font-size: 0.95rem; padding: 0.45rem 0.55rem; border: 1px solid #c0c0c0; border-radius: 4px; background: #fff; width: 100%; box-sizing: border-box; resize: vertical; min-height: 120px;}}
    #research-edit-form button {{margin-top: 0.5rem; padding: 0.45rem 1rem; border: none; border-radius: 4px; background: #0b6; color: #fff; font-weight: 600; cursor: pointer; transition: background 0.2s ease;}}
    #research-edit-form button:hover {{background: #099;}}
    #research-cancel-button {{background: #6b7280;}}
    #research-cancel-button:hover {{background: #4b5563;}}
    #research-message {{margin-top: 0.4rem; font-weight: 600; min-height: 1.4rem;}}
    #research-message.success {{color: #0b6;}}
    #research-message.error {{color: #c00;}}
    #form-message {{margin-top: 0.45rem; font-weight: 600; min-height: 1.5rem;}}
    #form-message.success {{color: #0b6;}}
    #form-message.error {{color: #c00;}}
    #delete-message {{margin-top: 0.45rem; font-weight: 600; min-height: 1.5rem;}}
    #delete-message.success {{color: #0b6;}}
    #delete-message.error {{color: #c00;}}
  </style>
</head>
<body>
<div class="container">
  <h1>🗂 Mission Board</h1>
  <section class="info-card">
    <h2>Research Topics</h2>
    {research_html}
    <details style="margin-top:0.75rem;">
      <summary style="cursor:pointer;font-weight:600;color:#2563eb;">Edit research topic</summary>
      <form id="research-edit-form" style="margin-top:0.6rem;">
        <textarea name="content" rows="10">{html_lib.escape(research_content)}</textarea>
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
          <button type="submit">Save</button>
          <button type="button" id="research-cancel-button">Cancel</button>
        </div>
      </form>
      <div id="research-message" aria-live="polite"></div>
    </details>
  </section>
  <section class="info-card">
    <h2>Latest Agent Log</h2>
    {latest_log_html}
  </section>
  <p style="color:#6b7280;font-size:0.9rem;">Total tasks tracked: <strong style="color:#111;">{total_tasks}</strong></p>
  <div id="delete-message" aria-live="polite"></div>
  {"".join(state_sections_html)}
  <hr class="divider">
  <section class="form-card">
    <h2>➕ Create a task</h2>
    <p>Edit the markdown template below and submit to save a new task into the <strong>backlog</strong>. Move it to inbox when it is ready for execution.</p>
    <form id="create-task-form">
      <label style="font-weight:600;">
        Task markdown
        <textarea name="markdown_content" required rows="30" style="font-family: monospace; font-size: 0.9rem; width: 100%; box-sizing: border-box; resize: vertical; min-height: 400px;">{task_template_default}</textarea>
      </label>
      <button type="submit">Create task</button>
    </form>
    <div id="form-message" aria-live="polite"></div>
  </section>
  <script>
    const researchForm = document.getElementById("research-edit-form");
    const researchMessage = document.getElementById("research-message");
    const researchTextarea = researchForm.querySelector("textarea[name='content']");
    const researchCancelButton = document.getElementById("research-cancel-button");
    let savedResearchContent = researchTextarea ? researchTextarea.value : "";
    researchForm.addEventListener("submit", async (event) => {{
      event.preventDefault();
      researchMessage.textContent = "Saving…";
      researchMessage.className = "";
      try {{
        const response = await fetch("/mission/update-research-topic", {{
          method: "POST",
          body: new URLSearchParams(new FormData(researchForm)),
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.detail || payload.message || "Unable to save research topic.");
        }}
        savedResearchContent = researchTextarea ? researchTextarea.value : savedResearchContent;
        researchMessage.textContent = payload.message || "Saved.";
        researchMessage.className = "success";
        setTimeout(() => {{ window.location.reload(); }}, 1200);
      }} catch (error) {{
        researchMessage.textContent = error.message || "Unable to save research topic.";
        researchMessage.className = "error";
      }}
    }});
    if (researchCancelButton && researchTextarea) {{
      researchCancelButton.addEventListener("click", () => {{
        researchTextarea.value = savedResearchContent;
        researchMessage.textContent = "Changes discarded.";
        researchMessage.className = "";
        setTimeout(() => {{ researchMessage.textContent = ""; }}, 1500);
      }});
    }}
    const form = document.getElementById("create-task-form");
    const message = document.getElementById("form-message");
    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      message.textContent = "Creating task…";
      message.className = "";
      try {{
        const response = await fetch("/mission/create-task", {{
          method: "POST",
          body: new URLSearchParams(new FormData(form)),
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.detail || payload.message || "Unable to create task.");
        }}
        message.textContent = `Created file ${{payload.filename || payload.path || "new task"}}. Reloading...`;
        message.className = "message success";
        form.reset();
        setTimeout(() => {{
          window.location.reload();
        }}, 1200);
      }} catch (error) {{
        message.textContent = error.message || "Unable to create task.";
        message.className = "message error";
      }}
    }});
    const deleteMessage = document.getElementById("delete-message");
    const setDeleteMessage = (text, type = "") => {{
      deleteMessage.textContent = text;
      deleteMessage.className = type;
    }};
    document.querySelectorAll(".delete-task-button").forEach((button) => {{
      button.addEventListener("click", async () => {{
        const targetPath = button.dataset.path;
        if (!targetPath) {{
          return;
        }}
        if (!window.confirm("Delete backlog task " + targetPath + "?")) {{
          return;
        }}
        setDeleteMessage("Deleting " + targetPath + "…", "");
        try {{
          const response = await fetch("/mission/delete-task", {{
            method: "POST",
            body: new URLSearchParams({{ path: targetPath }}),
          }});
          const payload = await response.json();
          if (!response.ok) {{
            throw new Error(payload.detail || payload.message || "Unable to delete task.");
          }}
          setDeleteMessage(payload.message || "Deleted " + targetPath + ".", "success");
          setTimeout(() => {{
            window.location.reload();
          }}, 1200);
        }} catch (error) {{
          setDeleteMessage(error.message || "Unable to delete task.", "error");
        }}
      }});
    }});
    document.querySelectorAll(".move-task-button").forEach((button) => {{
      button.addEventListener("click", async () => {{
        const targetPath = button.dataset.path;
        const label = button.dataset.label || "Move";
        if (!targetPath) {{
          return;
        }}
        setDeleteMessage(label + ": " + targetPath + "…", "");
        try {{
          const response = await fetch("/mission/move-task", {{
            method: "POST",
            body: new URLSearchParams({{ path: targetPath }}),
          }});
          const payload = await response.json();
          if (!response.ok) {{
            throw new Error(payload.detail || payload.message || "Unable to move task.");
          }}
          setDeleteMessage(payload.message || label + " succeeded.", "success");
          setTimeout(() => {{
            window.location.reload();
          }}, 1200);
        }} catch (error) {{
          setDeleteMessage(error.message || "Unable to move task.", "error");
        }}
      }});
    }});
  </script>
</div>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@app.post("/mission/update-research-topic")
def update_research_topic(content: str = Form(...)):
    """Update the research topics file with the provided content."""
    safe_content = content.strip()
    _write_research_topics(safe_content + "\n" if safe_content else "")
    return {"status": "ok", "message": "Research topic updated."}


@app.post("/mission/delete-task")
def delete_task(path: str = Form(...)):
    _ensure_task_workspace()
    task_file = _resolve_task_file(path)
    try:
        relative_path = task_file.relative_to(TASK_WORKSPACE)
    except ValueError:
        raise HTTPException(status_code=500, detail="Task path resolution failed.")
    if not relative_path.parts or relative_path.parts[0] != "backlog":
        raise HTTPException(status_code=400, detail="Delete action is only allowed for tasks in backlog.")
    try:
        task_file.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to delete task: {exc}")
    return {
        "status": "ok",
        "message": f"Deleted {relative_path}."
    }


@app.post("/mission/move-task")
def move_task(path: str = Form(...)):
    _ensure_task_workspace()
    task_file = _resolve_task_file(path)
    try:
        relative_path = task_file.relative_to(TASK_WORKSPACE)
    except ValueError:
        raise HTTPException(status_code=500, detail="Task path resolution failed.")
    if not relative_path.parts:
        raise HTTPException(status_code=400, detail="Invalid task path.")
    source_bucket = relative_path.parts[0]
    target_bucket = MOVE_ALLOWED.get(source_bucket)
    if not target_bucket:
        raise HTTPException(
            status_code=400,
            detail=f"Move is not allowed from '{source_bucket}'. Only backlog↔inbox moves are supported."
        )
    target_dir = TASK_WORKSPACE / target_bucket
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / task_file.name
    if target_file.exists():
        raise HTTPException(
            status_code=409,
            detail=f"A task with this filename already exists in {target_bucket}/."
        )
    try:
        task_file.rename(target_file)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to move task: {exc}")
    new_relative = target_file.relative_to(TASK_WORKSPACE)
    return {
        "status": "ok",
        "message": f"Moved {relative_path} → {new_relative}.",
        "path": str(new_relative),
    }


@app.get("/mission/task", response_class=HTMLResponse)
def mission_task(path: str):
    _ensure_task_workspace()
    task_file = _resolve_task_file(path)
    content = task_file.read_text(encoding="utf-8")
    escaped_content = html_lib.escape(content)
    try:
        relative_path = task_file.relative_to(TASK_WORKSPACE)
    except ValueError:
        relative_path = task_file

    html_content = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <title>Task detail: {html_lib.escape(str(relative_path))}</title>
  <style>
    body {{font-family: system-ui, sans-serif; margin: 1.5rem;}}
    pre {{background: #111827; color: #f8fafc; padding: 1rem; border-radius: 6px; max-width: 900px; white-space: pre-wrap; font-family: Menlo, Consolas, monospace;}}
    a {{display: inline-block; margin-bottom: 1rem;}}
  </style>
</head>
<body>
  <a href=\"/mission-board\">← Back to mission board</a>
  <h1>Task preview</h1>
  <p><strong>File:</strong> <code>{html_lib.escape(str(relative_path))}</code></p>
  <pre>{escaped_content}</pre>
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


@app.post("/mission/create-task")
def create_task(
    markdown_content: str = Form(...),
) -> dict:
    content = markdown_content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Task content must not be empty.")

    # Extract title from ## Title section, or fall back to # Task: heading
    title_text = _extract_section(content, "Title").strip()
    if not title_text:
        for line in content.splitlines():
            if line.startswith("# Task:"):
                title_text = line[len("# Task:"):].strip()
                break
    title_text = title_text or "untitled-task"

    _ensure_task_workspace()
    backlog_dir = TASK_WORKSPACE / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify_title(title_text)
    filename = _generate_task_filename(slug)
    task_path = backlog_dir / filename

    task_path.write_text(content, encoding="utf-8")
    try:
        relative_path = task_path.relative_to(TASK_WORKSPACE)
    except ValueError:
        relative_path = task_path

    return {
        "status": "ok",
        "filename": filename,
        "path": str(relative_path),
    }
