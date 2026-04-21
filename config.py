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
# Model selection strategy for optimal free-tier usage:
#   - llama-3.1-8b-instant:  30 RPM, 6000 TPM, 14400 RPD  (best daily budget)
#   - llama-3.3-70b-versatile: 30 RPM, 6000 TPM, 1000 RPD (smarter but limited daily)
# We use llama-3.1-8b-instant for maximum daily throughput.
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = "llama-3.1-8b-instant"

# ── Active settings resolved from provider choice ────────────────────────────
if LLM_PROVIDER == "groq":
    MODEL: str = GROQ_MODEL
    ACTIVE_API_KEY: str = GROQ_API_KEY
    ACTIVE_BASE_URL: str = "https://api.groq.com/openai/v1"
else:
    MODEL: str = OPENAI_MODEL
    ACTIVE_API_KEY: str = OPENAI_API_KEY
    ACTIVE_BASE_URL: str = "https://api.openai.com/v1"

# ── Token Budget Management ──────────────────────────────────────────────────
# Groq free tier limits (llama-3.1-8b-instant):
#   TPM  = 6,000 tokens per minute
#   RPM  = 30 requests per minute
#   RPD  = 14,400 requests per day
# We must ensure input_tokens + output_tokens < TPM for each request.
#
# Budget math per chunk (with current settings):
#   usable     = 6000 * 0.82            = 4920 tokens
#   for input  = 4920 - overhead - 2200 = ~2320 tokens  (~9 280 chars)
#   → Increased output budget (2200) allows for exhaustive test cases without truncation.
GROQ_TPM_LIMIT: int = 6000          # tokens per minute cap
CHARS_PER_TOKEN: float = 4.0        # rough estimate for English text
PROMPT_OVERHEAD_TOKENS: int = 400    # system message + template boilerplate
SAFETY_MARGIN: float = 0.82         # leave 18% headroom
MAX_OUTPUT_TOKENS: int = 2200       # ↑ increased from 1800 for better exhaustiveness
CHUNK_DELAY_SECONDS: float = 62.0   # wait between chunks to reset TPM window
MAX_TOKENS: int = MAX_OUTPUT_TOKENS
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
# No hard limit on scraping — the LLM layer handles chunking automatically.
MAX_TEXT_LENGTH: int = 50000
SELENIUM_WAIT_SECONDS: int = 10

# Default CSS selector used for all ALTV Jira pages.
# Change this single value if the Jira DOM structure ever changes.
JIRA_CSS_SELECTOR: str = "[data-testid='issue.views.field.rich-text.description']"

# ── Confluence Scraper Settings ───────────────────────────────────────────
CONFLUENCE_MAX_TEXT_LENGTH: int = 50000  # No hard limit; chunking handles size
CONFLUENCE_WAIT_SECONDS: int = 15       # Confluence pages load slower

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR: str = "logs"
LOG_FILE: str = f"{LOG_DIR}/app.log"
LOG_LEVEL: str = "INFO"

# ── Prompt Template (legacy — used only as fallback) ──────────────────────────
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