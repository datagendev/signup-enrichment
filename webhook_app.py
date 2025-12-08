import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel
import asyncio
import httpx
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    ToolUseBlock,
    query,
)

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


async def run_agent_sdk(request_id: str, email: str, system_prompt: str, user_message: str, datagen_key: str) -> str:
    """Use Anthropic Agent SDK to stream MCP interaction."""
    opts = ClaudeAgentOptions(
        model="claude-sonnet-4-5",
        system=system_prompt,
        mcp_servers={
            "datagen": {
                "type": "sse",
                "url": "https://mcp.datagen.dev/mcp",
                "headers": {"Authorization": f"Bearer {datagen_key.strip()}"},
            }
        },
        # allow full toolset; permissioning handled by MCP
    )

    collected: list[str] = []
    try:
        async for msg in query(prompt=user_message, options=opts):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text = block.text
                        collected.append(text)
                        log_event(
                            "agent_chunk",
                            request_id=request_id,
                            email=email,
                            chunk=text[:500],
                            truncated=len(text) > 500,
                        )
                    elif isinstance(block, ToolUseBlock):
                        log_event(
                            "agent_tool_use",
                            request_id=request_id,
                            email=email,
                            name=block.name,
                            input=block.input,
                        )
            else:
                # non-assistant messages (e.g., system or tool results) can be logged for debug
                log_event("agent_event", request_id=request_id, email=email, event=str(msg))
    except Exception as e:
        log_event("http_stream_error", request_id=request_id, email=email, error=str(e))
    return "".join(collected)


def stream_raw_mcp(request_id: str, email: str, system_prompt: str, user_message: str, anthropic_key: str, datagen_key: str) -> str:
    """Sync wrapper to run the async agent SDK from background task."""
    return asyncio.run(
        run_agent_sdk(
            request_id=request_id,
            email=email,
            system_prompt=system_prompt,
            user_message=user_message,
            datagen_key=datagen_key,
        )
    )
