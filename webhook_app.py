import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from anthropic import Anthropic

# Optional LangSmith tracing
try:
    from langsmith import Client as LangSmithClient  # type: ignore
    from langsmith import wrappers as ls_wrappers  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    LangSmithClient = None
    ls_wrappers = None

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

    trace_ctx = start_trace(request_id=request_id, email=email)
    
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    datagen_key = os.getenv("DATAGEN_API_KEY")

    if not anthropic_key:
        log_event("config_error", request_id=request_id, error="ANTHROPIC_API_KEY not set")
        return
    if not datagen_key:
        log_event("config_error", request_id=request_id, error="DATAGEN_API_KEY not set")
        return

    client = Anthropic(api_key=anthropic_key)
    # Auto-wrap Anthropic client for LangSmith tracing if configured
    if ls_wrappers and os.getenv("LANGSMITH_API_KEY") and os.getenv("LANGSMITH_TRACING", "false").lower() == "true":
        try:
            client = ls_wrappers.wrap_anthropic(
                client,
                tracing_extra={
                    "tags": ["webhook", "anthropic", "mcp"],
                },
            )
        except Exception as e:  # best-effort
            log_event("langsmith_error", request_id=request_id, email=email, error=str(e))

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
        response = client.beta.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1200,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            mcp_servers=[
                {
                    "type": "url",
                    "url": "https://mcp.datagen.dev/mcp",
                    "name": "datagen",
                    "authorization_token": datagen_key,
                }
            ],
            betas=["mcp-client-2025-04-04"],
            stream=False,
        )

        # Log the raw response (JSON-safe)
        try:
            log_event(
                "agent_raw_response",
                request_id=request_id,
                email=email,
                response_json=response.model_dump(),
            )
        except Exception:
            pass

        if response and response.content:
            for block in response.content:
                if getattr(block, "type", "") == "text" and getattr(block, "text", None):
                    chunks.append(block.text)

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

        finish_trace(
            trace_ctx,
            status="success",
            outputs={
                "email": email,
                "agent_response": agent_text[:2000],
                "truncated": len(agent_text) > 2000,
            },
        )

    except Exception as e:
        log_event("error", request_id=request_id, email=email, error=str(e))
        finish_trace(trace_ctx, status="error", error=str(e))

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


def start_trace(request_id: str, email: str):
    """Start a LangSmith trace if configured."""
    if not LangSmithClient or not os.getenv("LANGSMITH_API_KEY"):
        return None
    try:
        client = LangSmithClient()
        project = os.getenv("LANGSMITH_PROJECT", "signup-enrichment")
        run_id = client.create_run(
            name="enrichment-webhook",
            run_type="chain",
            inputs={"email": email},
            project=project,
            start_time=datetime.now(timezone.utc),
            tags=["webhook", "anthropic", "mcp"],
            reference_example_id=request_id,
        )
        return {"client": client, "run_id": run_id, "start_time": datetime.now(timezone.utc)}
    except Exception as e:  # best-effort
        log_event("langsmith_error", request_id=request_id, email=email, error=str(e))
        return None


def finish_trace(ctx, status: str, outputs: dict | None = None, error: str | None = None):
    if not ctx:
        return
    try:
        client = ctx["client"]
        run_id = ctx["run_id"]
        end_time = datetime.now(timezone.utc)
        client.update_run(
            run_id=run_id,
            outputs=outputs or {},
            error=error,
            end_time=end_time,
            status=status,
        )
    except Exception as e:  # best-effort
        log_event("langsmith_error", error=str(e))
