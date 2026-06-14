# -*- coding: utf-8 -*-
"""Converter module with both API and public extraction modes."""
import os
import re
import time
import json
import logging
import shutil

from .api import get_doc_meta, get_all_blocks, _get_feishu_headers
from .parser import parse_feishu_url
from .renderer import blocks_to_markdown
from .images import download_images, ASSETS_DIR_NAME
from .logger_setup import setup_logger

logger = logging.getLogger("feishu_to_md.converter")

DEFAULT_OUTPUT_TEMPLATE = "{title}.md"

_OBSIDIAN_VAULT = os.path.join(os.path.expanduser("~"), "Documents", "Obsidian Vault")


def make_frontmatter(title, url, word_count=0):
    st = "feishu" if ("feishu.cn" in url or "larksuite.com" in url) else "web"
    fm = "---\n"
    fm += f'title: {json.dumps(title or "untitled", ensure_ascii=False)}\n'
    fm += f"source: {url}\n"
    fm += f"source_type: {st}\n"
    fm += f"created: {time.strftime('%Y-%m-%d')}\n"
    fm += f"word_count: {word_count}\n"
    fm += 'description: ""\n'
    fm += "tags:\n  - clippings\n  - feishu\n---\n\n"
    return fm


def optimize_for_obsidian(md, title=""):
    while "\n\n\n" in md:
        md = md.replace("\n\n\n", "\n\n")
    md = re.sub(r"(?<!\n)\n(#{1,6}\s)", r"\n\n\1", md)
    lines = md.split("\n")
    fm_lines, body_lines, in_fm, fm_done = [], [], False, False
    for line in lines:
        if not fm_done and line.strip() == "---":
            if not in_fm:
                in_fm = True
                fm_lines.append(line)
            else:
                in_fm = False
                fm_done = True
                fm_lines.append(line)
            continue
        if in_fm:
            fm_lines.append(line)
        else:
            body_lines.append(line)
    seen_keys = set()
    clean_fm = []
    for fl in fm_lines:
        s = fl.strip()
        if s in ("---", "") or ":" not in s:
            clean_fm.append(fl)
            continue
        k = s.split(":", 1)[0].strip().lower()
        if k in seen_keys:
            continue
        seen_keys.add(k)
        clean_fm.append(fl)
    fm_text = "\n".join(clean_fm)
    body = "\n".join(body_lines).strip()
    desc_match = re.search(r'description:\s*""', fm_text)
    if desc_match:
        for line in body.split("\n"):
            s = line.strip()
            if s and not s.startswith(("#", "!", "- ", "* ", "> ", "", "|", "---")):
                if s != title and len(s) > 20:
                    escaped = s[:200].replace('"', "'")
                    fm_text = fm_text.replace('description: ""', f'description: "{escaped}"', 1)
                    break
    return fm_text + "\n" + body


def process_url(url, output_path=None, skip_images=False):
    """Process a single Feishu URL via Open API and convert to Markdown."""
    logger.info("Processing URL: %s", url)
    url_kind, token = parse_feishu_url(url)
    if not token:
        logger.error("Invalid Feishu URL: %s", url[:100])
        print(f"  [error] Invalid Feishu URL: {url[:80]}")
        return None
    logger.info("URL type: %s, token: %s", url_kind, token)
    meta = get_doc_meta(url_kind, token)
    if not meta:
        logger.error("API auth failed. Set FEISHU_APP_ID and FEISHU_APP_SECRET in .env")
        print("  [error] API auth failed. Check .env for FEISHU_APP_ID/FEISHU_APP_SECRET")
        return None
    doc_id = meta["doc_id"]
    title = meta["title"] or "untitled"
    headers = _get_feishu_headers()
    blocks = get_all_blocks(doc_id, headers)
    if not blocks:
        logger.error("No blocks fetched for doc_id=%s", doc_id)
        print("  [error] No content fetched. Check document permissions.")
        return None
    md_content = blocks_to_markdown(blocks)
    script_dir = os.environ.get("SCRIPT_DIR", os.path.dirname(os.path.abspath(".")))
    if not skip_images:
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ASSETS_DIR_NAME)
        assets_dir = os.path.normpath(assets_dir)
        cookies = os.getenv("FEISHU_COOKIES", "").strip()
        api_headers = headers if headers else None
        md_content, img_downloaded, img_total = download_images(
            md_content, assets_dir, referer_url=url, cookies=cookies, api_headers=api_headers
        )
        if img_total > 0:
            logger.info("Images: %d/%d downloaded", img_downloaded, img_total)
    frontmatter = make_frontmatter(title, url, len(md_content))
    full_md = frontmatter + md_content
    full_md = optimize_for_obsidian(full_md, title=title)
    if not output_path:
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
        output_path = os.path.join(
            script_dir if os.path.isdir(script_dir) else os.getcwd(),
            f"{safe_title}.md",
        )
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_md)
    logger.info("Saved output: %s (%d bytes)", output_path, len(full_md))
    print(f"  [save] Saved: {output_path} ({len(full_md)} bytes)")
    return output_path


def process_url_public(url, output_dir=None, skip_images=False):
    """Process a single Feishu URL via public page scraping.

    Output layout (Obsidian-ready, shared assets):
        <vault>/<title>.md
        <vault>/assets/<title>_001.png ...

    Args:
        url: Feishu document/wiki URL.
        output_dir: Base output directory. Defaults to Obsidian Vault.
        skip_images: If True, skip image download.

    Returns:
        Output file path on success, None on failure.
    """
    from .public_extract import extract_public

    logger.info("Processing URL (public mode): %s", url)

    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="feishu_")

    try:
        result = extract_public(
            url=url,
            out_dir=tmp_dir,
            download_images=not skip_images,
            cookies_str=os.getenv("FEISHU_COOKIES", ""),
            timeout=90,
        )
    except Exception as e:
        logger.error("Public extraction failed: %s", e)
        print(f"  [error] Public extraction failed: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    title = result.get("title", "feishu_doc")
    md_path = result["md_path"]
    img_ok = result.get("images_ok", 0)
    img_total = result.get("image_count", 0)

    base = output_dir or _OBSIDIAN_VAULT
    os.makedirs(base, exist_ok=True)

    # Safe filename for images (avoid collisions across docs)
    safe_prefix = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', title)
    safe_prefix = re.sub(r'[\\/:*?"<>|\s]+', '_', safe_prefix).strip('_')
    if not safe_prefix:
        safe_prefix = "feishu_doc"

    # Shared assets directory: <vault>/assets/
    shared_assets = os.path.join(base, "assets")
    os.makedirs(shared_assets, exist_ok=True)

    # Read the generated MD
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    # Move images from tmp _assets/ to <vault>/assets/<prefix>_NNN.png
    tmp_assets = os.path.join(tmp_dir, "_assets")
    if os.path.isdir(tmp_assets):
        for fname in sorted(os.listdir(tmp_assets)):
            src = os.path.join(tmp_assets, fname)
            # Rename: img_001.png -> <title>_001.png
            new_fname = fname.replace("img_", safe_prefix + "_")
            dst = os.path.join(shared_assets, new_fname)
            shutil.move(src, dst)
            # Update MD reference: _assets/img_001.png -> assets/<title>_001.png
            old_ref = f"_assets/{fname}"
            new_ref = f"assets/{new_fname}"
            md_content = md_content.replace(old_ref, new_ref)

    # Add frontmatter
    frontmatter = make_frontmatter(title, url, len(md_content))
    full_md = frontmatter + md_content

    # Write MD file directly in vault root (not in subfolder)
    safe_title = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', title)
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', safe_title).strip()
    if not safe_title:
        safe_title = "feishu_doc"
    final_md_path = os.path.join(base, safe_title + ".md")
    with open(final_md_path, "w", encoding="utf-8") as f:
        f.write(full_md)

    # Move manifest
    tmp_manifest = os.path.join(tmp_dir, "manifest.json")
    if os.path.exists(tmp_manifest):
        manifest_dir = os.path.join(base, "manifests")
        os.makedirs(manifest_dir, exist_ok=True)
        shutil.move(tmp_manifest, os.path.join(manifest_dir, safe_prefix + ".json"))

    # Cleanup tmp
    shutil.rmtree(tmp_dir, ignore_errors=True)

    logger.info("Saved: %s (images %d/%d)", final_md_path, img_ok, img_total)
    print(f"  [done] Title: {title}")
    print(f"  [done] Images: {img_ok}/{img_total} downloaded")
    print(f"  [done] Saved: {final_md_path}")
    print(f"  [done] Assets: {shared_assets}")
    return final_md_path


def process_urls_batch(urls, output_dir=None, skip_images=False):
    """Process multiple Feishu URLs in batch (API mode)."""
    logger.info("Batch processing %d URLs", len(urls))
    results = {"success": [], "failed": []}
    for i, url in enumerate(urls):
        print(f"\n[{i+1}/{len(urls)}] Processing: {url[:80]}")
        output = process_url(url, skip_images=skip_images)
        if output:
            results["success"].append(output)
        else:
            results["failed"].append(url)
    logger.info("Batch complete: %d success, %d failed", len(results["success"]), len(results["failed"]))
    print(f"\nBatch complete: {len(results['success'])} success, {len(results['failed'])} failed")
    return results


def process_urls_batch_public(urls, output_dir=None, skip_images=False):
    """Process multiple Feishu URLs in batch (public mode)."""
    logger.info("Batch processing %d URLs (public mode)", len(urls))
    results = {"success": [], "failed": []}
    for i, url in enumerate(urls):
        print(f"\n[{i+1}/{len(urls)}] Processing: {url[:80]}")
        output = process_url_public(url, output_dir=output_dir, skip_images=skip_images)
        if output:
            results["success"].append(output)
        else:
            results["failed"].append(url)
    logger.info("Batch complete (public): %d success, %d failed", len(results["success"]), len(results["failed"]))
    print(f"\nBatch complete: {len(results['success'])} success, {len(results['failed'])} failed")
    return results
