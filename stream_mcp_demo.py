"""
Small one-off script to inspect Anthropic + MCP streaming output.
Requires env vars: ANTHROPIC_API_KEY, DATAGEN_API_KEY.
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
        print("Missing ANTHROPIC_API_KEY or DATAGEN_API_KEY in environment", file=sys.stderr)
        sys.exit(1)

    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": (
                    "MCP smoke test: \n"
                    "1) List Datagen MCP tools that relate to LinkedIn.\n"
                    "2) If a search/profile tool exists, use it to look up the company 'Anthropic' "
                    "and summarize the top result (name, url, employees, headline) without writing to any DB.\n"
                    "Respond concisely."
                ),
            }
        ],
        "mcp_servers": [
            {
                "type": "url",
                "url": "https://mcp.datagen.dev/mcp",
                "name": "datagen",
                "authorization_token": datagen_key,
            }
        ],
        # tools array is not needed for MCP connector
        "stream": True,
    }

    print("Sending request...", file=sys.stderr)
    timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=None)

    with httpx.stream(
        "POST",
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": anthro_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "mcp-client-2025-04-04",
            "User-Agent": "stream-mcp-demo/1.0",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json=payload,
        timeout=timeout,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            line_str = line.decode() if isinstance(line, (bytes, bytearray)) else str(line)
            if not line_str.startswith("data:"):
                continue
            data = line_str[5:].strip()
            if data == "[DONE]":
                print("STREAM DONE")
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                print(f"RAW {data!r}")
                continue

            etype = event.get("type")
            # print compact view of deltas and tool calls
            if etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    print(f"TEXTΔ: {text}", end="", flush=True)
                else:
                    print(f"BLOCKΔ: {delta}")
            elif etype == "message_start":
                print(f"\nMESSAGE START id={event.get('message', {}).get('id')}")
            elif etype == "message_delta":
                print("\nMESSAGE DELTA", event.get("delta"))
            elif etype == "message_stop":
                print("\nMESSAGE STOP")
            elif etype == "content_block_start":
                block = event.get("content_block", {})
                print(f"\nBLOCK START {block.get('type')}")
            elif etype == "content_block_stop":
                print("\nBLOCK STOP")
            elif etype == "error":
                print(f"\nERROR: {event}")
            else:
                print(f"\nEVENT {etype}: {event}")


if __name__ == "__main__":
    main()
