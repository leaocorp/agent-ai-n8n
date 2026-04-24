import os
import pytest
from execution.config import get_config, Config


def test_get_config_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_VERIFY_TOKEN", "abc123")
    monkeypatch.setenv("BLOCKED_SENDER_IDS", "id1,id2,id3")
    cfg = get_config()
    assert cfg.meta_verify_token == "abc123"
    assert cfg.blocked_sender_ids == frozenset({"id1", "id2", "id3"})


def test_config_is_immutable() -> None:
    cfg = Config()
    with pytest.raises(AttributeError):
        cfg.meta_page_id = "new_id"  # type: ignore[misc]


def test_empty_blocklist_yields_empty_frozenset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLOCKED_SENDER_IDS", "")
    cfg = get_config()
    assert cfg.blocked_sender_ids == frozenset()
