"""
main.py
Command-line entry point for the Test Case Automator.

Usage (single URL):
    python main.py <URL> <CSS_SELECTOR> [--headless] [--output path/to/file.xlsx]

Usage (batch CSV):
    python main.py --batch requirements.csv [--headless] [--output path/to/file.xlsx]

CSV format:
    url,selector
    https://example.com/features,#feature-requirements
    https://example.com/login,#login-spec
"""

import argparse
import csv
import logging
import os
import sys
from pathlib import Path

from config import LOG_DIR, LOG_FILE, LOG_LEVEL, EXCEL_FILE_PATH
from scraper import scrape_section, discover_selectors
from prompt_template import generate_test_cases
from parser import parse_to_rows
from excel_handler import append_test_cases


# ── Logging Setup ─────────────────────────────────────────────────────────────

def _setup_logging(log_file: str = LOG_FILE, level: str = LOG_LEVEL) -> None:
    """
    Configure root logger to write to both console and a rotating log file.

    Args:
        log_file: Path to the log file.
        level:    Logging level string (e.g. 'INFO', 'DEBUG').
    """
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(numeric_level)
    fh.setFormatter(formatter)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(numeric_level)
    ch.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.addHandler(fh)
    root.addHandler(ch)


logger = logging.getLogger(__name__)


# ── Core Processing ───────────────────────────────────────────────────────────

def process_requirement(url: str, selector: str, headless: bool = True) -> int:
    """
    Full pipeline for a single URL + CSS selector:
      1. Scrape the requirement section.
      2. Send to LLM and parse response.
      3. Convert to rows.
      4. Append to Excel.

    Args:
        url:      Full URL of the target page.
        selector: CSS selector identifying the requirement section.
        headless: Whether to run the browser in headless mode.

    Returns:
        Number of test cases appended (0 on failure).
    """
    logger.info("═" * 60)
    logger.info("Processing: %s  |  Selector: %s", url, selector)

    # Step 1 – Scrape
    try:
        scraped_text = scrape_section(url, selector, headless=headless)
    except (ValueError, RuntimeError) as exc:
        logger.error("Scraping failed for %s: %s", url, exc)
        return 0

    # Step 2 – Generate test cases via LLM
    try:
        test_cases = generate_test_cases(scraped_text)
    except (EnvironmentError, RuntimeError) as exc:
        logger.error("LLM generation failed: %s", exc)
        return 0

    # Step 3 – Parse to rows
    rows = parse_to_rows(test_cases)
    if not rows:
        logger.warning("No rows produced for %s — skipping Excel write.", url)
        return 0

    # Step 4 – Append to Excel
    try:
        append_test_cases(rows)
    except (ValueError, IOError) as exc:
        logger.error("Excel write failed: %s", exc)
        return 0

    logger.info("✓ Appended %d test case(s) for: %s", len(rows), url)
    return len(rows)


def process_batch(csv_path: str, headless: bool = True) -> None:
    """
    Read a CSV file of (url, selector) pairs and process each row.

    Args:
        csv_path: Path to the batch CSV file.
        headless: Whether to run the browser headlessly.
    """
    path = Path(csv_path)
    if not path.exists():
        logger.error("Batch CSV not found: %s", csv_path)
        sys.exit(1)

    total_written = 0
    failed_rows: list[int] = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate CSV columns
        if reader.fieldnames is None or not {"url", "selector"}.issubset(
            set(reader.fieldnames)
        ):
            logger.error(
                "Batch CSV must have columns 'url' and 'selector'. "
                "Found: %s",
                reader.fieldnames,
            )
            sys.exit(1)

        for line_num, row in enumerate(reader, start=2):  # Row 1 = header
            url = row.get("url", "").strip()
            selector = row.get("selector", "").strip()

            if not url or not selector:
                logger.warning("Row %d: empty url or selector — skipping.", line_num)
                failed_rows.append(line_num)
                continue

            count = process_requirement(url, selector, headless=headless)
            if count == 0:
                failed_rows.append(line_num)
            total_written += count

    logger.info("═" * 60)
    logger.info("Batch complete. Total test cases written: %d", total_written)
    if failed_rows:
        logger.warning("Rows with errors: %s", failed_rows)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="test_case_automator",
        description=(
            "Automatically generate QA test cases from web requirement pages "
            "and export them to an Excel workbook."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single page
  python main.py https://myapp.com/docs "#requirements" --headless

  # Batch mode
  python main.py --batch requirements.csv --headless

  # Custom output path
  python main.py https://myapp.com/docs ".spec-content" --output ./output/cases.xlsx

  # Visible browser (useful for debugging selectors)
  python main.py https://myapp.com/docs "#spec" --no-headless
        """,
    )

    # Positional args (only used when NOT in batch mode)
    parser.add_argument(
        "url",
        nargs="?",
        help="URL of the page containing the requirement section.",
    )
    parser.add_argument(
        "selector",
        nargs="?",
        help='CSS selector for the requirement section (e.g. "#requirements").',
    )

    # Options
    parser.add_argument(
        "--discover",
        metavar="URL",
        help=(
            "Scan a page and print all available selectors (data-testid, id) "
            "with content previews. Use this to find the right selector before running. "
            "Example: python main.py --discover https://yourjira.atlassian.net/browse/TICKET-1"
        ),
    )
    parser.add_argument(
        "--batch",
        metavar="CSV_FILE",
        help="Path to a CSV file with columns 'url' and 'selector' for batch processing.",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run Chrome in headless mode (default: True). Use --no-headless to show browser.",
    )
    parser.add_argument(
        "--output",
        metavar="XLSX_PATH",
        default=None,
        help=f"Output Excel file path (default: {EXCEL_FILE_PATH}).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )

    return parser


def main() -> None:
    """Main entry point: parse args and dispatch to single or batch mode."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Override log level if requested
    _setup_logging(level=args.log_level)

    # Override Excel output path if provided
    if args.output:
        os.environ["EXCEL_FILE_PATH"] = args.output
        # Re-import config value now that env var is updated
        import config
        config.EXCEL_FILE_PATH = args.output
        import excel_handler
        excel_handler.EXCEL_FILE_PATH = args.output

    logger.info("Test Case Automator – starting up.")

    if args.discover:
        # ── Discover mode: scan page and print available selectors ──
        discover_selectors(args.discover)

    elif args.batch:
        # ── Batch mode ──
        process_batch(args.batch, headless=args.headless)

    elif args.url and args.selector:
        # ── Single mode ──
        if not args.url.startswith(("http://", "https://")):
            logger.error("URL must start with http:// or https://")
            sys.exit(1)

        count = process_requirement(args.url, args.selector, headless=args.headless)
        if count == 0:
            logger.error("No test cases were generated. Check logs for details.")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)

    logger.info("Done. Output saved to: %s", os.environ.get("EXCEL_FILE_PATH", EXCEL_FILE_PATH))


if __name__ == "__main__":
    main()