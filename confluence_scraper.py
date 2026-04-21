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
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    InvalidSessionIdException,
)
from bs4 import BeautifulSoup
import socket

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


def _is_port_in_use(port: int) -> bool:
    """Quick check if a local port is listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def _build_driver(headless: bool = True) -> tuple[webdriver.Edge, bool]:
    """Build and return (driver, is_attached_to_existing_session)."""
    # 1. Try to attach to existing Edge on port 9222
    if _is_port_in_use(9222):
        try:
            debug_options = Options()
            debug_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            driver = webdriver.Edge(service=Service(), options=debug_options)

            # Increased timeouts for heavy Confluence pages
            driver.set_page_load_timeout(120)
            driver.set_script_timeout(60)

            # Health-check: verify the session is alive before returning
            try:
                current_url = driver.current_url
                v = driver.capabilities.get('browserVersion', 'unknown')
                logger.info("Connected to existing Edge (v%s). Current page: %s", v, current_url)
                return driver, True
            except (InvalidSessionIdException, WebDriverException):
                logger.warning(
                    "Port 9222 is open but the Edge session is stale/invalid. "
                    "Please close Edge completely, run start_edge.bat again, "
                    "log in to Confluence, then retry."
                )
                raise ValueError(
                    "Edge session is stale. Please:\n"
                    "1. Close all Edge windows\n"
                    "2. Run start_edge.bat again\n"
                    "3. Log in to Confluence in the new Edge window\n"
                    "4. Then retry."
                )
        except ValueError:
            raise   # re-raise our own clear error
        except Exception as e:
            logger.debug("Port 9222 was open but connection failed: %s", e)

    # 2. Fall back to fresh browser
    logger.info(
        "No existing Edge on port 9222 - launching fresh browser.\n"
        "Tip: start Edge with --remote-debugging-port=9222 to reuse your login."
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
    driver.set_page_load_timeout(120)
    driver.set_script_timeout(60)
    logger.debug("Fresh Edge WebDriver initialised (headless=%s)", headless)
    return driver, False  # attached = False -> safe to quit


def _safe_close_driver(driver: webdriver.Edge, is_attached: bool) -> None:
    """Release the driver safely. Never quit() or stop the service on an attached session."""
    if is_attached:
        # ── WHY session_id = None ──────────────────────────────────────────────
        # Selenium's WebDriver.__del__() does:
        #   if hasattr(self, 'session_id'): self.quit()
        # When this Python object is garbage-collected, __del__ would call
        # quit() which sends DELETE /session to msedgedriver, which CLOSES
        # the browser — even though we never called quit() ourselves.
        # Setting session_id = None makes __del__ skip the quit() call,
        # so the browser stays alive for the next scrape job.
        # service.stop() is intentionally NOT called: killing the msedgedriver
        # proxy leaves Edge's debug endpoint in a broken state, causing
        # 'invalid session id' errors on subsequent connections.
        try:
            driver.session_id = None
        except Exception:
            pass
        logger.debug("Released attached driver safely — browser stays alive.")
    else:
        try:
            driver.quit()
        except Exception:
            pass
        logger.debug("Fresh WebDriver session closed.")


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
    Reuses the existing Edge debug session on port 9222 if available.

    Args:
        url:      Full Confluence page URL.
        headless: Whether to run in headless mode (ignored for attached sessions).

    Returns:
        Structured text extracted from the Confluence page.

    Raises:
        ValueError: If content cannot be found or page is inaccessible.
    """
    driver, is_attached = _build_driver(headless)
    try:
        logger.info("Navigating to Confluence page: %s", url)
        driver.get(url)

        # Confluence + Atlassian SSO can take longer to redirect — wait more than Jira
        time.sleep(8)

        if _is_login_page(driver):
            if is_attached:
                # Attached to real Edge but still on login — user needs to log in
                raise ValueError(
                    "Confluence requires login. Please:\n"
                    "1. Switch to the Edge window that opened via start_edge.bat\n"
                    "2. Log in to your Atlassian / Confluence account\n"
                    "3. Navigate to the Confluence page manually once\n"
                    "4. Then re-submit the URL here."
                )
            else:
                raise ValueError(
                    "Confluence redirected to login and no Edge debug session found on port 9222.\n"
                    "Fix: Run start_edge.bat first, log in to Confluence, then try again."
                )

        _wait_for_page(driver)

        if _is_login_page(driver):
            raise ValueError(
                "Still on login/auth page after waiting. Please log in to Confluence in the "
                "Edge window (opened by start_edge.bat) and then re-submit."
            )

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

    except (ValueError, WebDriverException, InvalidSessionIdException) as exc:
        err_msg = str(exc)
        if "invalid session id" in err_msg.lower() or isinstance(exc, InvalidSessionIdException):
            logger.error(
                "Edge session became invalid during Confluence scraping. "
                "Close all Edge windows, run start_edge.bat, log in to Confluence, then retry."
            )
        logger.error("Confluence scraping failed: %s", exc)
        raise
    finally:
        _safe_close_driver(driver, is_attached)
