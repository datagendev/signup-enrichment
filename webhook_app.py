import os
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from anthropic import Anthropic

app = FastAPI()


PROMPT_PATH = Path(__file__).resolve().parent / ".claude" / "agents" / "enrichment-sop-executor.md"
PROJECT_ID = "rough-base-02149126"
DATABASE_NAME = "datagen"


class SignupPayload(BaseModel):
    email: str
    # Optional: add other fields like first_name, last_name if your webhook sends them
    # first_name: str | None = None
    # last_name: str | None = None

def run_enrichment_task(email: str):
    """
    Background task to enrich the user profile using Anthropic + Datagen MCP.
    """
    print(f"🚀 Starting enrichment for: {email}")
    
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    datagen_key = os.getenv("DATAGEN_API_KEY")

    if not anthropic_key:
        print("❌ Error: ANTHROPIC_API_KEY not set")
        return
    if not datagen_key:
        print("❌ Error: DATAGEN_API_KEY not set")
        return

    client = Anthropic(api_key=anthropic_key)

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
        # Use the newest mid-tier model; Sonnet 4.5 alias avoids 404s on older snapshots
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
        )

        print(f"✅ Enrichment completed for {email}")
        if response and response.content:
            print(f"📝 Agent Response:\n{response.content[0].text}")

    except Exception as e:
        print(f"❌ Error during enrichment task for {email}: {e}")

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
