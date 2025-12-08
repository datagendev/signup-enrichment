"""
Minimal MCP streaming probe.
Asks the Datagen MCP connector to list available tools (read-only).
Env vars required: ANTHROPIC_API_KEY, DATAGEN_API_KEY.
"""

import json
import os
import sys
import uuid

import httpx


def main():
    anthro_key = os.getenv("ANTHROPIC_API_KEY")
    datagen_key = os.getenv("DATAGEN_API_KEY")
    if not anthro_key or not datagen_key:
        print("Missing ANTHROPIC_API_KEY or DATAGEN_API_KEY", file=sys.stderr)
        sys.exit(1)

    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": (
                    "List the available tools from the Datagen MCP server, and tell me specifically "
                    "whether any tool related to LinkedIn lookup/search/profile ('linkup' or similar) is available. "
                    "Do not call any tool."
                ),
            }
        ],
        "stream": True,
        "mcp_servers": [
            {
                "type": "url",
                "url": "https://mcp.datagen.dev/mcp",
                "name": "datagen",
                "authorization_token": datagen_key,
            }
        ],
    }

    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=None)
    print("Sending minimal MCP request...", file=sys.stderr)
    with httpx.stream(
        "POST",
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": anthro_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "mcp-client-2025-04-04",
            "User-Agent": "stream-mcp-simple/1.0",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json=payload,
        timeout=timeout,
    ) as r:
        r.raise_for_status()
        print(f"HTTP {r.status_code}", file=sys.stderr)
        any_output = False
        for line in r.iter_lines():
            if not line:
                continue
            line_str = line.decode() if isinstance(line, (bytes, bytearray)) else str(line)
            if not line_str.startswith("data:"):
                continue
            data = line_str[5:].strip()
            if data == "[DONE]":
                print("\nSTREAM DONE")
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                print(f"\nRAW {data!r}")
                continue

            etype = event.get("type")
            if etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    print(delta.get("text", ""), end="", flush=True)
            elif etype == "message_start":
                print("\nMESSAGE START")
            elif etype == "message_stop":
                print("\nMESSAGE STOP")
            elif etype == "error":
                print(f"\nERROR: {event}")
            else:
                # keep the log compact
                print(f"\nEVENT {etype}: {event}")
            any_output = True
        if not any_output:
            print("\nNo SSE lines received (did the API disable streaming?). Try checking creds/headers.")


if __name__ == "__main__":
    main()
