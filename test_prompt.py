# -*- coding: utf-8 -*-
"""
Test Script: prompt_utils.getPrompt
Author: Bopaiah Mekerira

Description:
    Verifies that getPrompt correctly loads and resolves the 'prompt2' template
    from prompt.idx, substituting dynamic variables at runtime.

Usage:
    python test_prompt.py
"""

# --- Standard library imports ---
import datetime
import sys

# --- Local imports ---
from prompt_utils import getPrompt


def run_test():
    """
    Loads the 'prompt2' prompt template and prints the resolved output.

    Overrides template variables with today's date and a seasonal label.
    Output is written to stdout; errors are written to stderr.
    """
    print("--- Running getPrompt Test on prompt2 (Tokyo Weather Template) ---", file=sys.stderr)

    json_args = {
        "CURRENT_DATE": datetime.date.today().isoformat(),
        "SEASON": "Spring Cherry Blossom Peak"
    }

    try:
        resolved_prompt = getPrompt("prompt2", json_args)
        try:
            print(resolved_prompt)
        except UnicodeEncodeError:
            sys.stdout.flush()
            sys.stdout.buffer.write(resolved_prompt.encode("utf-8"))
            sys.stdout.flush()
    except Exception as e:
        print(f"Error during test: {e}", file=sys.stderr)


if __name__ == "__main__":
    run_test()
