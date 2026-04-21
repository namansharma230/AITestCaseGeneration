"""Quick end-to-end test of the optimised LLM pipeline."""
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from prompt_template import generate_test_cases

sample_text = (
    "User should be able to login with valid email and password. "
    "If wrong password is entered 3 times, account should be locked for 30 minutes."
)

print("\n=== Testing generate_test_cases with short input ===")
result = generate_test_cases(sample_text)
print(f"\nGenerated {len(result)} test case(s):")
for tc in result:
    print(f"  - {tc.get('title', 'NO TITLE')}")
print("\n=== TEST PASSED ===")
