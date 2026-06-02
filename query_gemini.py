# -*- coding: utf-8 -*-
"""
Query Gemini/Gemma Models via CLI
Author: Bopaiah Mekerira

Description:
    A command-line interface (CLI) script to query Google's Gemini (or Gemma) models
    using the official google-genai SDK. Supports both raw prompt strings and named
    prompt templates loaded from prompt.idx via prompt_utils.

    Configuration is read from a .env file (default: ./.env). The model and API key
    can be overridden via CLI arguments.

Usage:
    python query_gemini.py [prompt] [-p PROMPT_NAME] [-a JSON_ARGS] [--model MODEL]
                           [--env ENV_PATH] [--list]

Arguments:
    prompt              Raw prompt string to send directly to the model.
    -p, --prompt-name   Name of a prompt template registered in prompt.idx.
    -a, --args          JSON string of key-value pairs to substitute into the template.
    --model             Gemini model name. Overrides MODEL in .env.
    --env               Path to the .env file. Defaults to ./.env.
    --list              List all available Gemini models and exit.

Examples:
    python query_gemini.py "Explain gravity"
    python query_gemini.py -p prompt2 -a '{"CURRENT_DATE": "2026-06-02", "SEASON": "Summer"}'
    python query_gemini.py -p prompt2 --env .env --model gemini-2.5-flash
    python query_gemini.py --list

Dependencies:
    - google-genai       (pip install google-genai)
    - python-dotenv      (pip install python-dotenv)
    - prompt_utils       (local module)
"""

# --- Standard library imports ---
import os
import sys
import argparse

# --- Third-party imports ---
from dotenv import load_dotenv

try:
    from google import genai
except ImportError:
    print("Error: The 'google-genai' library is required.")
    print("Install it with: pip install google-genai")
    sys.exit(1)

# --- Local imports ---
from prompt_utils import getPrompt


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """
    Parses CLI arguments and executes a Gemini model query.

    Supports:
      - Raw prompt strings passed directly as a positional argument.
      - Named prompt templates loaded from prompt.idx via -p/--prompt-name.
      - Runtime variable overrides via -a/--args (JSON string).
      - Model and .env path overrides via --model and --env.
      - Listing all available Gemini models via --list.
    """
    parser = argparse.ArgumentParser(
        description="Query a Gemini (or Gemma) model via CLI using templates or raw prompts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python query_gemini.py "Explain gravity"
  python query_gemini.py -p prompt2 -a '{"CURRENT_DATE": "2026-06-02", "SEASON": "Summer"}'
  python query_gemini.py -p prompt2 --env .env --model gemini-2.5-flash
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
        "-p", "--prompt", "--prompt-name", "--prompt_name",
        dest="prompt_name",
        type=str,
        help="Name of the prompt template to load from prompt.idx"
    )
    parser.add_argument(
        "-a", "--args", "--prompt-args", "--prompt_args",
        dest="prompt_args",
        type=str,
        help="JSON string of key-value arguments to substitute into the prompt template"
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Gemini model name to use. Overrides MODEL in .env if provided."
    )
    parser.add_argument(
        "--env",
        type=str,
        default=os.path.join(os.path.dirname(__file__), ".env"),
        help="Path to the .env configuration file. Defaults to ./.env"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available Gemini models and exit. Ignores other arguments."
    )

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    # --- Handle --list ---
    if args.list:
        load_dotenv(dotenv_path=args.env)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable is not set.")
            print("Please set it in your environment or a .env file.")
            sys.exit(1)
        print("Listing available models...")
        try:
            client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
            models = client.models.list()
            print("-" * 70)
            print(f"{'Model Name':<50} | {'Display Name'}")
            print("-" * 70)
            for m in models:
                display_name = getattr(m, 'display_name', 'N/A')
                print(f"{m.name:<50} | {display_name}")
            print("-" * 70)
            sys.exit(0)
        except Exception as e:
            print(f"Error listing models: {e}")
            sys.exit(1)

    # --- Resolve prompt text ---
    if args.prompt_name:
        # Load and resolve a named prompt template from prompt.idx
        try:
            prompt_text = getPrompt(args.prompt_name, args.prompt_args)
        except Exception as e:
            print(f"Error loading prompt '{args.prompt_name}': {e}")
            sys.exit(1)
    else:
        if args.prompt is None:
            print("Error: No prompt provided. Provide a prompt argument or use -p <prompt_name>.")
            sys.exit(1)
        prompt_text = args.prompt

    load_dotenv(dotenv_path=args.env)

    # --- Resolve model (CLI arg overrides .env) ---
    if not args.model:
        args.model = os.getenv("MODEL")
    if not args.model:
        print("Error: Model not specified. Provide --model or set MODEL in .env.")
        sys.exit(1)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        print("Please set it in your environment or a .env file.")
        sys.exit(1)

    print(f"Initializing client...")
    print(f"Model: {args.model}")
    print("-" * 50)
    print(f"Prompt:\n{prompt_text}")
    print("-" * 50)
    print("Generating response (this may take a moment)...\n")

    try:
        # Using v1beta for early-access models (e.g. gemma-3, gemini-2.5-*)
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        response = client.models.generate_content(
            model=args.model,
            contents=prompt_text
        )

        print("\n--- Response ---")
        if response.text:
            print(response.text)
        else:
            print("Received empty text response.")
            print(f"Raw response: {response}")

        # Token usage statistics
        usage = getattr(response, "usage_metadata", None)
        print("\n--- Token Usage ---")
        if usage is not None:
            print(f"Prompt tokens:     {getattr(usage, 'prompt_token_count', 'N/A')}")
            print(f"Completion tokens: {getattr(usage, 'candidates_token_count', 'N/A')}")
            print(f"Total tokens:      {getattr(usage, 'total_token_count', 'N/A')}")
        else:
            print("No usage information available in the response.")

    except Exception as e:
        print(f"\nError occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
