# -*- coding: utf-8 -*-
"""
Verification Script for prompt_utils (Realworld Prompt2 Test)
"""

import os
import sys
from prompt_utils import getPrompt

def run_test():
    print("--- Running getPrompt Test on prompt2 (Tokyo Weather Template) ---", file=sys.stderr)
    
    import datetime
    # Define JSON arguments to dynamically override Tokyo defaults with Kyoto specifics
    json_arg = {
        "CURRENT_DATE": datetime.date.today().isoformat(),
        "SEASON": "Spring Cherry Blossom Peak"
    }
    
    # Run the getPrompt function for "prompt2"
    try:
        updated_prompt = getPrompt("prompt2", json_arg)
        try:
            print(updated_prompt)
        except UnicodeEncodeError:
            sys.stdout.flush()
            sys.stdout.buffer.write(updated_prompt.encode('utf-8'))
            sys.stdout.flush()
    except Exception as e:
        print("Error during test:", e, file=sys.stderr)

if __name__ == "__main__":
    run_test()
