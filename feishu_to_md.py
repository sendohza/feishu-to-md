# -*- coding: utf-8 -*-
# feishu_to_md.py v7.0 - Feishu doc to Obsidian-ready Markdown
import sys
import os
import argparse
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from feishu_to_md import setup_logger, process_url, process_urls_batch
from feishu_to_md.converter import process_url_public, process_urls_batch_public
from feishu_to_md.cookie_fetcher import refresh_cookies

logger = logging.getLogger("feishu_to_md")


def main():
    parser = argparse.ArgumentParser(
        description="Feishu to Obsidian Markdown (v7.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Public mode -> saves to Obsidian Vault automatically
  python feishu_to_md.py --url "<url>" --mode public

  # Public mode -> custom output directory
  python feishu_to_md.py --url "<url>" --mode public --output-dir ./out

  # API mode (needs .env credentials)
  python feishu_to_md.py --url "<url>" --fix-images

  # Batch mode (public)
  python feishu_to_md.py --urls-file urls.txt --mode public
""",
    )
    parser.add_argument("--url", help="Feishu article URL to convert")
    parser.add_argument("--urls-file", help="File with one URL per line (batch mode)")
    parser.add_argument("--output", default="", help="Output file path (API single-URL mode)")
    parser.add_argument("--output-dir", default="", help="Output directory (default: Obsidian Vault for public mode)")
    parser.add_argument("--mode", choices=["api", "public"], default="api",
                        help="Conversion mode: 'api' uses Open API (default), 'public' scrapes the rendered page")
    parser.add_argument("--fix-images", action="store_true", help="Download CDN images (API mode)")
    parser.add_argument("--skip-images", action="store_true", help="Skip image download entirely")
    parser.add_argument("--refresh-cookies", action="store_true", help="Extract Feishu cookies from Chrome")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging level (default: INFO)")
    parser.add_argument("--log-file", action="store_true", help="Also write logs to file")

    args = parser.parse_args()

    setup_logger(level=args.log_level, log_to_file=args.log_file)

    if args.refresh_cookies:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(script_dir, ".env")
        success = refresh_cookies(env_path)
        sys.exit(0 if success else 1)

    # ---- PUBLIC MODE ----
    if args.mode == "public":
        # output_dir: use explicit arg if given, otherwise None (-> Obsidian Vault)
        output_dir = args.output_dir if args.output_dir else None

        if args.urls_file:
            if not os.path.isfile(args.urls_file):
                logger.error("URLs file not found: %s", args.urls_file)
                print(f"Error: URLs file not found: {args.urls_file}")
                sys.exit(1)
            with open(args.urls_file, encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            if not urls:
                logger.error("No URLs found in %s", args.urls_file)
                print(f"Error: No URLs found in {args.urls_file}")
                sys.exit(1)
            results = process_urls_batch_public(urls, output_dir=output_dir, skip_images=args.skip_images)
            sys.exit(1 if results["failed"] else 0)

        if not args.url:
            print("Error: --url is required in public mode")
            parser.print_help()
            sys.exit(1)

        result = process_url_public(args.url, output_dir=output_dir, skip_images=args.skip_images)
        if result:
            print(f"\nDone! Output: {result}")
            sys.exit(0)
        else:
            print("Failed")
            sys.exit(1)

    # ---- API MODE (default) ----
    if args.urls_file:
        if not os.path.isfile(args.urls_file):
            logger.error("URLs file not found: %s", args.urls_file)
            print(f"Error: URLs file not found: {args.urls_file}")
            sys.exit(1)
        with open(args.urls_file, encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        if not urls:
            logger.error("No URLs found in %s", args.urls_file)
            print(f"Error: No URLs found in {args.urls_file}")
            sys.exit(1)
        output_dir = args.output_dir or os.getcwd()
        results = process_urls_batch(urls, output_dir=output_dir, skip_images=args.skip_images)
        sys.exit(1 if results["failed"] else 0)

    if not args.url:
        parser.print_help()
        sys.exit(1)

    skip = args.skip_images or (not args.fix_images and not os.getenv("FEISHU_COOKIES", "").strip())
    result = process_url(args.url, args.output or None, skip_images=skip)
    if result:
        print(f"Done! Output: {result}")
        sys.exit(0)
    else:
        print("Failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
