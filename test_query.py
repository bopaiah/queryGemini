# -*- coding: utf-8 -*-
"""
Test Script: gemini_utils.query_gemini
Author: Bopaiah Mekerira

Description:
    Integration test for query_gemini() from gemini_utils.
    Loads the 'prompt2' template via getPrompt(), resolves it with today's date
    and a seasonal label, then sends it to the Gemini model using the GEO prefix.

Usage:
    python test_query.py
"""

# --- Standard library imports ---
import datetime
import json
import os
import sys

# --- Third-party imports ---
from dotenv import load_dotenv

# --- Local imports ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from prompt_utils import getPrompt
from gemini_utils import query_gemini


def main():
    """
    Resolves the 'prompt2' template and sends it to Gemini via query_gemini.

    Prints the full JSON response including response_data, token_usage, and metadata.
    """
    load_dotenv()

    json_args = {
        "CURRENT_DATE": datetime.date.today().isoformat(),
        "SEASON": "Spring Cherry Blossom Peak"
    }

    print("--- Testing query_gemini with getPrompt('prompt2') ---")
    try:
        prompt = getPrompt("prompt2", json_args)
        result = query_gemini("GEO", prompt)
        print("Query Result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Query failed: {e}")


if __name__ == "__main__":
    main()
