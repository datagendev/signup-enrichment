"""Local smoke test for the webhook.

Usage:
  source venv/bin/activate
  export TEST_EMAIL=someone@example.com  # optional
  python test_webhook_local.py

Reads .env if present to pick up ANTHROPIC_API_KEY, DATAGEN_API_KEY, etc.
"""

import os
from pathlib import Path
import time

from fastapi.testclient import TestClient
from webhook_app import app

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover
    load_dotenv = None


def main():
    if load_dotenv:
        env_path = Path(".env")
        if env_path.exists():
            load_dotenv(env_path)

    os.environ.setdefault("LANGSMITH_TRACING", "true")

    email = os.environ.get("TEST_EMAIL", "kuoyusheng@gmail.com")
    client = TestClient(app)

    resp = client.post("/webhook/signup", json={"email": email})
    print("status", resp.status_code)
    print("json", resp.json())

    # Allow background task to finish and logs to flush
    wait_seconds = int(os.environ.get("TEST_WAIT_SECONDS", "8"))
    if wait_seconds > 0:
        print(f"Waiting {wait_seconds}s for background enrichment logs...")
        time.sleep(wait_seconds)


if __name__ == "__main__":
    main()
