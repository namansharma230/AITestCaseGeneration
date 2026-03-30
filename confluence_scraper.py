"""
confluence_scraper.py
Selenium-based web scraper for Confluence wiki pages.

Extracts structured content (headings, tables, panels, lists) from
Confluence pages using known Confluence DOM selectors.
Reuses the same Edge debug-port attachment as scraper.py.
"""

import logging
import time

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

from config import CONFLUENCE_MAX_TEXT_LENGTH, CONFLUENCE_WAIT_SECONDS

logger = logging.getLogger(__name__)

_LOGIN_URL_HINTS: list[str] = [
    "login", "signin", "sign-in", "auth", "sso", "atlassian.net/login",
    "id.atlassian.com", "atlassian.com/login"
]

# Confluence content selectors — ordered from most specific to broadest
_CONFLUENCE_CONTENT_SELECTORS: list[str] = [
    "#content-body",
    "[data-testid='page-content']",
    ".ak-renderer-document",
    "#main-content",
    ".wiki-content",
    "[role='presentation'] .ak-renderer-document",
    "#content .page-content",
    "#content",
    "main",
]

# Selectors for the page title
_TITLE_SELECTORS: list[str] = [
    "#title-text",
    "[data-testid='title-text']",
    "h1",
]


def _build_driver(headless: bool = True) -> webdriver.Edge:
    """Build and return a Microsoft Edge WebDriver, attaching to port 9222 if available."""
    try:
        debug_options = Options()
        debug_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        driver = webdriver.Edge(service=Service(), options=debug_options)
        driver.set_page_load_timeout(60)
        logger.info("✓ Connected to existing Edge session. Current page: %s", driver.current_url)
        return driver
    except Exception:
        logger.info(
            "No existing Edge on port 9222 — launching fresh browser.\n"
            "Tip: start Edge with --remote-debugging-port=9222 to reuse your login:\n"
            '  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" '
            '--remote-debugging-port=9222 --user-data-dir="C:\\EdgeDebug"'
        )

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    )
    driver = webdriver.Edge(service=Service(), options=options)
    driver.set_page_load_timeout(60)
    logger.debug("Fresh Edge WebDriver initialised (headless=%s)", headless)
    return driver


def _is_login_page(driver: webdriver.Edge) -> bool:
    return any(hint in driver.current_url.lower() for hint in _LOGIN_URL_HINTS)


def _wait_for_page(driver: webdriver.Edge) -> None:
    """Wait for page readyState and scroll to trigger lazy content."""
    try:
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        logger.warning("Page readyState timed out — continuing anyway.")

    # Scroll to trigger lazy-loaded Confluence content
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
    time.sleep(1.5)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 2 / 3);")
    time.sleep(1.5)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)


def _get_page_title(driver: webdriver.Edge) -> str:
    """Extract the Confluence page title."""
    for selector in _TITLE_SELECTORS:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if elements:
            title = elements[0].text.strip()
            if title:
                return title
    return driver.title or "Untitled Page"


def _extract_structured_text(html: str) -> str:
    """
    Parse Confluence page HTML and extract structured text preserving
    headings, tables, panels, and list structure.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove scripts, styles, and other non-content elements
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()

    lines: list[str] = []

    for element in soup.descendants:
        if not hasattr(element, 'name') or element.name is None:
            continue

        # Headings → preserve hierarchy
        if element.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(element.name[1])
            prefix = "#" * level
            heading_text = element.get_text(strip=True)
            if heading_text:
                lines.append(f"\n{prefix} {heading_text}")

        # Tables → structured extraction
        elif element.name == 'table':
            table_lines = _extract_table(element)
            if table_lines:
                lines.append("\n" + "\n".join(table_lines))

        # Confluence panels (info, note, warning panels)
        elif element.name == 'div' and element.get('class'):
            classes = " ".join(element.get('class', []))
            if any(kw in classes for kw in ['panel', 'confluence-information-macro', 'info-macro']):
                panel_title = ""
                title_el = element.find(class_=lambda c: c and ('title' in c or 'header' in c))
                if title_el:
                    panel_title = title_el.get_text(strip=True)
                panel_body = element.find(class_=lambda c: c and ('body' in c or 'content' in c))
                if panel_body:
                    body_text = panel_body.get_text(separator="\n", strip=True)
                    if body_text:
                        header = f"[Panel: {panel_title}]" if panel_title else "[Panel]"
                        lines.append(f"\n{header}\n{body_text}")

        # Paragraphs
        elif element.name == 'p':
            text = element.get_text(strip=True)
            if text and not _is_inside_processed_element(element):
                lines.append(text)

        # List items
        elif element.name == 'li':
            text = element.get_text(strip=True)
            if text and not _is_inside_processed_element(element):
                # Check if ordered or unordered
                parent = element.find_parent(['ol', 'ul'])
                if parent and parent.name == 'ol':
                    idx = list(parent.find_all('li')).index(element) + 1
                    lines.append(f"  {idx}. {text}")
                else:
                    lines.append(f"  • {text}")

    # Deduplicate consecutive identical lines
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and (not cleaned or cleaned[-1].strip() != stripped):
            cleaned.append(line)

    return "\n".join(cleaned)


def _is_inside_processed_element(element) -> bool:
    """Check if element is inside a table or panel we already extracted."""
    for parent in element.parents:
        if parent.name == 'table':
            return True
        if parent.name == 'div' and parent.get('class'):
            classes = " ".join(parent.get('class', []))
            if any(kw in classes for kw in ['panel', 'confluence-information-macro', 'info-macro']):
                return True
    return False


def _extract_table(table_element) -> list[str]:
    """Convert an HTML table to structured text rows."""
    rows = table_element.find_all('tr')
    if not rows:
        return []

    table_lines: list[str] = []
    for row in rows:
        cells = row.find_all(['th', 'td'])
        cell_texts = [cell.get_text(separator=" ", strip=True) for cell in cells]
        if any(cell_texts):
            line = " | ".join(cell_texts)
            # Mark header rows
            if row.find('th'):
                table_lines.append(f"[Header] {line}")
            else:
                table_lines.append(f"  {line}")

    return table_lines


def _try_confluence_selectors(driver: webdriver.Edge) -> tuple[str, list]:
    """Try each Confluence content selector and return the first one that matches."""
    for selector in _CONFLUENCE_CONTENT_SELECTORS:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if elements:
            # Verify the element actually has meaningful text content
            text = elements[0].text.strip()
            if len(text) > 50:  # Minimum content threshold
                logger.info("✓ Confluence content found using: %s", selector)
                return selector, elements
    return "", []


def scrape_confluence_page(url: str, headless: bool = True) -> str:
    """
    Navigate to a Confluence wiki page, extract structured content,
    and return cleaned text suitable for LLM test-case generation.

    No CSS selector needed — automatically detects Confluence content areas.

    Args:
        url:      Full Confluence page URL.
        headless: Whether to run in headless mode.

    Returns:
        Structured text extracted from the Confluence page.

    Raises:
        ValueError: If content cannot be found or page is inaccessible.
    """
    driver = _build_driver(headless)
    try:
        logger.info("Navigating to Confluence page: %s", url)
        driver.get(url)
        time.sleep(4)  # Confluence pages can be slower to render

        if _is_login_page(driver):
            if headless:
                raise ValueError(
                    "Confluence redirected to login but browser is headless.\n"
                    "Fix: Start Edge with --remote-debugging-port=9222 and log in first."
                )
            logger.warning("Login page detected — waiting for manual login.")
            raise ValueError(
                "Login required. Please start Edge with:\n"
                '  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" '
                '--remote-debugging-port=9222 --user-data-dir="C:\\EdgeDebug"\n'
                "Then log in to Confluence and try again."
            )

        _wait_for_page(driver)

        if _is_login_page(driver):
            raise ValueError("Still on login page. Complete login and re-run.")

        # Get page title
        page_title = _get_page_title(driver)
        logger.info("Page title: %s", page_title)

        # Try to find content
        logger.info("Searching for Confluence content...")
        matched_selector, elements = _try_confluence_selectors(driver)

        if not elements:
            logger.error("URL: %s | Title: %s", driver.current_url, driver.title)
            raise ValueError(
                f"Could not find Confluence page content.\n"
                f"Tried selectors: {', '.join(_CONFLUENCE_CONTENT_SELECTORS)}\n"
                f"Page may not have loaded correctly or the structure is unexpected."
            )

        # Extract structured text from the matched content area
        raw_html = "\n".join(el.get_attribute("outerHTML") for el in elements)
        text = _extract_structured_text(raw_html)

        if not text or len(text.strip()) < 20:
            raise ValueError(
                f"Selector '{matched_selector}' matched but contained insufficient text content."
            )

        # Prepend the page title
        full_text = f"# {page_title}\n\n{text}"

        if len(full_text) > CONFLUENCE_MAX_TEXT_LENGTH:
            logger.warning(
                "Truncating Confluence text from %d to %d chars.",
                len(full_text), CONFLUENCE_MAX_TEXT_LENGTH,
            )
            full_text = full_text[:CONFLUENCE_MAX_TEXT_LENGTH] + "\n... [truncated]"

        logger.info("Scraped %d characters from Confluence page.", len(full_text))
        return full_text

    except (ValueError, WebDriverException) as exc:
        logger.error("Confluence scraping failed: %s", exc)
        raise
    finally:
        driver.quit()
        logger.debug("WebDriver session closed.")
