import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel
import httpx

app = FastAPI()


PROMPT_PATH = Path(__file__).resolve().parent / ".claude" / "agents" / "enrichment-sop-executor.md"
PROJECT_ID = "rough-base-02149126"
DATABASE_NAME = "datagen"

# Structured logger to keep Render logs easy to filter and parse
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("enrichment_webhook")


class SignupPayload(BaseModel):
    email: str
    # Optional: add other fields like first_name, last_name if your webhook sends them
    # first_name: str | None = None
    # last_name: str | None = None

def run_enrichment_task(email: str):
    """
    Background task to enrich the user profile using Anthropic + Datagen MCP.
    """
    request_id = str(uuid.uuid4())
    log_event("start", request_id=request_id, email=email)
    
    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    datagen_key = (os.getenv("DATAGEN_API_KEY") or "").strip()

    if not anthropic_key:
        log_event("config_error", request_id=request_id, error="ANTHROPIC_API_KEY not set")
        return
    if not datagen_key:
        log_event("config_error", request_id=request_id, error="DATAGEN_API_KEY not set")
        return

    system_prompt = _load_prompt()

    user_message = f"""
Run the Enrichment SOP for the single signup email below. Follow the SOP verbatim (7 steps, validation rules, and method classification). Use only Datagen MCP tools to execute the steps and to update CRM.

Email: {email}

Database update requirements:
- Use mcp_Neon_run_sql against projectId "{PROJECT_ID}" and database "{DATABASE_NAME}".
- Target table: crm. Match rows using the exact email value.
- If a LinkedIn profile is validated, store linkedin_url, headline/title, location fields, confidence, and method.
- If not found, still record method="not_found" and attempts per SOP.

Output requirements:
- Return a concise JSON summary (email, method, linkedin_url if any, headline/title, location, confidence, attempts or notes).
- Keep explanations brief; avoid verbose narratives.
"""

    try:
        chunks: list[str] = []

        # Stream the response so Render logs show progress in real time
        # Non-streaming to avoid Anthropic SDK MCP streaming parse errors; log full response
        # Stream raw SSE to avoid SDK MCP block parsing issues
        agent_text = stream_raw_mcp(
            request_id=request_id,
            email=email,
            system_prompt=system_prompt,
            user_message=user_message,
            anthropic_key=anthropic_key,
            datagen_key=datagen_key,
        )

        if agent_text:
            chunks.append(agent_text)

        agent_text = "".join(chunks)
        log_event("success", request_id=request_id, email=email)
        if agent_text:
            log_event(
                "agent_response",
                request_id=request_id,
                email=email,
                text=agent_text[:2000],
                truncated=len(agent_text) > 2000,
            )

    except Exception as e:
        log_event("error", request_id=request_id, email=email, error=str(e))

@app.post("/webhook/signup")
async def receive_signup(payload: SignupPayload, background_tasks: BackgroundTasks):
    """
    Receives a signup event (JSON) and triggers enrichment in the background.
    Expected JSON: {"email": "user@example.com"}
    """
    background_tasks.add_task(run_enrichment_task, payload.email)
    return {"status": "accepted", "message": f"Enrichment queued for {payload.email}"}

@app.get("/health")
def health():
    return {"status": "ok"}


def _load_prompt() -> str:
    """Load the SOP executor prompt from disk, with a small fallback."""
    try:
        raw = PROMPT_PATH.read_text(encoding="utf-8")
        # Drop the optional "Before You Start" preamble to keep the API payload lean
        sentinel = "## Before You Start"
        return raw.split(sentinel, 1)[0].rstrip()
    except FileNotFoundError:
        return "You are an enrichment SOP executor. Follow the documented seven-step process to find and validate a LinkedIn profile for a single email, then classify the method and update CRM via Datagen MCP."


def log_event(event: str, **data):
    """Emit a single-line JSON log for easier filtering in Render."""
    payload = {"event": event, **data}
    logger.info(json.dumps(payload))


def stream_raw_mcp_iter(request_id: str, email: str, system_prompt: str, user_message: str, anthropic_key: str, datagen_key: str):
    """
    Yield completed content blocks (text only) from Anthropic MCP streaming.
    We buffer deltas per content block index and emit when content_block_stop arrives,
    so logs aren't word-by-word.
    """
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": anthropic_key.strip(),
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "mcp-client-2025-04-04",
    }
    body = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 1200,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
        "mcp_servers": [
            {
                "type": "url",
                "url": "https://mcp.datagen.dev/mcp",
                "name": "datagen",
                "authorization_token": datagen_key.strip(),
            }
        ],
        "tools": [
            {
                "type": "mcp_toolset",
                "mcp_server_name": "datagen",
                "default_config": {
                    "enabled": False,
                    "defer_loading": False,
                },
                "configs": {
                    "getToolDetails": {"enabled": True},
                    "executeTool": {"enabled": True},
                },
            }
        ],
        "stream": True,
    }

    timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=None)
    buffers: dict[int, dict[str, list[str]]] = {}

    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", url, headers=headers, json=body) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                line_str = line.decode() if isinstance(line, (bytes, bytearray)) else str(line)
                if not line_str.startswith("data:"):
                    continue
                data = line_str[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                    ptype = payload.get("type")
                    if ptype == "content_block_delta":
                        idx = payload.get("index", 0)
                        delta = payload.get("delta", {})
                        dtype = delta.get("type")
                        if dtype == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                buffers.setdefault(idx, {"kind": "text", "parts": []})["parts"].append(text)
                        elif dtype == "input_json_delta":
                            part = delta.get("partial_json", "")
                            if part:
                                buffers.setdefault(idx, {"kind": "json", "parts": []})["parts"].append(part)
                    elif ptype == "content_block_stop":
                        idx = payload.get("index", 0)
                        buf = buffers.pop(idx, None)
                        if buf and buf.get("parts"):
                            joined = "".join(buf["parts"])
                            if buf.get("kind") == "json":
                                # best-effort parse
                                try:
                                    parsed = json.loads(joined)
                                    joined = json.dumps(parsed)
                                except Exception:
                                    pass
                            log_event(
                                "agent_chunk",
                                request_id=request_id,
                                email=email,
                                chunk=joined[:500],
                                truncated=len(joined) > 500,
                            )
                            yield joined
                except Exception as e:
                    log_event("agent_chunk_parse_error", request_id=request_id, email=email, error=str(e))
                    continue


def stream_raw_mcp(request_id: str, email: str, system_prompt: str, user_message: str, anthropic_key: str, datagen_key: str) -> str:
    """Collect all text from streaming iterator."""
    chunks: list[str] = []
    try:
        for text in stream_raw_mcp_iter(request_id, email, system_prompt, user_message, anthropic_key, datagen_key):
            chunks.append(text)
    except Exception as e:
        log_event("http_stream_error", request_id=request_id, email=email, error=str(e))
    return "".join(chunks)
