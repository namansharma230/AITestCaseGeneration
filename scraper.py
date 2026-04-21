"""
scraper.py
Selenium-based web scraper that extracts visible text from a CSS-selected section.

Features:
- Attaches to existing logged-in Edge session (no re-login needed)
- Detects login redirects with helpful error messages
- --discover mode: scans the page and prints all available selectors
- Auto-fallback: tries known Jira selectors if the primary one fails
- Auto-scroll to trigger lazy-loaded SPA content
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

from config import MAX_TEXT_LENGTH, SELENIUM_WAIT_SECONDS

logger = logging.getLogger(__name__)

_LOGIN_URL_HINTS: list[str] = [
    "login", "signin", "sign-in", "auth", "sso", "atlassian.net/login",
    "id.atlassian.com", "atlassian.com/login"
]

_JIRA_FALLBACK_SELECTORS: list[str] = [
    "[data-testid='issue-field-description']",
    "[data-testid='issue.views.field.rich-text.description']",
    "[data-testid='issue.views.issue-base.context.description.description-field.container--text']",
    "[data-component-selector='issue-field-description']",
    "[data-testid='ak-renderer-root']",
    "#description-val",
    ".description-wiki-markup",
    ".issue-body-content",
    "[data-testid='issue.views.issue-base.foundation.summary.heading']",
    "#details-module",
    "main",
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

            # Increased timeouts for complex/slow Jira pages
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
                    "log in to Jira, then retry."
                )
                raise ValueError(
                    "Edge session is stale. Please:\n"
                    "1. Close all Edge windows\n"
                    "2. Run start_edge.bat again\n"
                    "3. Log in to Jira in the new Edge window\n"
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


def _handle_login(driver: webdriver.Edge, target_url: str) -> None:
    logger.warning("Login page detected — pausing for manual login.")
    print("\n" + "=" * 65)
    print("  ACTION REQUIRED: Jira redirected to a login page.")
    print("  1. Log in to Jira in the Edge window.")
    print("  2. Wait until the Jira ticket is visible.")
    print("  3. Press ENTER here to continue.")
    print("=" * 65 + "\n")
    input("  Press ENTER after logging in... ")
    driver.get(target_url)
    time.sleep(4)


def _wait_for_page(driver: webdriver.Edge) -> None:
    try:
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        logger.warning("Page readyState timed out — continuing anyway.")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]
    return "\n".join(lines)


def discover_selectors(url: str) -> None:
    """
    Navigate to *url* and print every data-testid and id found on the page
    with a content preview so you can pick the right selector.

    Usage:
        python main.py --discover https://astrogo.atlassian.net/browse/ALTV-551
    """
    driver, is_attached = _build_driver(headless=False)
    try:
        logger.info("Discovering selectors on: %s", url)
        driver.get(url)
        time.sleep(3)
        _wait_for_page(driver)

        testids = driver.execute_script("""
            return [...document.querySelectorAll('[data-testid]')]
                .map(el => ({
                    testid: el.getAttribute('data-testid'),
                    text: el.innerText ? el.innerText.substring(0, 60).trim() : ''
                }));
        """)

        ids = driver.execute_script("""
            return [...document.querySelectorAll('[id]')]
                .filter(el => el.id)
                .map(el => ({
                    id: el.id,
                    text: el.innerText ? el.innerText.substring(0, 60).trim() : ''
                }));
        """)

        print("\n" + "=" * 72)
        print(f"  SELECTOR DISCOVERY: {url}")
        print("=" * 72)

        if testids:
            print(f"\n  -- data-testid attributes ({len(testids)} found) --\n")
            print(f"  {'SELECTOR TO USE':<65} CONTENT PREVIEW")
            print(f"  {'-'*64} {'-'*20}")
            for item in testids:
                sel = f"[data-testid='{item['testid']}']"
                preview = item['text'].replace('\n', ' ')[:30]
                print(f"  {sel:<65} {preview}")
        else:
            print("\n  No data-testid attributes found.")

        if ids:
            print(f"\n  -- id attributes ({len(ids)} found) --\n")
            print(f"  {'SELECTOR TO USE':<45} CONTENT PREVIEW")
            print(f"  {'-'*44} {'-'*20}")
            for item in ids:
                sel = f"#{item['id']}"
                preview = item['text'].replace('\n', ' ')[:30]
                print(f"  {sel:<45} {preview}")

        print("\n" + "=" * 72)
        print("  Pick the selector whose CONTENT PREVIEW matches the")
        print("  description / acceptance criteria of the ticket, then run:")
        print(f'  python main.py "{url}" "<your-selector>"')
        print("=" * 72 + "\n")
    finally:
        _safe_close_driver(driver, is_attached)


def _try_fallback_selectors(driver: webdriver.Edge) -> tuple[str, list]:
    """Try each Jira fallback selector and return the first one that matches."""
    for selector in _JIRA_FALLBACK_SELECTORS:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if elements:
            logger.info("Auto-fallback matched: %s", selector)
            return selector, elements
    return "", []


def scrape_section(url: str, selector: str, headless: bool = True) -> str:
    """
    Navigate to *url*, handle login if needed, find elements matching *selector*
    (with auto-fallback to built-in Jira selectors), and return cleaned text.
    """
    driver, is_attached = _build_driver(headless)
    try:
        logger.info("Navigating to: %s", url)
        driver.get(url)
        time.sleep(3)

        if _is_login_page(driver):
            if headless:
                raise ValueError(
                    "Jira redirected to login but browser is headless.\n"
                    f"Fix: python main.py \"{url}\" \"{selector}\" --no-headless"
                )
            _handle_login(driver, url)

        _wait_for_page(driver)

        if _is_login_page(driver):
            raise ValueError("Still on login page. Complete login and re-run.")

        # Try user-supplied selector first
        logger.info("Trying selector: %s", selector)
        elements = []
        matched_selector = selector

        try:
            WebDriverWait(driver, SELENIUM_WAIT_SECONDS).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
        except TimeoutException:
            logger.warning("Selector '%s' not found - trying Jira fallbacks...", selector)

        # Auto-fallback
        if not elements:
            matched_selector, elements = _try_fallback_selectors(driver)

        if not elements:
            logger.error("URL: %s | Title: %s", driver.current_url, driver.title)
            raise ValueError(
                f"Selector '{selector}' not found, and all Jira fallbacks failed.\n\n"
                "Run discover to see what's available on this page:\n"
                f'  python main.py --discover "{url}"'
            )

        logger.info("%d element(s) found using: %s", len(elements), matched_selector)

        text = _extract_text(
            "\n".join(el.get_attribute("outerHTML") for el in elements)
        )

        if not text:
            raise ValueError(f"Selector '{matched_selector}' matched but contained no text.")

        if len(text) > MAX_TEXT_LENGTH:
            logger.warning("Truncating text from %d to %d chars.", len(text), MAX_TEXT_LENGTH)
            text = text[:MAX_TEXT_LENGTH] + "\n... [truncated]"

        logger.info("Scraped %d characters.", len(text))
        return text

    except (ValueError, WebDriverException, InvalidSessionIdException) as exc:
        err_msg = str(exc)
        if "invalid session id" in err_msg.lower() or isinstance(exc, InvalidSessionIdException):
            logger.error(
                "Edge session became invalid during scraping. "
                "Close all Edge windows, run start_edge.bat, log in to Jira, then retry."
            )
        logger.error("Scraping failed: %s", exc)
        raise
    finally:
        _safe_close_driver(driver, is_attached)