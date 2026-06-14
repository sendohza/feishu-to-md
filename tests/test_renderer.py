# -*- coding: utf-8 -*-
"""Tests for feishu_to_md.renderer module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feishu_to_md.renderer import extract_inline, _render_block, blocks_to_markdown
from feishu_to_md.api import (
    BT_TEXT, BT_H1, BT_H2, BT_BULLET, BT_ORDERED,
    BT_TODO, BT_CODE, BT_QUOTE, BT_DIVIDER, BT_IMAGE,
)


# --- extract_inline tests ---

def test_extract_inline_plain():
    elements = [{"text_run": {"content": "Hello world"}}]
    result = extract_inline(elements)
    assert result == "Hello world"


def test_extract_inline_bold():
    elements = [{"text_run": {"content": "bold", "text_element_style": {"bold": True}}}]
    result = extract_inline(elements)
    assert result == "**bold**"


def test_extract_inline_italic():
    elements = [{"text_run": {"content": "italic", "text_element_style": {"italic": True}}}]
    result = extract_inline(elements)
    assert result == "*italic*"


def test_extract_inline_strikethrough():
    elements = [{"text_run": {"content": "deleted", "text_element_style": {"strikethrough": True}}}]
    result = extract_inline(elements)
    assert result == "~~deleted~~"


def test_extract_inline_code():
    elements = [{"text_run": {"content": "code()", "text_element_style": {"inline_code": True}}}]
    result = extract_inline(elements)
    assert result == "`code()`"


def test_extract_inline_link():
    elements = [{"text_run": {"content": "click", "text_element_style": {"link": {"url": "https://example.com"}}}}]
    result = extract_inline(elements)
    assert result == "[click](https://example.com)"


def test_extract_inline_mixed():
    elements = [
        {"text_run": {"content": "plain"}},
        {"text_run": {"content": "bold", "text_element_style": {"bold": True}}},
        {"text_run": {"content": "text"}},
    ]
    result = extract_inline(elements)
    assert result == "plain**bold**text"


def test_extract_inline_none():
    assert extract_inline(None) == ""
    assert extract_inline([]) == ""


# --- _render_block tests ---

def test_render_block_h1():
    item = {
        "block_type": BT_H1,
        "text_run": {"elements": [{"text_run": {"content": "Title"}}]},
    }
    result = _render_block(item)
    assert result == "# Title"


def test_render_block_h2():
    item = {
        "block_type": BT_H2,
        "text_run": {"elements": [{"text_run": {"content": "Section"}}]},
    }
    result = _render_block(item)
    assert result == "## Section"


def test_render_block_bullet():
    item = {
        "block_type": BT_BULLET,
        "text_run": {"elements": [{"text_run": {"content": "Item one"}}]},
    }
    result = _render_block(item)
    assert result == "- Item one"


def test_render_block_ordered():
    item = {
        "block_type": BT_ORDERED,
        "index": 1,
        "text_run": {"elements": [{"text_run": {"content": "First"}}]},
    }
    result = _render_block(item)
    assert result == "1. First"


def test_render_block_todo_done():
    item = {
        "block_type": BT_TODO,
        "todo": {"done": True},
        "text_run": {"elements": [{"text_run": {"content": "Done task"}}]},
    }
    result = _render_block(item)
    assert result == "- [x] Done task"


def test_render_block_todo_pending():
    item = {
        "block_type": BT_TODO,
        "todo": {"done": False},
        "text_run": {"elements": [{"text_run": {"content": "Pending task"}}]},
    }
    result = _render_block(item)
    assert result == "- [ ] Pending task"


def test_render_block_code():
    item = {
        "block_type": BT_CODE,
        "code": {"language": "python"},
        "text_run": {"elements": [
            {"text_run": {"content": "def hello():\n"}},
            {"text_run": {"content": "    print('world')\n"}},
        ]},
    }
    result = _render_block(item)
    assert "```python" in result
    assert "def hello():" in result
    assert "```" in result


def test_render_block_quote():
    item = {
        "block_type": BT_QUOTE,
        "quote": {},
        "text_run": {"elements": [{"text_run": {"content": "Quote text"}}]},
    }
    result = _render_block(item)
    assert result == "> Quote text"


def test_render_block_divider():
    item = {"block_type": BT_DIVIDER}
    result = _render_block(item)
    assert result == "---"


def test_render_block_image():
    item = {"block_type": BT_IMAGE, "image": {"token": "img_token_123"}}
    result = _render_block(item)
    assert "![img_token_123]" in result
    assert "internal-api-drive-stream.feishu.cn" in result


def test_render_block_callout():
    item = {
        "block_type": 23,
        "callout": {"type": "warning"},
        "text_run": {"elements": [{"text_run": {"content": "Be careful!"}}]},
    }
    result = _render_block(item)
    assert "> [!warning]" in result


def test_render_block_empty():
    item = {"block_type": BT_TEXT}
    result = _render_block(item)
    assert result == ""


def test_render_block_unsupported_type():
    item = {
        "block_type": 99,
        "text_run": {"elements": [{"text_run": {"content": "weird"}}]},
    }
    result = _render_block(item)
    assert result == "weird"


# --- blocks_to_markdown tests ---

def test_blocks_to_markdown():
    blocks = [
        {"block_type": 1, "block_id": "root", "children": ["b1", "b2"]},
        {"block_id": "b1", "block_type": BT_H1, "parent_id": "root",
         "text_run": {"elements": [{"text_run": {"content": "Heading"}}]}},
        {"block_id": "b2", "block_type": BT_TEXT, "parent_id": "root",
         "text_run": {"elements": [{"text_run": {"content": "Body text"}}]}},
    ]
    result = blocks_to_markdown(blocks)
    assert "# Heading" in result
    assert "Body text" in result


def test_blocks_to_markdown_no_root():
    blocks = [
        {"block_type": BT_TEXT, "text_run": {"elements": [{"text_run": {"content": "Orphan text"}}]}},
    ]
    result = blocks_to_markdown(blocks)
    assert "Orphan text" in result


def test_blocks_to_markdown_normalize_spacing():
    blocks = [
        {"block_type": 1, "block_id": "r", "children": ["b1", "b2", "b3"]},
        {"block_id": "b1", "block_type": BT_TEXT, "parent_id": "r",
         "text_run": {"elements": [{"text_run": {"content": "A"}}]}},
        {"block_id": "b2", "block_type": BT_TEXT, "parent_id": "r",
         "text_run": {"elements": [{"text_run": {"content": "B"}}]}},
        {"block_id": "b3", "block_type": BT_TEXT, "parent_id": "r",
         "text_run": {"elements": [{"text_run": {"content": "C"}}]}},
    ]
    result = blocks_to_markdown(blocks)
    assert "\n\n\n" not in result


def test_render_block_nested_list_indent():
    blocks = [
        {"block_type": 1, "block_id": "root", "children": ["parent"]},
        {"block_id": "parent", "block_type": BT_BULLET, "parent_id": "root",
         "text_run": {"elements": [{"text_run": {"content": "Parent item"}}]}},
        {"block_id": "child1", "block_type": BT_BULLET, "parent_id": "parent",
         "text_run": {"elements": [{"text_run": {"content": "Nested"}}]}},
    ]
    result = blocks_to_markdown(blocks)
    assert "  - Nested" in result
