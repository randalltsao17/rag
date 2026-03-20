#!/usr/bin/env bash
set -euo pipefail

QUESTION="${1:-}"
TOP_K="${2:-3}"

echo "$TOP_K"

if [ -z "$QUESTION" ]; then
  echo "Usage: ./ask.sh \"your question\" [top_k]"
  exit 1
fi

curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg q "$QUESTION" --argjson k "$TOP_K" '{question:$q, top_k:$k}')" \
| jq -r '.answer'
