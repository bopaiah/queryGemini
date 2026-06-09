import os
import json
from dotenv import load_dotenv
from gemini_utils import query_gemini

def test_query():
    load_dotenv()
    print("\n--- Testing query_gemini ---")
    try:
        result = query_gemini("GEO", "Say hello in JSON format: {\"greeting\": \"hello\"}")
        print("Query Result:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Query failed: {e}")

if __name__ == "__main__":
    test_query()
