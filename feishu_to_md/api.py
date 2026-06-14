# -*- coding: utf-8 -*-
"""Feishu Open API client with retry logic."""
import os
import time
import logging

import requests

logger = logging.getLogger("feishu_to_md.api")

# Feishu Open API base
API_BASE = "https://open.feishu.cn/open-apis"

# Block type constants - VERIFIED against real Feishu API response (2025+)
BT_TEXT       = 2
BT_H1, BT_H2, BT_H3 = 3, 4, 5
BT_H4, BT_H5, BT_H6 = 6, 7, 8
BT_BULLET, BT_ORDERED = 9, 10
BT_TODO       = 17
BT_CODE       = 14
BT_QUOTE      = 15
BT_DIVIDER    = 22
BT_IMAGE      = 27
BT_GRID       = 24
BT_GRID_COL   = 25

# Callout type mapping (block_type 23)
CALLOUT_MAP = {
    "note":     "[!note]",
    "tip":      "[!tip]",
    "info":     "[!info]",
    "warning":  "[!warning]",
    "danger":   "[!danger]",
    "quote":    "[!quote]",
    "caution":  "[!caution]",
    # Chinese aliases
    "笔记":     "[!note]",
    "提示":     "[!tip]",
    "信息":     "[!info]",
    "警告":     "[!warning]",
    "危险":     "[!danger]",
    "引用":     "[!quote]",
}


def _get_feishu_headers():
    """Get tenant access token for Feishu Open API."""
    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        logger.debug("No FEISHU_APP_ID/APP_SECRET configured, API auth unavailable")
        return None

    max_retries = 3
    for attempt in range(max_retries):
        try:
            r = requests.post(
                f"{API_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
                timeout=10,
            )
            d = r.json()
            if d.get("code") != 0:
                logger.error("Token request failed (attempt %d/%d): %s", attempt + 1, max_retries, d.get("msg", ""))
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))
                continue
            logger.debug("Obtained tenant access token successfully")
            return {"Authorization": "Bearer " + d["tenant_access_token"]}
        except requests.RequestException as e:
            logger.warning("Token request network error (attempt %d/%d): %s", attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))

    return None


def _api_get(url, headers, params=None, timeout=15, max_retries=3):
    """Make a GET request with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status in (429, 500, 502, 503, 504):
                wait = 1 * (2 ** attempt)
                logger.warning("API HTTP %s (attempt %d/%d), retrying in %ds", status, attempt + 1, max_retries, wait)
                time.sleep(wait)
            else:
                logger.error("API HTTP error: %s", e)
                return None
        except requests.RequestException as e:
            logger.warning("API network error (attempt %d/%d): %s", attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))
            else:
                return None
    return None


def get_doc_meta(url_kind, token):
    """Resolve document metadata (title, doc_id) from Feishu Open API.
    
    Returns dict with 'doc_id' and 'title', or None on failure.
    """
    headers = _get_feishu_headers()
    if not headers:
        logger.warning("Cannot resolve doc meta without API auth")
        return None

    title, doc_id = "", token

    if url_kind == "wiki":
        try:
            wd = _api_get(
                f"{API_BASE}/wiki/v2/spaces/get_node",
                headers=headers,
                params={"token": token},
                timeout=10,
            )
            if wd and wd.get("code") == 0:
                node = wd.get("data", {}).get("node", {})
                doc_id = node.get("obj_token", token)
                title = node.get("title", "")
                logger.debug("Wiki resolved: doc_id=%s, title=%s", doc_id, title)
        except Exception as e:
            logger.error("Wiki resolve error: %s", e)

    try:
        dd = _api_get(
            f"{API_BASE}/docx/v1/documents/{doc_id}",
            headers=headers,
            timeout=10,
        )
        if dd and dd.get("code") == 0:
            d = dd.get("data", {}).get("document", {})
            if not title:
                title = d.get("title", "")
                logger.debug("Doc info resolved: title=%s", title)
    except Exception as e:
        logger.error("Doc info error: %s", e)

    if title:
        logger.info("Document title: %s", title)

    return {"doc_id": doc_id, "title": title}


def get_all_blocks(doc_id, headers=None, max_retries=3):
    """Paginate through all blocks of a document.
    
    Returns list of block items, or empty list on failure.
    """
    if headers is None:
        headers = _get_feishu_headers()
    if not headers:
        logger.error("No headers available for block fetch")
        return []

    all_items = []
    page_token = None

    for attempt in range(max_retries):
        try:
            params = {"page_size": 200}
            if page_token:
                params["page_token"] = page_token

            url = f"{API_BASE}/docx/v1/documents/{doc_id}/blocks"
            d = _api_get(url, headers=headers, params=params, timeout=15)

            if d is None:
                logger.warning("Failed to fetch blocks page (attempt %d/%d)", attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return all_items

            if d.get("code") != 0:
                logger.error("API error fetching blocks: %s", d.get("msg", ""))
                break

            items = d.get("data", {}).get("items", [])
            all_items.extend(items)
            logger.debug("Fetched %d blocks (total: %d)", len(items), len(all_items))

            if not d.get("data", {}).get("has_more", False):
                break
            page_token = d.get("data", {}).get("page_token")
            if not page_token:
                logger.warning("No page_token returned but has_more=true, stopping pagination")
                break

        except Exception as e:
            logger.error("Block fetch exception (attempt %d/%d): %s", attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))

    logger.info("Fetched %d total blocks", len(all_items))
    return all_items
