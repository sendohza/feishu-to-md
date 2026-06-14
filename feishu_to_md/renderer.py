# -*- coding: utf-8 -*-
"""Renderer: convert Feishu block data to Markdown text."""
import re
import urllib.parse
import logging

from .api import (
    BT_TEXT, BT_H1, BT_H2, BT_H3, BT_H4, BT_H5, BT_H6,
    BT_BULLET, BT_ORDERED, BT_TODO, BT_CODE, BT_QUOTE,
    BT_DIVIDER, BT_IMAGE, BT_GRID, BT_GRID_COL,
    CALLOUT_MAP,
)

logger = logging.getLogger("feishu_to_md.renderer")

# Backtick character for inline code and code blocks
BACKTICK = chr(96)
TRIPLE_BACKTICK = BACKTICK * 3

_META_KEYS = frozenset({"block_id", "block_type", "parent_id", "children"})

# Content container keys (metadata-only, not text container) for each block type.
# These hold block-specific fields like "done", "language", "token", etc.
_BLOCK_META_KEYS = {
    BT_TODO: "todo",
    BT_CODE: "code",
    BT_QUOTE: "quote",
    BT_IMAGE: "image",
    23: "callout",
    11: "code",
    12: "todo",
}


def extract_inline(elements):
    """Extract formatted text from Feishu inline elements."""
    if not elements:
        return ""

    parts = []
    for e in elements:
        tr = e.get("text_run") or {}
        content = tr.get("content", "")
        if not content:
            continue

        style = tr.get("text_element_style") or {}
        link = style.get("link", {})

        if link and link.get("url"):
            parts.append(f"[{content.strip()}]({urllib.parse.unquote(link['url'])})")
            continue

        if style.get("bold"):
            content = f"**{content}**"
        if style.get("italic"):
            content = f"*{content}*"
        if style.get("strikethrough"):
            content = f"~~{content}~~"
        if style.get("inline_code"):
            content = f"{BACKTICK}{content}{BACKTICK}"
        if style.get("underline"):
            content = f"<u>{content}</u>"

        parts.append(content)

    return "".join(parts)


def _get_elements(item):
    """Get the elements list from a block item.

    Feishu API v1: item["text"]["elements"]  (elements inside text/code/image etc.)
    """
    bt = item.get("block_type", BT_TEXT)
    # Try the API v1 structure: item["text"]["elements"], item["code"]["elements"], etc.
    for key in ("text", "code", "quote", "todo", "callout", "image"):
        container = item.get(key)
        if isinstance(container, dict) and "elements" in container:
            return container["elements"]
    # Fallback: legacy structure item["text_run"]["elements"]
    tr = item.get("text_run")
    if isinstance(tr, dict) and "elements" in tr:
        return tr["elements"]
    return None


def _get_meta_dict(item):
    """Get the metadata dict from a block item (todo, code, image, callout, etc.)."""
    bt = item.get("block_type", BT_TEXT)
    meta_key = _BLOCK_META_KEYS.get(bt)
    if meta_key and meta_key in item:
        v = item[meta_key]
        return v if isinstance(v, dict) else {}
    # Also try direct key access
    for key in ("todo", "code", "quote", "image", "callout"):
        if key in item and isinstance(item[key], dict):
            return item[key]
    return {}


def _get_meta_dict(item):
    """Get the metadata dict from a block item (todo, code, image, callout, etc.)."""
    bt = item.get("block_type", BT_TEXT)
    meta_key = _BLOCK_META_KEYS.get(bt)
    if meta_key and meta_key in item:
        v = item[meta_key]
        return v if isinstance(v, dict) else {}
    return {}


def _render_block(item):
    """Convert a single Feishu block to a Markdown line."""
    bt = item.get("block_type", BT_TEXT)
    meta = _get_meta_dict(item)
    elements = _get_elements(item)
    text = extract_inline(elements)

    # Headings & text
    if bt == BT_TEXT:
        return text
    if bt == BT_H1:
        return f"# {text}"
    if bt == BT_H2:
        return f"## {text}"
    if bt == BT_H3:
        return f"### {text}"
    if bt == BT_H4:
        return f"#### {text}"
    if bt == BT_H5:
        return f"##### {text}"
    if bt == BT_H6:
        return f"###### {text}"

    # Lists
    if bt == BT_BULLET:
        return f"- {text}"
    if bt == BT_ORDERED:
        return f"{meta.get('index', 1)}. {text}"

    # Code block
    if bt == BT_CODE:
        lang = meta.get("language", "")
        code_lines = [(e.get("text_run") or {}).get("content", "") for e in (elements or [])]
        return f"{TRIPLE_BACKTICK}{lang}\n" + "\n".join(code_lines) + "\n" + f"{TRIPLE_BACKTICK}"

    # Todo
    if bt == BT_TODO:
        return f"- [{'x' if meta.get('done', False) else ' '}] {text}"

    # Quote
    if bt == BT_QUOTE:
        return f"> {text}"

    # Divider
    if bt == BT_DIVIDER:
        return "---"

    # Image
    if bt == BT_IMAGE:
        token = meta.get("token", "")
        if token:
            # Use a special URL scheme; images.py will resolve via Drive API
            url = f"feishu-image://{token}"
            alt = extract_inline(elements) if elements else token
            return f"![{alt}]({url})"
        return ""

    # Grid containers
    if bt in (BT_GRID, BT_GRID_COL):
        return ""

    # Callout (block_type 23)
    if bt == 23:
        callout_type = meta.get("type", "note")
        md_tag = CALLOUT_MAP.get(callout_type, f"[!{callout_type}]")
        return f"> {md_tag} {text}"

    # Legacy fallbacks
    if bt == 11:
        lang = meta.get("language", "")
        cl = [(e.get("text_run") or {}).get("content", "") for e in (elements or [])]
        return f"{TRIPLE_BACKTICK}{lang}\\n" + "\\n".join(cl) + "\\n" + f"{TRIPLE_BACKTICK}"
    if bt == 12:
        done = meta.get("done", False)
        if "done" in meta:
            return f"- [{'x' if done else ' '}] {text}"
        return f"> {text}"

    if text.strip():
        return text
    return ""


def _build_children_map(items):
    """Build a parent_id -> [children] mapping."""
    children = {}
    for item in items:
        pid = item.get("parent_id", "")
        if pid:
            children.setdefault(pid, []).append(item)
    return children


def _render_blocks(items, children_map, parent_id=""):
    """Recursively render blocks with proper indentation for nested lists."""
    lines = []
    for item in children_map.get(parent_id, []):
        line = _render_block(item)
        sub_lines = _render_blocks(items, children_map, item.get("block_id", ""))

        if line.strip():
            lines.append(line)
            if sub_lines:
                for s in sub_lines:
                    if s.startswith("- ") or s.startswith("1. ") or s.startswith("> "):
                        lines.append("  " + s)
                    else:
                        lines.append(s)
        else:
            lines.extend(sub_lines)

    return lines


def blocks_to_markdown(blocks):
    """Convert a list of Feishu blocks to a Markdown string."""
    children = _build_children_map(blocks)

    root_id = ""
    for item in blocks:
        if item.get("block_type") == 1:
            root_id = item.get("block_id", "")
            break

    lines = _render_blocks(blocks, children, root_id)
    
    # If no root block found, render all blocks at top level
    if not root_id:
        lines = []
        for item in blocks:
            line = _render_block(item)
            if line.strip():
                lines.append(line)
    
    result = "\n\n".join(lines)

    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")

    return result
