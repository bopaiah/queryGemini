# -*- coding: utf-8 -*-
"""
Query Gemini/Gemma Models via CLI
Author: Bopaiah Mekerira
Description: A utility script to query the Gemini or Gemma model via Google GenAI SDK.
             Supports multiline variable injection into prompts.
"""

import os
import sys
import argparse
from dotenv import load_dotenv

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: The 'google-genai' library is required.")
    print("Install it with: pip install google-genai")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Query the Gemma (or Gemini) model via CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python query_gemini.py -f prompt.txt
  python query_gemini.py -f prompt.txt --vars input_env.txt --env .env --model gemini-2.5-flash
"""
    )
    parser.add_argument("prompt", type=str, nargs='?', default=None, help="The prompt to send to the model (optional if -f is used)")
    parser.add_argument(
        "-f", "--file",
        type=str,
        help="Path to a file containing the PROMPT. If provided, its content is used as the prompt."
    )
    parser.add_argument(
        "--vars",
        type=str,
        help="Path to a file containing variable definitions (key=value). If omitted, a default file derived from the prompt file name will be used. Default ./input_env.txt"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        help="Model name to use. If omitted, the script reads MODEL from the .env file. Default model name from ENV file"
    )
    parser.add_argument(
        "--env",
        type=str,
        default=os.path.join(os.path.dirname(__file__), ".env"),
        help="Path to the .env file. Default ./.env"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available Gemini models. Ignores other arguments"
    )

    args = parser.parse_args()
    
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

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
            # Fetch up to 100 models (models.list is a generator or iterator in some SDKs, list() returns iterable page)
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
    
    # Determine prompt text
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                prompt_text = f.read()
        except Exception as e:
            print(f"Error reading prompt file '{args.file}': {e}")
            sys.exit(1)
    else:
        if args.prompt is None:
            print("Error: No prompt provided. Provide a prompt argument or use -f <filename>.")
            sys.exit(1)
        prompt_text = args.prompt
    
    # Load variables if provided or infer default based on prompt file
    vars_dict = {}
    vars_path = args.vars
    if not vars_path and args.file:
        # Derive default vars filename from prompt filename (e.g., prompt_env.txt -> input_env.txt)
        prompt_basename = os.path.basename(args.file)
        if prompt_basename.lower().startswith("prompt_"):
            default_name = "input_" + prompt_basename[len("prompt_"):]
        else:
            name, ext = os.path.splitext(prompt_basename)
            default_name = name + "_vars" + ext
        vars_path = os.path.join(os.path.dirname(args.file), default_name)
    if vars_path:
        explicit_vars = bool(args.vars)  # True if user passed --vars explicitly
        if not os.path.exists(vars_path):
            if explicit_vars:
                print(f"Error: vars file '{vars_path}' not found.")
                sys.exit(1)
            else:
                vars_path = None  # default not found — skip substitution silently
        if vars_path:
            try:
                with open(vars_path, "r", encoding="utf-8") as vf:
                    content = vf.read()
                
                i = 0
                n = len(content)
                while i < n:
                    # Skip leading whitespace/newlines
                    while i < n and content[i].isspace():
                        i += 1
                    if i >= n:
                        break
                        
                    # Check if comment
                    if content[i] == '#':
                        while i < n and content[i] != '\n':
                            i += 1
                        continue
                        
                    # Parse Key: must match [A-Za-z_][A-Za-z0-9_]*
                    key_start = i
                    while i < n and (content[i].isalnum() or content[i] == '_'):
                        i += 1
                    key = content[key_start:i]
                    
                    if not key:
                        # If not a valid key, skip to next line
                        while i < n and content[i] != '\n':
                            i += 1
                        continue
                        
                    # Skip spaces before '='
                    while i < n and content[i].isspace() and content[i] != '\n':
                        i += 1
                        
                    if i >= n or content[i] != '=':
                        # Not a valid assignment, skip to next line
                        while i < n and content[i] != '\n':
                            i += 1
                        continue
                        
                    # Skip '='
                    i += 1
                    
                    # Skip spaces after '='
                    while i < n and content[i].isspace() and content[i] != '\n':
                        i += 1
                        
                    if i >= n:
                        vars_dict[key] = ""
                        break
                        
                    # Check if value is quoted
                    quote_char = None
                    if content[i] in ('"', "'"):
                        quote_char = content[i]
                        i += 1
                        
                    val_chars = []
                    if quote_char:
                        # Quoted string parser: handles escape characters and multi-line content
                        while i < n:
                            c = content[i]
                            if c == '\\':
                                if i + 1 < n:
                                    next_c = content[i + 1]
                                    if next_c == quote_char:
                                        val_chars.append(quote_char)
                                        i += 2
                                        continue
                                    elif next_c == '\\':
                                        val_chars.append('\\')
                                        i += 2
                                        continue
                                    elif next_c == 'n':
                                        val_chars.append('\n')
                                        i += 2
                                        continue
                                    elif next_c == 't':
                                        val_chars.append('\t')
                                        i += 2
                                        continue
                                    elif next_c == 'r':
                                        val_chars.append('\r')
                                        i += 2
                                        continue
                                    else:
                                        # Keep escape and the character if not a standard escape sequence
                                        val_chars.append('\\')
                                        val_chars.append(next_c)
                                        i += 2
                                        continue
                            elif c == quote_char:
                                i += 1 # Skip closing quote
                                break
                            else:
                                val_chars.append(c)
                                i += 1
                        value = "".join(val_chars)
                    else:
                        # Unquoted string parser: read until end of line or '#'
                        while i < n and content[i] != '\n':
                            c = content[i]
                            # Handle trailing comment if it starts with space then '#'
                            if c == '#' and (i == 0 or content[i-1].isspace()):
                                break
                            val_chars.append(c)
                            i += 1
                        value = "".join(val_chars).strip()
                        
                    vars_dict[key] = value
            except Exception as e:
                print(f"Error reading vars file '{vars_path}': {e}")
                sys.exit(1)
    
    # Substitute variables into prompt_text if any
    if vars_dict:
        for k, v in vars_dict.items():
            placeholder = f"${k}"
            prompt_text = prompt_text.replace(placeholder, v)

    load_dotenv(dotenv_path=args.env)
    
    # Determine model: command-line overrides .env
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
        # Using v1beta for early-access models like gemma-3
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
        # Token usage statistics (google-genai SDK exposes this as usage_metadata)
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
