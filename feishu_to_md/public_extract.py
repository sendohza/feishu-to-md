# -*- coding: utf-8 -*-
"""Public link extractor: scrape rendered Feishu page without API credentials."""
import os
import re
import time
import hashlib
import json
import logging
import base64
import urllib.parse

import requests

logger = logging.getLogger("feishu_to_md.public_extract")

_ASSETS_DIR = "_assets"
_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}


def _ext_from_url(url, default=".png"):
    path = urllib.parse.urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    return ext if ext in _IMG_EXTS else default


def _safe_filename(url, idx):
    h = hashlib.md5(url.encode()).hexdigest()[:10]
    ext = _ext_from_url(url)
    return "img_%03d_%s%s" % (idx, h, ext)


def _download_image(url, out_path, referer, cookies_str="", retries=2):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0 Safari/537.36",
        "Referer": referer,
    }
    if cookies_str:
        headers["Cookie"] = cookies_str
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=15, stream=True)
            if r.status_code == 200:
                data = r.content
                if len(data) > 200:
                    with open(out_path, "wb") as f:
                        f.write(data)
                    return True
            logger.debug("Image download status %d (attempt %d): %s", r.status_code, attempt + 1, url[:80])
        except Exception as e:
            logger.debug("Image download error (attempt %d): %s", attempt + 1, e)
        if attempt < retries:
            time.sleep(1 * (attempt + 1))
    return False


def _save_base64_png(data_url, out_path):
    try:
        if not data_url or not data_url.startswith("data:image"):
            return False
        header, b64data = data_url.split(",", 1)
        raw = base64.b64decode(b64data)
        if len(raw) < 200:
            return False
        with open(out_path, "wb") as f:
            f.write(raw)
        return True
    except Exception as e:
        logger.debug("Failed to save base64 image: %s", e)
        return False


_EXTRACT_JS = r"""async () => {
    const container = document.querySelector('.bear-web-x-container')
                   || document.querySelector('[class*="docx-in-wiki"]')
                   || document.documentElement;
    const root = document.querySelector('.zone-container.editor-kit-container')
              || document.querySelector('.editor-kit-container')
              || document.body;
    if (!root) return {error: 'no root found'};

    let title = '';
    const titleH1 = root.querySelector('h1.page-block-content');
    if (titleH1) {
        title = titleH1.innerText.replace(/[\u200b\u200c\u200d\ufeff]/g, '').trim();
    } else {
        const h1s = document.querySelectorAll('h1');
        for (const h of h1s) {
            const t = h.innerText.trim();
            if (t && t.length > 2 && !h.className.includes('ellipsis')) {
                title = t.replace(/[\u200b\u200c\u200d\ufeff]/g, '').trim();
                break;
            }
        }
    }
    if (!title && document.title) {
        title = document.title.replace(/ - .*/, '').replace(/[\u200b\u200c\u200d\ufeff]/g, '').trim();
    }

    const delay = ms => new Promise(r => setTimeout(r, ms));
    const seenBlockIds = new Set();
    const orderedBlocks = [];
    const capturedImages = {};

    function cleanText(t) {
        return (t || '').replace(/[\u200b\u200c\u200d\ufeff]/g, '').trim();
    }

    // Process all currently visible blocks in one pass
    function processVisibleBlocks() {
        const items = root.querySelectorAll('[class*="docx-"][class*="-block"]');
        for (const item of items) {
            const cls = item.className.toString();
            const bid = item.getAttribute('data-block-id') || '';
            if (!bid) continue;
            if (seenBlockIds.has(bid)) continue;
            if (cls.includes('zero-space') || cls.includes('toolbar') || cls.includes('forbidden') || cls.includes('comment')) continue;

            // Image blocks
            if (cls.includes('docx-image-block')) {
                const img = item.querySelector('img');
                if (!img) continue;  // not rendered yet, will catch on next scroll
                const src = img.getAttribute('data-src') || img.getAttribute('src') || '';
                if (!src || src.startsWith('data:')) continue;
                const cap = item.querySelector('[class*="caption"]');
                const alt = cap ? cleanText(cap.innerText) : '';
                seenBlockIds.add(bid);
                // Try canvas capture right now (while element is in DOM)
                let captured = false;
                if (img.complete && img.naturalWidth > 0) {
                    try {
                        const canvas = document.createElement('canvas');
                        canvas.width = img.naturalWidth;
                        canvas.height = img.naturalHeight;
                        const ctx2 = canvas.getContext('2d');
                        ctx2.drawImage(img, 0, 0);
                        const dataUrl = canvas.toDataURL('image/png');
                        if (dataUrl.length > 500) {
                            capturedImages[bid] = dataUrl;
                            captured = true;
                        }
                    } catch (e) { /* fall through */ }
                }
                orderedBlocks.push({t: 'img', src: src, alt: alt, blockId: bid, captured: captured});
                continue;
            }

            seenBlockIds.add(bid);
            const text = cleanText(item.innerText);

            // Headings
            const hm = cls.match(/docx-heading(\d)-block/);
            if (hm) {
                if (text) orderedBlocks.push({t: 'h', level: parseInt(hm[1]), text: text, blockId: bid});
                continue;
            }
            // Code
            if (cls.includes('code-block')) {
                const code = item.querySelector('code');
                const lang = (code ? code.className : cls).replace(/language-|lang-/g, '').trim();
                const codeText = cleanText((code || item).innerText);
                if (codeText) orderedBlocks.push({t: 'code', lang: lang, text: codeText, blockId: bid});
                continue;
            }
            if (cls.includes('quote')) {
                if (text) orderedBlocks.push({t: 'quote', text: text, blockId: bid});
                continue;
            }
            if (cls.includes('divider')) {
                orderedBlocks.push({t: 'hr', blockId: bid});
                continue;
            }
            if (cls.includes('bullet-block')) {
                if (text) orderedBlocks.push({t: 'bullet', text: text, blockId: bid});
                continue;
            }
            if (cls.includes('ordered-block')) {
                if (text) orderedBlocks.push({t: 'ordered', text: text, blockId: bid});
                continue;
            }
            if (cls.includes('todo')) {
                const done = !!item.querySelector('[checked],.checked,[aria-checked=true]');
                if (text) orderedBlocks.push({t: 'todo', text: text, done: done, blockId: bid});
                continue;
            }
            if (cls.includes('text-block')) {
                if (text) orderedBlocks.push({t: 'text', text: text, blockId: bid});
                continue;
            }
            if (text && text.length > 1) {
                orderedBlocks.push({t: 'text', text: text, blockId: bid});
            }
        }
        // Title
        const titleEl = root.querySelector('h1.page-block-content');
        if (titleEl && !seenBlockIds.has('title-h1')) {
            const tt = cleanText(titleEl.innerText);
            if (tt) {
                seenBlockIds.add('title-h1');
                orderedBlocks.unshift({t: 'h', level: 1, text: tt, blockId: 'title-h1'});
            }
        }
    }

    // === Main scroll loop ===
    processVisibleBlocks();
    let maxH = container.scrollHeight || 6000;
    const step = 120;  // small steps to catch images before they're recycled
    const maxIter = 250;
    let iter = 0;

    for (let y = 0; y <= maxH + 5000 && iter < maxIter; y += step) {
        container.scrollTop = y;
        await delay(80);
        processVisibleBlocks();
        if (container.scrollHeight > maxH) maxH = container.scrollHeight;
        iter++;
    }
    // Second pass
    for (let y = 0; y <= maxH + 2000 && iter < maxIter * 2; y += step) {
        container.scrollTop = y;
        await delay(50);
        processVisibleBlocks();
        if (container.scrollHeight > maxH) maxH = container.scrollHeight;
        iter++;
    }
    container.scrollTop = 0;

    return {title: title, blocks: orderedBlocks, totalBlocks: orderedBlocks.length, capturedImages: capturedImages};
}"""


def _download_via_playwright(page, src, fpath):
    """Download an image using Playwright's browser context (handles auth cookies).
    
    Args:
        page: Playwright Page object (with active browser context).
        src: Image URL to download.
        fpath: Local path to save the image.
        
    Returns:
        True if download succeeded, False otherwise.
    """
    try:
        # Use page.request (shares browser context cookies)
        resp = page.request.get(src, timeout=15000)
        if resp.status == 200 and len(resp.body) > 500:
            with open(fpath, "wb") as f:
                f.write(resp.body)
            logger.debug("Downloaded image via Playwright: %s", os.path.basename(fpath))
            return True
        else:
            logger.debug("Playwright download HTTP %d for %s", resp.status, src[:80])
    except Exception as e:
        logger.debug("Playwright download failed for %s: %s", src[:60], e)
    return False


def extract_public(url, out_dir, download_images=True, cookies_str="", timeout=90):
    """Extract a public Feishu doc page and save as local MD + assets."""
    from playwright.sync_api import sync_playwright

    os.makedirs(out_dir, exist_ok=True)
    assets_dir = os.path.join(out_dir, _ASSETS_DIR)
    if download_images:
        os.makedirs(assets_dir, exist_ok=True)

    logger.info("Opening page: %s", url[:100])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
        )
        if cookies_str:
            for part in cookies_str.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    ctx.add_cookies([{
                        "name": k.strip(),
                        "value": v.strip(),
                        "domain": ".feishu.cn",
                        "path": "/",
                    }])

        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        except Exception as e:
            logger.warning("Page goto timeout/error, continuing: %s", e)

        for sel in [
            ".zone-container.editor-kit-container",
            ".editor-kit-container",
            "[class*='doc-content']",
            "article",
        ]:
            try:
                page.wait_for_selector(sel, timeout=8000)
                logger.debug("Found content selector: %s", sel)
                break
            except Exception:
                continue

        result = page.evaluate(_EXTRACT_JS)
        browser.close()

    title = result.get("title", "") or "feishu_doc"
    blocks = result.get("blocks", [])
    captured = result.get("capturedImages", {})
    logger.info("Extracted %d blocks, %d captured images, title=%s", len(blocks), len(captured), title)

    md_lines = []
    img_manifest = []
    img_idx = 0

    for blk in blocks:
        bt = blk.get("t", "")
        if bt == "h":
            level = blk.get("level", 2)
            md_lines.append("#" * level + " " + blk["text"])
        elif bt == "text":
            md_lines.append(blk["text"])
        elif bt == "bullet":
            md_lines.append("- " + blk["text"])
        elif bt == "ordered":
            md_lines.append("1. " + blk["text"])
        elif bt == "todo":
            mark = "x" if blk.get("done") else " "
            md_lines.append("- [%s] %s" % (mark, blk["text"]))
        elif bt == "quote":
            for line in blk["text"].split("\n"):
                line = line.strip()
                if line:
                    md_lines.append("> " + line)
        elif bt == "code":
            lang = blk.get("lang", "")
            md_lines.append("`" + lang)
            md_lines.append(blk["text"])
            md_lines.append("`")
        elif bt == "hr":
            md_lines.append("---")
        elif bt == "img":
            img_idx += 1
            src = blk.get("src", "")
            alt = blk.get("alt", "") or ("image_%d" % img_idx)
            block_id = blk.get("blockId", "")

            data_url = captured.get(block_id, "")

            if download_images and data_url:
                fname = "img_%03d.png" % img_idx
                fpath = os.path.join(assets_dir, fname)
                ok = _save_base64_png(data_url, fpath)
                if ok:
                    md_lines.append("![%s](%s/%s)" % (alt, _ASSETS_DIR, fname))
                    img_manifest.append({"blockId": block_id, "local": fname, "status": "ok"})
                    continue

            if src.startswith("blob:"):
                md_lines.append("![%s](%s)" % (alt, src))
                img_manifest.append({"blockId": block_id, "src": src[:80], "status": "blob_unavailable"})
                continue

            if download_images:
                fname = _safe_filename(src, img_idx)
                fpath = os.path.join(assets_dir, fname)
                # Try Playwright browser context download first (handles authenticated internal CDN)
                ok = _download_via_playwright(page, src, fpath)
                if not ok:
                    ok = _download_image(src, fpath, referer=url, cookies_str=cookies_str)
                if ok:
                    md_lines.append("![%s](%s/%s)" % (alt, _ASSETS_DIR, fname))
                    img_manifest.append({"blockId": block_id, "local": fname, "status": "ok"})
                else:
                    md_lines.append("![%s](%s)" % (alt, src))
                    img_manifest.append({"blockId": block_id, "src": src[:100], "status": "failed"})
                    logger.warning("Failed to download image: %s", src[:80])
            else:
                md_lines.append("![%s](%s)" % (alt, src))
                img_manifest.append({"blockId": block_id, "src": src[:100], "status": "skipped"})

    clean_lines = []
    for line in md_lines:
        if not clean_lines or line != clean_lines[-1]:
            clean_lines.append(line)

    md_content = "\n\n".join(clean_lines)
    while "\n\n\n" in md_content:
        md_content = md_content.replace("\n\n\n", "\n\n")
    md_content = md_content.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').replace('\ufeff', '')

    safe_title = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', title)
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', safe_title).strip()
    if not safe_title:
        safe_title = "feishu_doc"
    md_path = os.path.join(out_dir, safe_title + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    manifest_path = os.path.join(out_dir, "manifest.json")
    manifest = {
        "title": title,
        "url": url,
        "blocks_total": len(blocks),
        "images_total": len(img_manifest),
        "images_ok": sum(1 for m in img_manifest if m.get("status") == "ok"),
        "images_failed": sum(1 for m in img_manifest if m.get("status") == "failed"),
        "images": img_manifest,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    ok_count = manifest["images_ok"]
    total_count = manifest["images_total"]
    logger.info("Saved: %s (images %d/%d)", md_path, ok_count, total_count)

    return {
        "md_path": md_path,
        "assets_dir": assets_dir if download_images else None,
        "title": title,
        "image_count": total_count,
        "images_ok": ok_count,
        "manifest_path": manifest_path,
    }
