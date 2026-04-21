"""
summary_prompt.py
LLM prompts and generator functions for producing:
  1. A structured summary of a requirement page
  2. A list of testing dependencies / prerequisites

Token-optimised for Groq free tier (6 000 TPM).
Adds truncation and a mandatory delay between the two sequential LLM calls
so we never exceed the TPM window.
"""

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
    GROQ_TPM_LIMIT,
    CHARS_PER_TOKEN,
    SAFETY_MARGIN,
    MAX_OUTPUT_TOKENS,
    CHUNK_DELAY_SECONDS,
)

logger = logging.getLogger(__name__)

_client = openai.OpenAI(api_key=ACTIVE_API_KEY, base_url=ACTIVE_BASE_URL)


# ===========================================================================
# Token helpers
# ===========================================================================

def _estimate_tokens(text: str) -> int:
    """Rough token count - approx 1 token per 4 chars."""
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def _truncate_for_budget(text: str, prompt_template: str, system_msg: str) -> str:
    """
    Truncate text so the full request (system + prompt + output) fits
    within the Groq TPM budget.
    """
    template_without_placeholder = prompt_template.replace("{scraped_text}", "")
    overhead_tokens = (
        _estimate_tokens(template_without_placeholder)
        + _estimate_tokens(system_msg)
    )
    usable_tpm = int(GROQ_TPM_LIMIT * SAFETY_MARGIN)
    available_for_input = usable_tpm - overhead_tokens - MAX_OUTPUT_TOKENS
    max_chars = max(500, int(available_for_input * CHARS_PER_TOKEN))

    if len(text) <= max_chars:
        return text

    logger.warning(
        "Text too long (%d chars, ~%d tokens); truncating to %d chars for TPM budget.",
        len(text), _estimate_tokens(text), max_chars,
    )
    return text[:max_chars] + "\n\n... [Content truncated for token budget] ..."


# ===========================================================================
# Prompt templates - kept compact to minimise token usage
# ===========================================================================

SUMMARY_PROMPT = (
    "You are a senior QA analyst. Analyse the following requirement/specification "
    "content and produce a structured summary.\n\n"
    "Content:\n{scraped_text}\n\n"
    "Return a JSON object (NOT an array) with these exact keys:\n\n"
    "{{\n"
    '  "overview": "A concise 3-5 sentence summary of what this requirement is about.",\n'
    '  "key_features": [\n'
    '    "Feature 1 - brief description",\n'
    '    "Feature 2 - brief description"\n'
    "  ],\n"
    '  "scope": "What is in scope - devices, platforms, user types, regions. '
    'Also mention what is out of scope if stated.",\n'
    '  "acceptance_criteria_count": 0,\n'
    '  "complexity": "Low/Medium/High - based on conditions, integrations, edge cases"\n'
    "}}\n\n"
    "Rules:\n"
    '- "key_features" must list EVERY distinct feature or behaviour described.\n'
    '- "overview" should be understandable by someone who hasn\'t read the original.\n'
    "- Output ONLY valid JSON. No markdown, no explanation, no code fences."
)


DEPENDENCIES_PROMPT = (
    "You are a senior QA engineer analysing a requirement to identify everything "
    "the QA team needs BEFORE they can start testing.\n\n"
    "Content:\n{scraped_text}\n\n"
    "Identify ALL testing dependencies and prerequisites.\n\n"
    "Return a JSON array of dependency objects:\n\n"
    "[\n"
    "  {{\n"
    '    "category": "One of: Content, Device/Hardware, Backend/API, Configuration, '
    'Account/User, Integration, Data, Environment, Feature Flag, Other",\n'
    '    "item": "Short name of the dependency",\n'
    '    "description": "Detailed description of what is needed and why",\n'
    '    "owner": "One of: Engineering, DevOps, Content Team, QA, Product, Third Party",\n'
    '    "priority": "One of: Blocker, High, Medium, Low"\n'
    "  }}\n"
    "]\n\n"
    "Rules:\n"
    "- Be EXHAUSTIVE. Check every paragraph, table row, bullet point.\n"
    "- Look for: Content types, Device types, Backend services, User accounts, "
    "Feature flags, Test environment, Third-party integrations, Test data, Config changes.\n"
    "- Output ONLY a valid JSON array. No markdown, no explanation, no code fences."
)


# ===========================================================================
# JSON parsing helpers
# ===========================================================================

def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences from LLM output."""
    cleaned = re.sub(r'^\s*```(?:json)?\s*\n?', '', raw, count=1)
    cleaned = re.sub(r'\n?\s*```\s*$', '', cleaned)
    return cleaned.strip()


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a JSON object from LLM output with fallbacks."""
    stripped = _strip_code_fences(raw)

    # Try direct parse
    for text in [raw, stripped]:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Regex fallback - find outermost {...}
    match = re.search(r'\{.*\}', stripped, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                logger.warning("Used regex fallback to extract JSON object.")
                return parsed
        except json.JSONDecodeError:
            pass

    logger.error("Could not parse summary JSON. Raw (first 500 chars): %s", raw[:500])
    return {
        "overview": "Failed to parse summary. Check logs for raw LLM output.",
        "key_features": [],
        "scope": "Unknown",
        "acceptance_criteria_count": 0,
        "complexity": "Unknown",
    }


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    """Parse a JSON array from LLM output with fallbacks."""
    stripped = _strip_code_fences(raw)

    for text in [raw, stripped]:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    match = re.search(r'\[.*\]', stripped, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                logger.warning("Used regex fallback to extract JSON array.")
                return parsed
        except json.JSONDecodeError:
            pass

    logger.error("Could not parse dependencies JSON. Raw (first 500 chars): %s", raw[:500])
    return []


# ===========================================================================
# Core LLM call with adaptive token management
# ===========================================================================

def _call_llm(prompt: str, system_msg: str) -> str:
    """Call the LLM with retries and adaptive token budgeting. Returns raw text."""
    if not ACTIVE_API_KEY:
        provider_hint = "GROQ_API_KEY" if LLM_PROVIDER == "groq" else "OPENAI_API_KEY"
        raise EnvironmentError(f"{provider_hint} is not set in your .env file.")

    # Adaptive max_tokens based on input size
    input_tokens = _estimate_tokens(prompt) + _estimate_tokens(system_msg)
    usable_tpm = int(GROQ_TPM_LIMIT * SAFETY_MARGIN)
    safe_output = max(500, usable_tpm - input_tokens)
    safe_output = min(safe_output, MAX_OUTPUT_TOKENS)

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
            return response.choices[0].message.content or ""

        except openai.RateLimitError as exc:
            logger.warning("Rate limit on attempt %d: %s", attempt, exc)
            last_error = exc
            wait = max(LLM_RETRY_DELAY * (2 ** attempt), 30)
            logger.info("Waiting %.0fs before retry...", wait)
            time.sleep(wait)
        except openai.APIError as exc:
            logger.warning("API error on attempt %d: %s", attempt, exc)
            last_error = exc
            time.sleep(LLM_RETRY_DELAY * attempt)

    raise RuntimeError(f"LLM call failed after {LLM_RETRIES} attempts. Last error: {last_error}")


# ===========================================================================
# Public API
# ===========================================================================

def generate_summary(scraped_text: str) -> dict[str, Any]:
    """Generate a structured summary of the scraped requirement text."""
    system_msg = (
        "You are a senior QA analyst. "
        "Respond with valid JSON only. No markdown, no explanation."
    )
    # Truncate to fit within budget
    scraped_text = _truncate_for_budget(scraped_text, SUMMARY_PROMPT, system_msg)
    prompt = SUMMARY_PROMPT.format(scraped_text=scraped_text)
    raw = _call_llm(prompt, system_msg)
    raw = _strip_code_fences(raw)
    result = _parse_json_object(raw)
    logger.info("Summary generated: %d key features identified.", len(result.get("key_features", [])))
    return result


def generate_dependencies(scraped_text: str) -> list[dict[str, Any]]:
    """Generate a list of testing dependencies from the scraped requirement text."""
    system_msg = (
        "You are a senior QA engineer. "
        "Respond with a valid JSON array only. No markdown, no explanation."
    )
    # Truncate to fit within budget
    scraped_text = _truncate_for_budget(scraped_text, DEPENDENCIES_PROMPT, system_msg)
    prompt = DEPENDENCIES_PROMPT.format(scraped_text=scraped_text)
    raw = _call_llm(prompt, system_msg)
    raw = _strip_code_fences(raw)
    deps = _parse_json_array(raw)
    logger.info("Dependencies identified: %d item(s).", len(deps))
    return deps
