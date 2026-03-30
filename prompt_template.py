import json
import logging
import re
import time
from typing import Any

import openai

from config import (
    ACTIVE_API_KEY,
    ACTIVE_BASE_URL,
    LLM_PROVIDER,
    MODEL,
    MAX_TOKENS,
    TEMPERATURE,
    LLM_RETRIES,
    LLM_RETRY_DELAY,
)

logger = logging.getLogger(__name__)

_client = openai.OpenAI(api_key=ACTIVE_API_KEY, base_url=ACTIVE_BASE_URL)

PROMPT_TEMPLATE = """You are a senior QA engineer. Your task is to generate DETAILED, NON-GENERIC test cases from the acceptance criteria below.

STRICT RULES — follow every rule without exception:

RULE 1 — COVERAGE (Most Important):
- Read the acceptance criteria and number every single point, sub-point, and condition you find.
- You MUST generate exactly ONE positive test case per point. No point can be skipped.
- If a point has sub-conditions (e.g. "Correct PIN → X happens, Wrong PIN → Y happens"), treat each sub-condition as a separate point with its own test case.
- At the END of the array, after all positive test cases, append all negative test cases grouped together.

RULE 2 — STEPS:
- Every test case must have a MINIMUM of 5 steps.
- Steps must be highly specific. Include: exact page names, button labels, field names, input values, expected UI states.
- BAD step (never do this): "Click Submit"
- GOOD step: "Click the 'Rent Now' button on the Content Detail Page for the movie 'Inception (2010)'"

RULE 3 — EXPECTED RESULTS:
- Must be specific and measurable.
- BAD: "The feature works correctly"
- GOOD: "A confirmation pop-up appears with title 'Confirm Purchase', content name 'Inception', price '₹199', and two buttons: 'OK' (default) and 'Cancel'"

RULE 4 — NEGATIVE TEST CASES:
- After ALL positive test cases are listed, add negative test cases.
- Cover: invalid inputs, missing fields, boundary conditions, unauthorized actions, network errors, wrong credentials.
- Title must start with "Negative -" so they are easy to identify.
- Group all negatives at the end of the JSON array.

RULE 5 — NO DUPLICATES:
- Do not repeat the same scenario twice even if it appears in multiple points.

Acceptance Criteria:
{scraped_text}

Output ONLY a valid JSON array. No explanation. No markdown. No extra text.

[
  {{
    "title": "Positive - [exact point being tested]",
    "priority": "High/Medium/Low",
    "preconditions": "Specific setup — logged-in user, device type, subscription status, content state",
    "test_data": "Exact input values, credentials, content titles, PINs, prices",
    "steps": [
      "1. Navigate to [exact page name]",
      "2. Locate [exact UI element name]",
      "3. Enter/Click/Select [exact value or element]",
      "4. Observe [exact system response or UI change]",
      "5. Verify [exact expected state or message]"
    ],
    "expected_result": "Specific, measurable outcome with exact UI text, states, or values"
  }},
  {{
    "title": "Negative - [failure scenario being tested]",
    "priority": "High/Medium/Low",
    "preconditions": "Specific setup for the failure condition",
    "test_data": "Invalid or boundary input values",
    "steps": [
      "1. Navigate to [exact page name]",
      "2. Reproduce the failure condition step by step",
      "3. Enter [invalid/boundary value] in [exact field name]",
      "4. Click [exact button name]",
      "5. Observe the system error response"
    ],
    "expected_result": "Exact error message text, blocked state, or failure behaviour expected"
  }}
]"""


def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences (```json ... ``` or ``` ... ```) from LLM output."""
    # Remove opening fence: ```json or ```
    cleaned = re.sub(r'^\s*```(?:json)?\s*\n?', '', raw, count=1)
    # Remove closing fence
    cleaned = re.sub(r'\n?\s*```\s*$', '', cleaned)
    return cleaned.strip()


def _extract_json(raw: str) -> list[dict[str, Any]]:
    # Attempt 1 — direct parse
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Attempt 2 — strip code fences first, then parse
    stripped = _strip_code_fences(raw)
    if stripped != raw:
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                logger.info("Parsed JSON after stripping code fences.")
                return parsed
        except json.JSONDecodeError:
            pass

    # Attempt 3 — regex: find outermost [...] in the text
    match = re.search(r'\[.*\]', stripped, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                logger.warning("Used regex fallback to extract JSON array.")
                return parsed
        except json.JSONDecodeError:
            pass

    logger.error("Could not parse LLM response as JSON.")
    logger.warning("Raw LLM output (first 500 chars):\n%s", raw[:500])
    return [{
        "title": "PARSE_ERROR – manual review required",
        "priority": "High",
        "preconditions": "N/A",
        "test_data": "N/A",
        "steps": ["1. Review raw LLM output in logs/app.log"],
        "expected_result": "N/A",
    }]


def _normalize_steps(steps: Any) -> list[str]:
    if isinstance(steps, str):
        steps = [s.strip() for s in re.split(r'\n|\d+\.', steps) if s.strip()]
    if not isinstance(steps, list):
        return ["1. No steps provided"]
    normalized = []
    for i, step in enumerate(steps, start=1):
        step_text = re.sub(r'^\d+[\.\)]\s*', '', str(step).strip())
        normalized.append(f"{i}. {step_text}")
    return normalized


def _validate_test_case(tc: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "title": "Untitled Test Case",
        "priority": "Medium",
        "preconditions": "None",
        "test_data": "None",
        "steps": ["1. No steps provided"],
        "expected_result": "Not specified",
    }
    for key, default in defaults.items():
        if key not in tc or not tc[key]:
            logger.warning("Test case missing '%s'; using default.", key)
            tc[key] = default

    tc["steps"] = _normalize_steps(tc["steps"])

    # Pad to minimum 5 steps if LLM returned fewer
    while len(tc["steps"]) < 5:
        tc["steps"].append(
            f"{len(tc['steps']) + 1}. Verify the UI state reflects the expected outcome"
        )

    return tc


def generate_test_cases(scraped_text: str) -> list[dict[str, Any]]:
    if not ACTIVE_API_KEY:
        provider_hint = "GROQ_API_KEY" if LLM_PROVIDER == "groq" else "OPENAI_API_KEY"
        signup_hint = (
            "Sign up free at https://console.groq.com"
            if LLM_PROVIDER == "groq"
            else "Get a key at https://platform.openai.com/api-keys"
        )
        raise EnvironmentError(
            f"{provider_hint} is not set in your .env file.\n{signup_hint}"
        )

    prompt = PROMPT_TEMPLATE.format(scraped_text=scraped_text)
    last_error: Exception | None = None

    for attempt in range(1, LLM_RETRIES + 1):
        logger.info("LLM call attempt %d/%d (provider: %s) …", attempt, LLM_RETRIES, LLM_PROVIDER)
        try:
            response = _client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior QA engineer. "
                            "Always respond with a valid JSON array only. "
                            "No markdown, no explanation, no code fences."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=MAX_TOKENS,
                temperature=max(0.2, min(TEMPERATURE, 0.3)),
            )

            raw = response.choices[0].message.content or ""
            raw = _strip_code_fences(raw)

            test_cases = _extract_json(raw)
            validated = [_validate_test_case(tc) for tc in test_cases]
            logger.info("Received and validated %d test case(s).", len(validated))
            return validated

        except openai.RateLimitError as exc:
            logger.warning("Rate limit on attempt %d: %s", attempt, exc)
            last_error = exc
            time.sleep(LLM_RETRY_DELAY * attempt)
        except openai.APIError as exc:
            logger.warning("API error on attempt %d: %s", attempt, exc)
            last_error = exc
            time.sleep(LLM_RETRY_DELAY)

    raise RuntimeError(
        f"LLM call failed after {LLM_RETRIES} attempts. Last error: {last_error}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Confluence Page — Prompt Template & Generator
# ══════════════════════════════════════════════════════════════════════════════

CONFLUENCE_PROMPT_TEMPLATE = """You are a senior QA engineer writing exhaustive, granular test cases from a Confluence specification page. Your goal is COMPLETE, LINE-BY-LINE coverage — never summarise, never skip, never merge points together.

═══════════════════════════════════════════════════════════
STRICT RULES — follow every rule without exception
═══════════════════════════════════════════════════════════

RULE 1 — EXHAUSTIVE COVERAGE (Most Critical):
- Go through the specification LINE BY LINE. Number every single statement, bullet point, sub-bullet, table row, condition, and requirement you find.
- You MUST generate a SEPARATE test case for EACH individual point. Do NOT combine multiple points into one test case.
- If the document says "Feature X supports A, B, and C" — that is THREE separate test cases, one for A, one for B, one for C.
- If a table has 10 rows, generate at least 10 test cases (one per row), plus additional ones if rows have sub-conditions.
- If a section describes behaviour for different device types, platforms, or user roles — create a SEPARATE test case for EACH device/platform/role.
- If a requirement has conditions (e.g. "when X then Y, otherwise Z") — create separate test cases for EACH branch.
- NEVER summarise multiple requirements into a single test case. Each test case must trace back to exactly ONE specific statement in the specification.
- Cover every heading, every paragraph, every bullet point, every table cell, every note, every panel.
- If you are unsure whether two points are different — treat them as different and create separate test cases.
- After ALL positive test cases, append negative test cases at the end.

RULE 2 — DETAILED STEPS (Minimum 7 steps per test case):
- Every test case must have a MINIMUM of 7 detailed steps.
- Each step must be an atomic action — one click, one input, one observation per step.
- Include: exact screen/page names, menu paths, button labels, field names, dropdown values, exact text to type, exact checkbox/radio to select.
- Describe what the user SEES after each action (loading states, transitions, confirmations).
- BAD step: "Configure the settings"
- BAD step: "Verify the feature works"
- GOOD step: "Navigate to Settings > Content Management > Genre Configuration page"
- GOOD step: "In the 'Genre Name' text field, type 'Action' and press Enter"  
- GOOD step: "Observe that the loading spinner appears for approximately 2 seconds, then a grid of content cards is displayed"
- GOOD step: "Verify that each content card shows: poster image (16:9 aspect ratio), title text (bold, max 2 lines), genre badge ('Action' in blue), and a 'Play' button overlay on hover"

RULE 3 — DETAILED EXPECTED RESULTS:
- Must describe the EXACT expected outcome with specific values, text, UI elements, states, and measurements.
- Reference exact field names, error messages, UI labels, counts, formats, and positions.
- BAD: "The feature works correctly"
- BAD: "Content is displayed"
- GOOD: "The 'Learn Action' report page displays a data table with columns: 'Date', 'User ID', 'Action Type', 'Content Title', 'Duration (seconds)'. The table shows the 20 most recent actions sorted by date descending. Each row has alternating white/grey background. A 'Download CSV' button is visible in the top-right corner."
- GOOD: "The system returns HTTP 200 with a JSON response containing 'status: success', 'reportId: [UUID format]', and 'generatedAt: [ISO 8601 timestamp]'. The report file is available for download within 5 seconds."

RULE 4 — DETAILED PRECONDITIONS & TEST DATA:
- Preconditions must list EVERY setup requirement: user role, device model/type, OS version, app version, network state, account type, subscription status, content availability, feature flags, previous actions needed.
- Test data must include EXACT values: specific content titles, specific user credentials (use placeholders like 'testuser@example.com'), specific device models, specific configuration values, specific date ranges.

RULE 5 — NEGATIVE TEST CASES (Exhaustive):
- After ALL positive test cases, add comprehensive negative test cases.
- For EACH feature or requirement, think about what could go wrong:
  * Unsupported device types or platforms
  * Invalid input values (empty, too long, special characters, SQL injection, XSS)
  * Missing required fields or configurations
  * Network errors (timeout, no connectivity, slow connection)
  * Unauthorized access (wrong role, expired session, revoked permissions)
  * Boundary conditions (0, max value, one above max, one below min)
  * Race conditions (double-click, rapid navigation)
  * Data not found / empty state scenarios
  * Concurrent user scenarios
- Title must start with "Negative -" so they are easy to identify.
- Group all negatives at the end of the JSON array.

RULE 6 — NO DUPLICATES, NO SKIPPING:
- Do not repeat the same scenario, but do not skip any point either.
- When in doubt, create the test case — it is better to have too many test cases than to miss a requirement.

═══════════════════════════════════════════════════════════

Specification/Documentation:
{scraped_text}

═══════════════════════════════════════════════════════════
OUTPUT FORMAT — ONLY a valid JSON array. No explanation. No markdown. No extra text.
═══════════════════════════════════════════════════════════

[
  {{
    "title": "Positive - [exact requirement/point being tested — reference the specific line/bullet from the spec]",
    "priority": "High/Medium/Low",
    "preconditions": "1. User role: [exact role]. 2. Device: [exact model/type]. 3. App version: [version]. 4. Account: [type/status]. 5. Pre-existing state: [any setup actions completed]. 6. Feature flags: [if applicable].",
    "test_data": "Username: testuser@example.com, Device: [model], Content: '[exact title]', Configuration: [exact settings], Input values: [exact values to use]",
    "steps": [
      "1. [Exact navigation action with full menu path]",
      "2. [Exact element interaction with element name/label]",
      "3. [Exact input with specific values to enter]",
      "4. [Exact observation of UI response/transition]",
      "5. [Exact verification of intermediate state]",
      "6. [Exact next action in the workflow]",
      "7. [Exact final verification with specific values/text to check]"
    ],
    "expected_result": "Detailed, measurable outcome: exact UI text displayed, exact values shown, exact layout/format, exact counts, exact states of all relevant elements, exact error messages if applicable"
  }},
  {{
    "title": "Negative - [exact failure/edge scenario — reference what could go wrong for which requirement]",
    "priority": "High/Medium/Low",
    "preconditions": "Specific setup that creates the failure condition — device in wrong state, missing permission, invalid configuration",
    "test_data": "Invalid/boundary values: empty fields, max+1 length strings, special characters, wrong device model, expired tokens",
    "steps": [
      "1. [Setup the failure condition precisely]",
      "2. [Navigate to the relevant feature/page]",
      "3. [Attempt the action that should fail]",
      "4. [Enter specific invalid/boundary values]",
      "5. [Trigger the submission/action]",
      "6. [Observe the system's error response]",
      "7. [Verify error handling — message text, UI state, data integrity]"
    ],
    "expected_result": "Exact error message text, exact error code, exact UI state (disabled buttons, red borders, warning banners), exact fallback behaviour, confirmation that no data corruption occurred"
  }}
]"""


def generate_confluence_test_cases(scraped_text: str) -> list[dict[str, Any]]:
    """Generate test cases from Confluence page content using a spec-optimized prompt."""
    if not ACTIVE_API_KEY:
        provider_hint = "GROQ_API_KEY" if LLM_PROVIDER == "groq" else "OPENAI_API_KEY"
        signup_hint = (
            "Sign up free at https://console.groq.com"
            if LLM_PROVIDER == "groq"
            else "Get a key at https://platform.openai.com/api-keys"
        )
        raise EnvironmentError(
            f"{provider_hint} is not set in your .env file.\n{signup_hint}"
        )

    prompt = CONFLUENCE_PROMPT_TEMPLATE.format(scraped_text=scraped_text)
    last_error: Exception | None = None

    for attempt in range(1, LLM_RETRIES + 1):
        logger.info("LLM call attempt %d/%d (provider: %s, source: Confluence) …", attempt, LLM_RETRIES, LLM_PROVIDER)
        try:
            response = _client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior QA engineer specializing in test case generation "
                            "from technical specifications and documentation. "
                            "Always respond with a valid JSON array only. "
                            "No markdown, no explanation, no code fences."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=MAX_TOKENS,
                temperature=max(0.2, min(TEMPERATURE, 0.3)),
            )

            raw = response.choices[0].message.content or ""
            raw = _strip_code_fences(raw)

            test_cases = _extract_json(raw)
            validated = [_validate_test_case(tc) for tc in test_cases]
            logger.info("Received and validated %d Confluence test case(s).", len(validated))
            return validated

        except openai.RateLimitError as exc:
            logger.warning("Rate limit on attempt %d: %s", attempt, exc)
            last_error = exc
            time.sleep(LLM_RETRY_DELAY * attempt)
        except openai.APIError as exc:
            logger.warning("API error on attempt %d: %s", attempt, exc)
            last_error = exc
            time.sleep(LLM_RETRY_DELAY)

    raise RuntimeError(
        f"LLM call failed after {LLM_RETRIES} attempts. Last error: {last_error}"
    )