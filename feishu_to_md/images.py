# -*- coding: utf-8 -*-
"""Image download and replacement for Feishu Markdown output."""
import os
import re
import time
import hashlib
import urllib.parse
import logging

import requests

logger = logging.getLogger("feishu_to_md.images")

ASSETS_DIR_NAME = "_assets"

# CDN image pattern from Feishu API
CDN_RE = re.compile(
    r'!\[([^\]]*)\]\((https://internal-api-drive-stream\.feishu\.cn/[^)]+)\)'
)

# Feishu image scheme: feishu-image://{file_token}
FEISHU_IMG_RE = re.compile(
    r'!\[([^\]]*)\]\(feishu-image://([^)]+)\)'
)


def download_images(md_content, assets_dir, referer_url="", cookies="", api_headers=None):
    """Download Feishu CDN images and replace URLs with local paths.
    
    Args:
        md_content: Markdown string containing Feishu CDN image URLs.
        assets_dir: Directory path to save downloaded images.
        referer_url: Referer header for image requests.
        cookies: Feishu session cookies string.
        api_headers: Optional dict with Authorization header for API-authenticated downloads.
        
    Returns:
        Tuple of (updated_md, downloaded_count, total_count).
    """
    os.makedirs(assets_dir, exist_ok=True)

    # --- Handle feishu-image:// URLs via Drive API (these are not CDN URLs) ---
    fi_matches = list(FEISHU_IMG_RE.finditer(md_content))
    fi_total = len(fi_matches)
    if fi_matches and api_headers:
        logger.info("Found %d feishu-image:// URLs to download via Drive API", fi_total)

    downloaded = 0

    # Process feishu-image:// URLs first
    if fi_matches and api_headers:
        for match in fi_matches:
            alt, file_token = match.group(1), match.group(2)
            ext = ".png"
            fname = hashlib.md5(file_token.encode()).hexdigest()[:12] + ext
            fpath = os.path.join(assets_dir, fname)

            if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
                md_content = md_content.replace(
                    f"feishu-image://{file_token}", f"{ASSETS_DIR_NAME}/{fname}", 1
                )
                downloaded += 1
                continue

            # Get download link via Drive API
            try:
                api_base = "https://open.feishu.cn/open-apis"
                r = requests.get(
                    f"{api_base}/drive/v1/files/{file_token}/download",
                    headers=api_headers,
                    timeout=10,
                    allow_redirects=False,
                )
                dl_url = None
                if r.status_code in (200, 202):
                    dl_url = r.json().get("data", {}).get("download_link") or r.json().get("data", {}).get("url")
                elif r.status_code in (301, 302, 303, 307, 308):
                    dl_url = r.headers.get("Location")

                if not dl_url:
                    dl_url = f"https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/all/{file_token}"

                dr = requests.get(dl_url, headers=api_headers, timeout=15)
                if dr.status_code == 200 and len(dr.content) > 500:
                    with open(fpath, "wb") as f:
                        f.write(dr.content)
                    md_content = md_content.replace(
                        f"feishu-image://{file_token}", f"{ASSETS_DIR_NAME}/{fname}", 1
                    )
                    downloaded += 1
                    logger.debug("Downloaded feishu-image (Drive API): %s", fname)
                else:
                    logger.warning("Drive API download failed: HTTP %d for %s", dr.status_code, file_token[:20])
            except Exception as e:
                logger.warning("feishu-image download error: %s", e)

    # --- Handle CDN image URLs (https://internal-api-drive-stream...) ---
    matches = list(CDN_RE.finditer(md_content))
    total = len(matches) + fi_total

    if total == 0:
        logger.debug("No images found in content")
        return md_content, 0, 0

    logger.info("Found %d total images to download (%d CDN, %d feishu-image)", len(matches), fi_total)
    has_cookies = bool(cookies)

    # Also handle feishu-image:// URLs via Drive API
    fi_matches = list(FEISHU_IMG_RE.finditer(md_content))
    if fi_matches and api_headers:
        logger.info("Found %d feishu-image:// URLs to download via Drive API", len(fi_matches))
        for match in fi_matches:
            alt, file_token = match.group(1), match.group(2)
            ext = ".png"
            fname = hashlib.md5(file_token.encode()).hexdigest()[:12] + ext
            fpath = os.path.join(assets_dir, fname)

            if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
                md_content = md_content.replace(
                    f"feishu-image://{file_token}", f"{ASSETS_DIR_NAME}/{fname}", 1
                )
                downloaded += 1
                continue

            # Get download link via Drive API
            try:
                api_base = "https://open.feishu.cn/open-apis"
                r = requests.get(
                    f"{api_base}/drive/v1/files/{file_token}/download",
                    headers=api_headers,
                    timeout=10,
                    allow_redirects=False,
                )
                dl_url = None
                if r.status_code in (200, 202):
                    dl_url = r.json().get("data", {}).get("download_link") or r.json().get("data", {}).get("url")
                elif r.status_code in (301, 302, 303, 307, 308):
                    dl_url = r.headers.get("Location")

                if not dl_url:
                    # Try the drive stream URL with API token
                    dl_url = f"https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/all/{file_token}"

                dr = requests.get(dl_url, headers=api_headers, timeout=15)
                if dr.status_code == 200 and len(dr.content) > 500:
                    with open(fpath, "wb") as f:
                        f.write(dr.content)
                    md_content = md_content.replace(
                        f"feishu-image://{file_token}", f"{ASSETS_DIR_NAME}/{fname}", 1
                    )
                    downloaded += 1
                    logger.debug("Downloaded feishu-image (Drive API): %s", fname)
                else:
                    logger.warning("Drive API download failed: HTTP %d for %s", dr.status_code, file_token[:20])
            except Exception as e:
                logger.warning("feishu-image download error: %s", e)
    
    for match in matches:
        alt, img_url = match.group(1), match.group(2)
        ext = os.path.splitext(urllib.parse.urlparse(img_url).path)[1] or ".png"
        fname = hashlib.md5(img_url.encode()).hexdigest()[:12] + ext
        fpath = os.path.join(assets_dir, fname)
        
        # Skip if already downloaded (and non-trivial size)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
            md_content = md_content.replace(img_url, f"{ASSETS_DIR_NAME}/{fname}", 1)
            downloaded += 1
            continue
        
        success = False

        # Method 1: with API Bearer token (most reliable for internal-api-drive-stream)
        if api_headers:
            try:
                dr = requests.get(img_url, headers=api_headers, timeout=10, allow_redirects=True)
                logger.debug("API token download: status=%d, len=%d, url=%s", dr.status_code, len(dr.content), img_url[:80])
                if dr.status_code == 200 and len(dr.content) > 500:
                    with open(fpath, "wb") as f:
                        f.write(dr.content)
                    md_content = md_content.replace(img_url, f"{ASSETS_DIR_NAME}/{fname}", 1)
                    downloaded += 1
                    success = True
                    logger.debug("Downloaded image (API token): %s", fname)
                else:
                    logger.warning("API token download HTTP %d for: %s", dr.status_code, img_url[:80])
            except Exception as e:
                logger.debug("API token download failed: %s", e)

        # Method 2: with cookies
        if not success and has_cookies:
            try:
                h = {
                    "Cookie": cookies,
                    "Referer": referer_url or "https://feishu.cn",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/134.0.0.0 Safari/537.36",
                }
                dr = requests.get(img_url, headers=h, timeout=8)
                if dr.status_code == 200 and len(dr.content) > 500:
                    with open(fpath, "wb") as f:
                        f.write(dr.content)
                    md_content = md_content.replace(img_url, f"{ASSETS_DIR_NAME}/{fname}", 1)
                    downloaded += 1
                    success = True
                    logger.debug("Downloaded image (cookies): %s", fname)
            except Exception as e:
                logger.warning("Cookie download failed: %s", e)

        # Method 3: without cookies (public images)
        if not success:
            try:
                dr = requests.get(
                    img_url,
                    timeout=5,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://feishu.cn"},
                )
                if dr.status_code == 200 and len(dr.content) > 500:
                    with open(fpath, "wb") as f:
                        f.write(dr.content)
                    md_content = md_content.replace(img_url, f"{ASSETS_DIR_NAME}/{fname}", 1)
                    downloaded += 1
                    success = True
                    logger.debug("Downloaded image (no cookie): %s", fname)
            except Exception as e:
                logger.warning("Public download failed: %s", e)
        
        if not success:
            logger.warning("Failed to download image: %s", img_url[:80])
        
        # Rate limiting: small delay between requests
        time.sleep(0.2)
    
    logger.info("Images: %d/%d downloaded", downloaded, total)
    return md_content, downloaded, total
