"""Tests for Instagram media receiver."""
import pytest
from execution.instagram_receiver import InstagramReceiver, WebhookPayload


def test_parse_text_message() -> None:
    body = {
        "entry": [{"messaging": [{"sender": {"id": "s1"}, "recipient": {"id": "r1"},
            "timestamp": 1700000000000,
            "message": {"mid": "mid1", "text": "Olá doutor"}}]}]
    }
    payload = InstagramReceiver.parse_webhook(body)
    assert payload.sender_id == "s1"
    assert payload.text == "Olá doutor"
    assert payload.message_mid == "mid1"
    assert payload.attachment_type is None


def test_parse_audio_message() -> None:
    body = {
        "entry": [{"messaging": [{"sender": {"id": "s1"}, "recipient": {"id": "r1"},
            "timestamp": 1700000000000,
            "message": {"mid": "mid2", "attachments": [
                {"type": "audio", "payload": {"url": "https://cdn.example.com/audio.mp4"}}
            ]}}]}]
    }
    payload = InstagramReceiver.parse_webhook(body)
    assert payload.attachment_type == "audio"
    assert payload.attachment_url == "https://cdn.example.com/audio.mp4"
    assert payload.text is None


def test_parse_image_message() -> None:
    body = {
        "entry": [{"messaging": [{"sender": {"id": "s1"}, "recipient": {"id": "r1"},
            "timestamp": 1700000000000,
            "message": {"mid": "mid3", "attachments": [
                {"type": "image", "payload": {"url": "https://cdn.example.com/photo.jpg"}}
            ]}}]}]
    }
    payload = InstagramReceiver.parse_webhook(body)
    assert payload.attachment_type == "image"


def test_is_echo() -> None:
    body = {
        "entry": [{"messaging": [{"sender": {"id": "s1"}, "recipient": {"id": "r1"},
            "timestamp": 1700000000000,
            "message": {"mid": "mid4", "text": "test", "is_echo": True}}]}]
    }
    payload = InstagramReceiver.parse_webhook(body)
    assert payload.is_echo is True


def test_parse_missing_message_returns_none() -> None:
    body = {"entry": [{"messaging": [{"sender": {"id": "s1"}, "recipient": {"id": "r1"},
        "timestamp": 1700000000000}]}]}
    payload = InstagramReceiver.parse_webhook(body)
    assert payload is None
