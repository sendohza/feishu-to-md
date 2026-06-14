# -*- coding: utf-8 -*-
"""URL parser for Feishu document URLs."""
import re
import logging

logger = logging.getLogger("feishu_to_md.parser")

_URL_PATTERNS = [
    ("wiki", r"feishu\.cn/wiki/([A-Za-z0-9_-]{10,60})"),
    ("wiki", r"larksuite\.com/wiki/([A-Za-z0-9_-]{10,60})"),
    ("docx", r"feishu\.cn/docx/([A-Za-z0-9_-]{10,60})"),
    ("doc",  r"feishu\.cn/docs/([A-Za-z0-9_-]{10,60})"),
    ("doc",  r"larksuite\.com/docs/([A-Za-z0-9_-]{10,60})"),
]

_COMMUNITY_PATTERNS = [
    r"feishu\.cn/community/.+?id=(\d+)",
    r"feishu\.cn/community/.+?/(\d+)",
]


def parse_feishu_url(url):
    """Parse a Feishu URL and return (url_kind, token).
    
    Args:
        url: Feishu document URL string.
        
    Returns:
        Tuple of (kind, token). Examples:
            ("wiki", "abc123...")
            ("doc",  "xyz789...")
            ("docx", "def456...")
            (None, None) for unparseable URLs.
    """
    url = url.strip()
    
    for kind, pattern in _URL_PATTERNS:
        m = re.search(pattern, url)
        if m:
            token = m.group(1)
            logger.debug("Parsed %s URL, token=%s", kind, token)
            return (kind, token)
    
    for pattern in _COMMUNITY_PATTERNS:
        m = re.search(pattern, url)
        if m:
            token = m.group(1)
            logger.debug("Parsed community URL, token=%s", token)
            return ("community", token)
    
    if "feishu.cn" in url or "larksuite.com" in url:
        logger.warning("URL is Feishu but pattern did not match: %s", url[:80])
        return ("unknown", None)
    
    logger.debug("Not a Feishu URL: %s", url[:80])
    return (None, None)


def is_feishu_url(url):
    """Check if a URL belongs to Feishu."""
    kind, _ = parse_feishu_url(url)
    return kind is not None
