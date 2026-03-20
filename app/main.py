import os
import hashlib
from pathlib import Path
from typing import List

from fastapi import FastAPI
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
