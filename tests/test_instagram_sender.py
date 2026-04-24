"""Tests for Instagram message sender."""
import pytest
from execution.instagram_sender import InstagramSender


def test_split_response_by_newlines() -> None:
    text = "Oi, Maria! Como vai?\nFico feliz com seu interesse\nO que mais te incomoda?"
    parts = InstagramSender.split_response(text)
    assert parts == ["Oi, Maria! Como vai?", "Fico feliz com seu interesse", "O que mais te incomoda?"]


def test_split_filters_empty_parts() -> None:
    text = "Parte 1\n\n\nParte 2"
    parts = InstagramSender.split_response(text)
    assert parts == ["Parte 1", "Parte 2"]


def test_split_strips_trailing_dot() -> None:
    text = "Isso é um teste."
    parts = InstagramSender.split_response(text)
    assert parts == ["Isso é um teste"]


def test_empty_response_returns_empty_list() -> None:
    parts = InstagramSender.split_response("")
    assert parts == []
