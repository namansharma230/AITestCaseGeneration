import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ── Output Directory ──────────────────────────────────────────────────────────
# When running as a PyInstaller .exe, TESTCASE_OUTPUT_DIR is set by launcher.py
# Default: ~/Documents/TestCaseAutomator/  (clean, user-friendly location)
_output_dir_default = os.getenv(
    "TESTCASE_OUTPUT_DIR",
    str(Path.home() / "Documents" / "TestCaseAutomator")
)
Path(_output_dir_default).mkdir(parents=True, exist_ok=True)

# ── LLM Provider ──────────────────────────────────────────────────────────────
# Set to "groq" for free testing, switch to "openai" when you add billing.
# You can also set LLM_PROVIDER in your .env file.
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")

# ── OpenAI Settings ───────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = "gpt-4o-mini"

# ── Groq Settings (free, no credit card required) ─────────────────────────────
# Sign up free at: https://console.groq.com
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = "llama-3.3-70b-versatile"

# ── Active settings resolved from provider choice ────────────────────────────
if LLM_PROVIDER == "groq":
    MODEL: str = GROQ_MODEL
    ACTIVE_API_KEY: str = GROQ_API_KEY
    ACTIVE_BASE_URL: str = "https://api.groq.com/openai/v1"
else:
    MODEL: str = OPENAI_MODEL
    ACTIVE_API_KEY: str = OPENAI_API_KEY
    ACTIVE_BASE_URL: str = "https://api.openai.com/v1"

MAX_TOKENS: int = 32000
TEMPERATURE: float = 0.3
LLM_RETRIES: int = 3
LLM_RETRY_DELAY: float = 2.0

# ── Excel Settings ────────────────────────────────────────────────────────────
EXCEL_FILE_PATH: str = os.getenv(
    "EXCEL_FILE_PATH",
    str(Path(_output_dir_default) / "test_cases.xlsx")
)
SHEET_NAME: str = "Test Cases"

EXCEL_COLUMNS: dict[str, int] = {
    "id":               1,
    "title":            2,
    "preconditions":    3,
    "steps":            4,
    "expected_result":  5,
    "postconditions":   6,
    "priority":         7,
}

EXCEL_HEADERS: list[str] = [
    "Test Case ID",
    "Title",
    "Preconditions",
    "Steps",
    "Expected Result",
    "Postconditions",
    "Priority",
]

# ── Scraper Settings ──────────────────────────────────────────────────────────
MAX_TEXT_LENGTH: int = 5000
SELENIUM_WAIT_SECONDS: int = 10

# Default CSS selector used for all ALTV Jira pages.
# Change this single value if the Jira DOM structure ever changes.
JIRA_CSS_SELECTOR: str = "[data-testid='issue.views.field.rich-text.description']"

# ── Confluence Scraper Settings ───────────────────────────────────────────
CONFLUENCE_MAX_TEXT_LENGTH: int = 8000   # Wiki pages tend to be longer
CONFLUENCE_WAIT_SECONDS: int = 15       # Confluence pages load slower

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR: str = "logs"
LOG_FILE: str = f"{LOG_DIR}/app.log"
LOG_LEVEL: str = "INFO"

# ── Prompt Template ───────────────────────────────────────────────────────────
PROMPT_TEMPLATE: str = """You are a QA expert. Generate 5-10 comprehensive test cases for the following requirement section.

Requirement:
{scraped_text}

For each test case, output in STRICT JSON format (array of objects):
[
  {{
    "title": "Short descriptive title",
    "preconditions": "List any setup needed",
    "steps": ["1. Step one", "2. Step two"],
    "expected_result": "Exact expected outcome",
    "postconditions": "Cleanup or assertions",
    "priority": "High/Medium/Low"
  }}
]

Only output the JSON array. No extra text."""