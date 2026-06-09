# -*- coding: utf-8 -*-
"""
Query Gemini Models via CLI
Author: Bopaiah Mekerira

Description:
    A CLI utility to query Gemini models using named prompt templates or raw prompts.
    Delegates all API interaction to gemini_utils.query_gemini() and prompt loading
    to prompt_utils.getPrompt().

    The --model flag accepts either:
      - A model prefix (e.g. GEO, IMAGE) — uses {PREFIX}_MODEL, {PREFIX}_API_KEY,
        and {PREFIX}_CONFIG from .env
      - A full Gemini model name (e.g. gemini-2.5-flash) — overrides GEO_MODEL in .env
        while keeping GEO_API_KEY and GEO_CONFIG

Usage:
    python query_gemini.py [prompt] [-p PROMPT_NAME] [-a JSON_ARGS] [--model MODEL_OR_PREFIX] [--env PATH] [--list]
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from prompt_utils import getPrompt
from gemini_utils import query_gemini, list_gemini_models
from env_utils import get_env


def _is_model_prefix(value):
    """
    Returns True if value looks like an env prefix (all uppercase letters/underscores,
    no hyphens or dots), e.g. 'GEO', 'IMAGE', 'MY_MODEL'.
    Returns False if it looks like a model name, e.g. 'gemini-2.5-flash'.
    """
    return value.replace("_", "").isupper() and "-" not in value and "." not in value


def main():
    parser = argparse.ArgumentParser(
        description="Query Gemini models via CLI using templates or raw prompts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The --model flag accepts a model prefix or a full model name:
  --model GEO          Use GEO_MODEL, GEO_API_KEY, GEO_CONFIG from .env
  --model IMAGE        Use IMAGE_MODEL, IMAGE_API_KEY, IMAGE_CONFIG from .env
  --model gemini-2.5-flash  Override GEO_MODEL with this model name

Examples:
  python query_gemini.py "Explain the effect of el-nino on weather"
  python query_gemini.py -p prompt2
  python query_gemini.py -p prompt2 --model GEO
  python query_gemini.py -p prompt2 --model IMAGE
  python query_gemini.py -p prompt2 -a '{"CURRENT_DATE": "2026-06-02", "SEASON": "Summer"}' --model GEO
  python query_gemini.py -p prompt2 --model gemini-2.5-flash
  python query_gemini.py --list
"""
    )
    parser.add_argument(
        "prompt",
        type=str,
        nargs='?',
        default=None,
        help="Raw prompt string to send directly to the model (optional if -p is used)"
    )
    parser.add_argument(
        "-p", "--prompt-name", "--prompt_name",
        dest="prompt_name",
        type=str,
        help="Name of a prompt template in prompt.idx"
    )
    parser.add_argument(
        "-a", "--args", "--prompt-args", "--prompt_args",
        dest="prompt_args",
        type=str,
        help="JSON string of variables to substitute into the prompt template"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="GEO",
        help=(
            "Model prefix (e.g. GEO, IMAGE) to select the {PREFIX}_MODEL / _API_KEY / _CONFIG "
            "group from .env, OR a full model name (e.g. gemini-2.5-flash) to override GEO_MODEL. "
            "Defaults to GEO."
        )
    )
    parser.add_argument(
        "--env",
        type=str,
        default=os.path.join(os.path.dirname(__file__), ".env"),
        help="Path to the .env file (default: ./.env)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available Gemini models and exit"
    )

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    load_dotenv(dotenv_path=args.env)

    # --- List models ---
    if args.list:
        api_key = get_env("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY is not set in environment or .env file.")
            sys.exit(1)
        print("Listing available models...")
        try:
            models = list_gemini_models(api_key)
            print("-" * 70)
            print(f"{'Model Name':<50} | {'Display Name'}")
            print("-" * 70)
            for m in models:
                display_name = getattr(m, 'display_name', 'N/A')
                print(f"{m.name:<50} | {display_name}")
            print("-" * 70)
        except Exception as e:
            print(f"Error listing models: {e}")
            sys.exit(1)
        sys.exit(0)

    # --- Resolve prompt text ---
    if args.prompt_name:
        try:
            prompt_text = getPrompt(args.prompt_name, args.prompt_args)
        except Exception as e:
            print(f"Error loading prompt '{args.prompt_name}': {e}")
            sys.exit(1)
    elif args.prompt:
        prompt_text = args.prompt
    else:
        print("Error: No prompt provided. Supply a prompt argument or use -p <prompt_name>.")
        sys.exit(1)

    # --- Determine model prefix and apply --model override ---
    # If --model looks like a prefix (e.g. GEO, IMAGE), use it directly as the prefix.
    # If it looks like a model name (e.g. gemini-2.5-flash), override GEO_MODEL with it.
    model_value = args.model
    if _is_model_prefix(model_value):
        model_prefix = model_value
    else:
        # Treat as a full model name — override GEO_MODEL
        model_prefix = "GEO"
        os.environ["GEO_MODEL"] = model_value

    # --- Query Gemini via gemini_utils ---
    print(f"Prompt:\n{prompt_text}")
    print("-" * 50)
    print(f"Using model prefix: {model_prefix}")
    print("Generating response...\n")

    try:
        # === Actual Gemini API call ===
        result = query_gemini(model_prefix, prompt_text)

        response_data = result.get("response_data", {})
        token_usage = result.get("token_usage", {})
        metadata = result.get("metadata", {})

        print("\n--- Response ---")
        data = response_data.get("data", "")
        if isinstance(data, dict) or isinstance(data, list):
            import json
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(data if data else "Received empty response.")

        print("\n--- Token Usage ---")
        print(f"Prompt tokens:     {token_usage.get('prompt_token_count', 'N/A')}")
        print(f"Completion tokens: {token_usage.get('candidates_token_count', 'N/A')}")
        print(f"Total tokens:      {token_usage.get('total_token_count', 'N/A')}")
        print(f"Model:             {token_usage.get('model', 'N/A')}")
        print(f"Finish reason:     {metadata.get('finish_reason', 'N/A')}")

    except Exception as e:
        print(f"\nError occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
