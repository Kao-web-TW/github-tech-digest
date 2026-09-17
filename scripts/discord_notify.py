"""Build and send the daily Discord webhook notification."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


def build_discord_payload(selected: list, artifact_url: str) -> dict:
    """Build a Discord webhook payload summarizing today's picks."""
    if not selected:
        description = "今日無顯著新工具。"
    else:
        description = "\n".join(
            f"**{item['full_name']}** (★{item['stars']}) — {item['reason']}"
            for item in selected
        )
    return {
        "embeds": [
            {
                "title": "GitHub 新技術每日精選",
                "description": description,
                "url": artifact_url,
                "color": 5814783,
            }
        ]
    }


def send_discord_notification(webhook_url: str, payload: dict) -> bool:
    """POST the payload to the Discord webhook. Returns True on success, False on failure."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


if __name__ == "__main__":
    payload_path = Path(sys.argv[1])
    loaded_payload = json.loads(payload_path.read_text(encoding="utf-8"))
    webhook = os.environ["DISCORD_WEBHOOK_URL"]
    ok = send_discord_notification(webhook, loaded_payload)
    print("ok" if ok else "failed")
    sys.exit(0 if ok else 1)
