"""Simulate Meta webhook POST for local testing.

Fires real-looking payloads against a Modal `-dev` endpoint.

Usage:
    python execution/simulate_webhook.py --endpoint https://your-app--webhook-post-dev.modal.run
    python execution/simulate_webhook.py --endpoint https://your-app--webhook-post-dev.modal.run --text "Quanto custa a consulta?"
"""
from __future__ import annotations

import argparse
import httpx
import json
import time
import sys


def build_text_payload(sender_id: str, text: str) -> dict:
    """Build a webhook payload that mimics a real Instagram text message."""
    return {
        "object": "instagram",
        "entry": [{
            "time": int(time.time() * 1000),
            "id": "17841471503215852",
            "messaging": [{
                "sender": {"id": sender_id},
                "recipient": {"id": "17841471503215852"},
                "timestamp": int(time.time() * 1000),
                "message": {
                    "mid": f"simulated_{int(time.time())}",
                    "text": text,
                },
            }],
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate Instagram webhook POST")
    parser.add_argument("--endpoint", required=True, help="Modal webhook URL")
    parser.add_argument("--text", default="Olá doutor, tudo bem?", help="Message text")
    parser.add_argument("--sender", default="test_sender_123", help="Sender ID")

    args = parser.parse_args()

    payload = build_text_payload(args.sender, args.text)
    print(f"Sending to: {args.endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")

    response = httpx.post(args.endpoint, json=payload, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

    if response.status_code == 200:
        print("Webhook accepted successfully")
    else:
        print("Webhook rejected")
        sys.exit(1)


if __name__ == "__main__":
    main()
