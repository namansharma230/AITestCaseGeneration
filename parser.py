"""
parser.py
Transforms validated test-case dicts (from the LLM) into flat row lists
ready to be written to the Excel sheet.
Each row receives a unique short UUID as its Test Case ID.
"""

import logging
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def _short_uuid() -> str:
    """Generate a unique Test Case ID. Example: TC-3A7F2D1B"""
    return "TC-" + uuid.uuid4().hex[:8].upper()


def _format_steps(steps: Any) -> str:
    """Normalise steps to a clean numbered multi-line string."""
    if isinstance(steps, list):
        formatted = []
        for i, step in enumerate(steps, start=1):
            step_text = re.sub(r'^\d+[\.\)]\s*', '', str(step).strip())
            formatted.append(f"{i}. {step_text}")
        return "\n".join(formatted)
    return str(steps).strip()


def parse_to_rows(test_cases: list[dict[str, Any]]) -> list[list[str]]:
    """
    Convert a list of test-case dicts into row arrays for Excel.

    Column order: [ID, Title, Preconditions, Steps, Expected Result, Test Data, Priority]
    """
    rows: list[list[str]] = []

    for i, tc in enumerate(test_cases, start=1):
        try:
            row = [
                _short_uuid(),                                          # A – Test Case ID
                str(tc.get("title", "")).strip(),                       # B – Title
                str(tc.get("preconditions", "")).strip(),               # C – Preconditions
                _format_steps(tc.get("steps", [])),                     # D – Steps
                str(tc.get("expected_result", "")).strip(),             # E – Expected Result
                str(tc.get("test_data", tc.get("postconditions", ""))).strip(),  # F – Test Data
                str(tc.get("priority", "Medium")).strip(),              # G – Priority
            ]
            rows.append(row)
            logger.debug("Parsed row %d: ID=%s | Title=%s", i, row[0], row[1])
        except Exception as exc:
            logger.error("Failed to parse test case %d: %s — skipping.", i, exc)

    logger.info("Parsed %d row(s) ready for Excel.", len(rows))
    return rows  # Fixed: was 'rowss' (typo causing NameError)