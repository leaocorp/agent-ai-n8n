"""Tests for the webhook handler."""
import pytest
from execution.webhook_handler import verify_webhook, parse_post_body
from execution.config import Config


def test_verify_webhook_returns_challenge(test_config: Config) -> None:
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "test_token",
        "hub.challenge": "challenge_abc",
    }
    result = verify_webhook(params, test_config)
    assert result == "challenge_abc"


def test_verify_webhook_rejects_bad_token(test_config: Config) -> None:
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token",
        "hub.challenge": "challenge_abc",
    }
    result = verify_webhook(params, test_config)
    assert result is None


def test_parse_post_body_extracts_messaging() -> None:
    body = {
        "object": "instagram",
        "entry": [{"messaging": [{"sender": {"id": "s1"}}]}],
    }
    assert parse_post_body(body) is True


def test_parse_post_body_rejects_non_instagram() -> None:
    body = {"object": "page", "entry": []}
    assert parse_post_body(body) is False
