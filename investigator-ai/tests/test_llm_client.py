"""Message-content flattening: newer Gemini models return typed content blocks, not str."""

from __future__ import annotations

from investigator_ai.llm.client import _text_of


class _Msg:
    def __init__(self, content):
        self.content = content


def test_plain_string_passes_through():
    assert _text_of(_Msg("hello")) == "hello"


def test_list_of_text_blocks_is_concatenated():
    msg = _Msg(
        [
            {"type": "text", "text": "Duplicate billing "},
            {"type": "text", "text": "is the strongest signal."},
        ]
    )
    assert _text_of(msg) == "Duplicate billing is the strongest signal."


def test_non_text_blocks_and_signatures_are_dropped():
    msg = _Msg(
        [
            {"type": "text", "text": "answer", "extras": {"signature": "AAAA...."}},
            {"type": "thinking", "thinking": "hidden"},
        ]
    )
    assert _text_of(msg) == "answer"


def test_bare_string_argument():
    assert _text_of("x") == "x"
