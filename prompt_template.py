"""
prompt_template.py
Generates test cases via Groq / OpenAI LLM with smart chunking to stay
within the free-tier token budget (6 000 TPM for Groq).

Strategy:
  1. Estimate total tokens (prompt overhead + input + max_output).
  2. If it fits in one request - send directly.
  3. If not - split input text into safe-sized chunks, process each with
     a 62-second delay between calls to reset the TPM window.
  4. Merge all test-case arrays into a single list.
"""

import json
import logging
import math
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
    GROQ_TPM_LIMIT,
    CHARS_PER_TOKEN,
    PROMPT_OVERHEAD_TOKENS,
    SAFETY_MARGIN,
    MAX_OUTPUT_TOKENS,
    CHUNK_DELAY_SECONDS,
)

logger = logging.getLogger(__name__)

_client = openai.OpenAI(api_key=ACTIVE_API_KEY, base_url=ACTIVE_BASE_URL)


# ===========================================================================
# Token budget helpers
# ===========================================================================

def _estimate_tokens(text: str) -> int:
    """Rough token count - approx 1 token per 4 characters for English."""
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def _max_input_tokens() -> int:
    """How many input tokens we can safely use per request."""
    usable = int(GROQ_TPM_LIMIT * SAFETY_MARGIN)
    return usable - PROMPT_OVERHEAD_TOKENS - MAX_OUTPUT_TOKENS


def _chunk_text(text: str, max_chars: int) -> list[str]:
    """
    Split text into chunks of at most *max_chars* characters.
    Tries to break on paragraph boundaries (double newline), then single
    newlines, then hard-cuts as last resort.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        # Try to find a paragraph break within the safe window
        slice_ = remaining[:max_chars]
        cut = slice_.rfind("\n\n")
        if cut < max_chars // 3:
            # No good paragraph break; try single newline
            cut = slice_.rfind("\n")
        if cut < max_chars // 3:
            # No good newline; try sentence boundary
            cut = slice_.rfind(". ")
            if cut > 0:
                cut += 1  # include the period
        if cut < max_chars // 3:
            # Hard cut
            cut = max_chars

        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].strip()

    return chunks


# ===========================================================================
# Compact prompt templates - minimise token overhead
# ===========================================================================

PROMPT_TEMPLATE = (
    "You are a senior QA engineer. Generate test cases from these requirements.\n\n"
    "RULES:\n"
    "1. One row per requirement. One negative case for every 3 positive cases.\n"
    "2. STEPS: 5+ specific steps - include names, buttons, and exact input values.\n"
    "3. EXPECTED: Specific UI states, text, or errors.\n"
    "4. DESCRIPTION: A brief 1-2 sentence summary of what this test case verifies.\n"
    "5. PLATFORM: The target platform or environment (e.g. Web, Android, iOS, API, Desktop, Cross-platform).\n"
    "6. NO MARKDOWN: Output only a valid JSON array. No explanations.\n"
    "7. FIELD TYPES: All values MUST be simple strings. NO NESTED OBJECTS.\n\n"
    "Requirements:\n{scraped_text}\n\n"
    "[\n"
    "  {{\n"
    '    "title": "Positive/Negative - [brief point]",\n'
    '    "description": "Brief summary of what this test verifies",\n'
    '    "priority": "High/Medium/Low",\n'
    '    "platform": "Web/Android/iOS/API/Desktop/Cross-platform",\n'
    '    "preconditions": "User role, device state",\n'
    '    "test_data": "String of exact inputs (NO OBJECTS)",\n'
    '    "steps": ["1. Step...", "2. ..."],\n'
    '    "expected_result": "Exact outcome"\n'
    "  }}\n"
    "]"
)


CONFLUENCE_PROMPT_TEMPLATE = (
    "You are a senior QA. Generate exhaustive test cases from this spec.\n\n"
    "RULES:\n"
    "1. ATOMIC: One case per bullet/row. No merging.\n"
    "2. STEPS: 7+ specific steps with UI labels.\n"
    "3. NEGATIVES: Cover errors/auth for every feature.\n"
    "4. DESCRIPTION: A brief 1-2 sentence summary of what this test case verifies.\n"
    "5. PLATFORM: The target platform or environment (e.g. Web, Android, iOS, API, Desktop, Cross-platform).\n"
    "6. NO MARKDOWN: Output only valid JSON array. No explanations.\n"
    "7. FIELD TYPES: All values MUST be simple strings. NO NESTED OBJECTS.\n\n"
    "Spec:\n{scraped_text}\n\n"
    "[\n"
    "  {{\n"
    '    "title": "...",\n'
    '    "description": "Brief summary of what this test verifies",\n'
    '    "priority": "...",\n'
    '    "platform": "Web/Android/iOS/API/Desktop/Cross-platform",\n'
    '    "preconditions": "...",\n'
    '    "test_data": "String (NO OBJECTS)",\n'
    '    "steps": ["1. Step...", "2. ..."],\n'
    '    "expected_result": "..."\n'
    "  }}\n"
    "]"
)


# ===========================================================================
# JSON extraction helpers
# ===========================================================================

def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences from LLM output."""
    cleaned = re.sub(r'^\s*```(?:json)?\s*\n?', '', raw, count=1)
    cleaned = re.sub(r'\n?\s*```\s*$', '', cleaned)
    return cleaned.strip()


def _repair_json(raw_text: str) -> str:
    """
    Tries to repair truncated JSON by closing unclosed strings, objects, and arrays.
    Essential for free-tier LLMs that hit token limits mid-generation.
    """
    text = raw_text.strip()
    if not text:
        return ""

    stack = []
    is_in_string = False
    is_escaped = False
    
    chars = []
    for char in text:
        chars.append(char)
        if is_in_string:
            if is_escaped:
                is_escaped = False
            elif char == '\\':
                is_escaped = True
            elif char == '"':
                is_in_string = False
        else:
            if char == '"':
                is_in_string = True
            elif char == '{':
                stack.append('}')
            elif char == '[':
                stack.append(']')
            elif char == '}':
                if stack and stack[-1] == '}':
                    stack.pop()
            elif char == ']':
                if stack and stack[-1] == ']':
                    stack.pop()
    
    repaired = "".join(chars)
    if is_in_string:
        repaired += '"'
    
    # Close unclosed structures in reverse order
    while stack:
        closing_char = stack.pop()
        # Remove trailing comma before closing if present
        repaired = re.sub(r',\s*$', '', repaired)
        repaired += closing_char
        
    return repaired


def _extract_json(raw: str) -> tuple[list[dict[str, Any]], bool]:
    """
    Parse a JSON array from LLM output.
    Returns: (list_of_items, was_truncated)
    """
    stripped = _strip_code_fences(raw)
    
    # Strategy 1 - direct parse
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed, False
        if isinstance(parsed, dict):
            return [parsed], False
    except json.JSONDecodeError:
        pass

    # Strategy 2 - regex: find outermost [...]
    match = re.search(r'\[.*\]', stripped, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                logger.debug("Used regex fallback to extract JSON array.")
                return parsed, False
        except json.JSONDecodeError:
            pass

    # Strategy 3 - Robust state-based repair for truncated JSON
    repaired = _repair_json(stripped)
    if repaired != stripped:
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, list):
                logger.info("Successfully repaired truncated JSON (len: %d -> %d)", 
                            len(stripped), len(repaired))
                return parsed, True
        except json.JSONDecodeError:
            pass

    logger.error("Could not parse or repair JSON from LLM. Raw sample: %s...", raw[:200])
    return [], False


def _normalize_steps(steps) -> list[str]:
    """Ensure steps is a list of strings."""
    if isinstance(steps, str):
        return [s.strip() for s in steps.split("\n") if s.strip()]
    if isinstance(steps, list):
        result = []
        for s in steps:
            if isinstance(s, str):
                result.append(s.strip())
            elif isinstance(s, dict):
                result.append(str(s))
        return result
    return [str(steps)]


def _validate_test_case(tc: dict[str, Any]) -> dict[str, Any]:
    """Ensure every test case has all required fields and normalised steps/data."""
    defaults = {
        "title": "Untitled Test Case",
        "description": "No description provided",
        "preconditions": "None",
        "steps": ["1. Execute the test scenario"],
        "expected_result": "Verify the expected behaviour",
        "test_data": "N/A",
        "priority": "Medium",
        "platform": "N/A",
    }
    for key, default in defaults.items():
        if key not in tc or not tc[key]:
            tc[key] = default

    # Force steps to list
    tc["steps"] = _normalize_steps(tc["steps"])
    
    # Force test_data to string (prevents parsing errors if LLM returns an object)
    if not isinstance(tc["test_data"], str):
        tc["test_data"] = json.dumps(tc["test_data"])

    # Pad to minimum 5 steps if LLM returned fewer
    while len(tc["steps"]) < 5:
        tc["steps"].append(
            f"{len(tc['steps']) + 1}. Verify the UI state reflects the expected outcome"
        )

    return tc


# ===========================================================================
# Core LLM call with adaptive token management
# ===========================================================================

def _call_llm_for_test_cases(
    prompt: str,
    system_msg: str,
    max_output: int | None = None,
) -> list[dict[str, Any]]:
    """
    Make a single LLM call and return parsed test cases.
    Calculates safe max_tokens based on input size to avoid 413/429 errors.
    """
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

    # Adaptive max_tokens: leave room for input within TPM budget
    input_tokens = _estimate_tokens(prompt) + _estimate_tokens(system_msg)
    usable_tpm = int(GROQ_TPM_LIMIT * SAFETY_MARGIN)
    safe_output = max(500, usable_tpm - input_tokens)
    safe_output = min(safe_output, max_output or MAX_OUTPUT_TOKENS)

    logger.info(
        "Token budget: input~%d, output_cap=%d, total~%d (limit=%d)",
        input_tokens, safe_output, input_tokens + safe_output, GROQ_TPM_LIMIT,
    )

    last_error: Exception | None = None

    for attempt in range(1, LLM_RETRIES + 1):
        logger.info(
            "LLM call attempt %d/%d (provider: %s, model: %s)",
            attempt, LLM_RETRIES, LLM_PROVIDER, MODEL,
        )
        try:
            response = _client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=safe_output,
                temperature=max(0.2, min(TEMPERATURE, 0.3)),
            )

            raw = response.choices[0].message.content or ""
            raw = _strip_code_fences(raw)

            test_cases, truncated = _extract_json(raw)
            
            # If truncated, discard the last item as it's likely missing fields (steps, etc)
            if truncated and len(test_cases) > 1:
                logger.warning("Discarding the last truncated/incomplete test case.")
                test_cases.pop()

            validated = [_validate_test_case(tc) for tc in test_cases]
            logger.info("Received and validated %d test case(s).", len(validated))
            return validated

        except openai.RateLimitError as exc:
            logger.warning("Rate limit on attempt %d: %s", attempt, exc)
            last_error = exc
            # Exponential backoff + extra wait for TPM reset
            wait = max(LLM_RETRY_DELAY * (2 ** attempt), 30)
            logger.info("Waiting %.0fs before retry...", wait)
            time.sleep(wait)
        except openai.APIError as exc:
            logger.warning("API error on attempt %d: %s", attempt, exc)
            last_error = exc
            time.sleep(LLM_RETRY_DELAY * attempt)

    raise RuntimeError(
        f"LLM call failed after {LLM_RETRIES} attempts. Last error: {last_error}"
    )


# ===========================================================================
# Public API - handles any input size automatically
# ===========================================================================

SYSTEM_MSG_JIRA = (
    "You are a senior QA engineer. "
    "Always respond with a valid JSON array only. "
    "No markdown, no explanation, no code fences."
)

SYSTEM_MSG_CONFLUENCE = (
    "You are a senior QA engineer specializing in test case generation "
    "from technical specifications and documentation. "
    "Always respond with a valid JSON array only. "
    "No markdown, no explanation, no code fences."
)


def generate_test_cases(scraped_text: str) -> list[dict[str, Any]]:
    """
    Generate test cases from Jira requirement text.
    Automatically chunks large inputs to fit within free-tier token limits.
    """
    return _generate_with_chunking(
        scraped_text=scraped_text,
        template=PROMPT_TEMPLATE,
        system_msg=SYSTEM_MSG_JIRA,
        source_label="Jira",
    )


def generate_confluence_test_cases(scraped_text: str) -> list[dict[str, Any]]:
    """
    Generate test cases from Confluence page content.
    Automatically chunks large inputs to fit within free-tier token limits.
    """
    return _generate_with_chunking(
        scraped_text=scraped_text,
        template=CONFLUENCE_PROMPT_TEMPLATE,
        system_msg=SYSTEM_MSG_CONFLUENCE,
        source_label="Confluence",
    )


def _generate_with_chunking(
    scraped_text: str,
    template: str,
    system_msg: str,
    source_label: str,
) -> list[dict[str, Any]]:
    """
    Core chunking engine.
    1. Calculate how many characters of input fit per request.
    2. Split the scraped text into chunks.
    3. Process each chunk with a TPM-reset delay between them.
    4. Merge all results.
    """
    # Calculate the max chars of scraped_text that fit in one request
    template_without_placeholder = template.replace("{scraped_text}", "")
    template_overhead_tokens = _estimate_tokens(template_without_placeholder)
    system_tokens = _estimate_tokens(system_msg)
    overhead_tokens = template_overhead_tokens + system_tokens

    usable_tpm = int(GROQ_TPM_LIMIT * SAFETY_MARGIN)
    available_for_input = usable_tpm - overhead_tokens - MAX_OUTPUT_TOKENS
    max_input_chars = max(500, int(available_for_input * CHARS_PER_TOKEN))

    logger.info(
        "[%s] Input text: %d chars (~%d tokens). Max per chunk: %d chars. Overhead: ~%d tokens.",
        source_label, len(scraped_text), _estimate_tokens(scraped_text),
        max_input_chars, overhead_tokens,
    )

    chunks = _chunk_text(scraped_text, max_input_chars)
    logger.info("[%s] Split into %d chunk(s).", source_label, len(chunks))

    all_test_cases: list[dict[str, Any]] = []

    for i, chunk in enumerate(chunks, 1):
        logger.info(
            "[%s] Processing chunk %d/%d (%d chars, ~%d tokens)...",
            source_label, i, len(chunks), len(chunk), _estimate_tokens(chunk),
        )

        prompt = template.format(scraped_text=chunk)
        cases = _call_llm_for_test_cases(prompt, system_msg)
        all_test_cases.extend(cases)

        logger.info(
            "[%s] Chunk %d/%d produced %d test case(s). Running total: %d.",
            source_label, i, len(chunks), len(cases), len(all_test_cases),
        )

        # Wait for TPM window reset before next chunk (skip after last chunk)
        if i < len(chunks):
            logger.info(
                "[%s] Waiting %.0fs for TPM window reset before next chunk...",
                source_label, CHUNK_DELAY_SECONDS,
            )
            time.sleep(CHUNK_DELAY_SECONDS)

    if not all_test_cases:
        raise RuntimeError(
            f"No test cases generated from {len(chunks)} chunk(s). "
            "The LLM returned empty results for all chunks."
        )

    logger.info(
        "[%s] Total: %d test case(s) from %d chunk(s).",
        source_label, len(all_test_cases), len(chunks),
    )
    return all_test_cases
