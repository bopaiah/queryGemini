# -*- coding: utf-8 -*-
"""
Prompt Loader Utility
Author: Bopaiah Mekerira
Description: A utility library to load prompt content, resolve file inclusions,
             parse environment files, and substitute placeholders with dynamic JSON/dictionary variables.
             It reads the prompt.idx file in the same folder to locate prompt and environment files.
             
             Use Cases:
             - It reads the prompt from the prompt file mentioned in the idx and its related env file
               for updating the variables mentioned in the prompt file like {{my_variable}}.
             - The env file arguments can be overridden by passing them in getPrompt arguments json_input.
             - If a part of a prompt file needs to be loaded from another prompt file, it can be
               mentioned in the prompt file with {{file:filepath}}.
"""

import os
import re
import json

def parse_idx_line(line):
    """
    Parses a single line from prompt.idx.
    Supports comma-separated columns as well as custom dot-space separators.
    """
    line = line.strip()
    if not line:
        return None
    # Split by comma first
    parts = [p.strip() for p in line.split(',')]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        # Check if the second and third columns are separated by dot and space (e.g. ". ")
        name = parts[0]
        rest = parts[1]
        # Split on ". " but be careful about paths starting with "./"
        sub_parts = re.split(r'\.\s+(?=\.?/)', rest)
        if len(sub_parts) == 2:
            return name, sub_parts[0].strip(), sub_parts[1].strip()
        else:
            sub_parts = rest.split(". ")
            if len(sub_parts) >= 2:
                return name, sub_parts[0].strip(), sub_parts[1].strip()
    return None

def parse_env_file(filepath):
    """
    Parses key-value data from an env file.
    Only triple backticks (```) are identified for multi-line inputs.
    All other values are treated as single-line literally after '='.
    """
    if not os.path.exists(filepath):
        return {}
    
    vars_dict = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Warning: Could not read env file at '{filepath}': {e}")
        return {}

    content_len = len(content)
    i = 0
    while i < content_len:
        # Skip leading whitespace/newlines
        while i < content_len and content[i].isspace():
            i += 1
        if i >= content_len:
            break
            
        # Check if comment
        if content[i] == '#':
            while i < content_len and content[i] != '\n':
                i += 1
            continue
            
        # Parse Key
        key_start = i
        while i < content_len and (content[i].isalnum() or content[i] == '_'):
            i += 1
        key = content[key_start:i]
        
        if not key:
            # Skip invalid characters to next line
            while i < content_len and content[i] != '\n':
                i += 1
            continue
            
        # Skip spaces before '='
        while i < content_len and content[i].isspace() and content[i] != '\n':
            i += 1
            
        if i >= content_len or content[i] != '=':
            # Skip to next line
            while i < content_len and content[i] != '\n':
                i += 1
            continue
            
        # Skip '='
        i += 1
        
        # Skip spaces after '='
        while i < content_len and content[i].isspace() and content[i] != '\n':
            i += 1
            
        if i >= content_len:
            vars_dict[key] = ""
            break
            
        # Check if value starts with triple backticks ```
        if content[i:i+3] == "```":
            i += 3
            val_chars = []
            # Read until next ```
            while i < content_len:
                if content[i:i+3] == "```":
                    i += 3
                    break
                val_chars.append(content[i])
                i += 1
            value = "".join(val_chars)
            # Strip single leading newline
            if value.startswith("\r\n"):
                value = value[2:]
            elif value.startswith("\n"):
                value = value[1:]
            # Strip single trailing newline
            if value.endswith("\r\n"):
                value = value[:-2]
            elif value.endswith("\n"):
                value = value[:-1]
        else:
            # Read all content of single line after '='
            val_start = i
            while i < content_len and content[i] != '\n':
                i += 1
            value = content[val_start:i].strip()
            if value.endswith('\r'):
                value = value[:-1].strip()
                
        vars_dict[key] = value

    return vars_dict

def resolve_file_inclusions(content, base_dir):
    """
    Finds and resolves all {{file:<path>}} occurrences.
    Replaces them with the actual contents of the target file.
    """
    pattern = r'\{\{\s*file:([^\}]+)\s*\}\}'
    
    def replacer(match):
        rel_path = match.group(1).strip()
        abs_path = os.path.abspath(os.path.join(base_dir, rel_path))
        if os.path.exists(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                print(f"Warning: Failed to read included file at '{abs_path}': {e}")
                return match.group(0)
        else:
            print(f"Warning: Included file not found at '{abs_path}'")
        return match.group(0)
        
    return re.sub(pattern, replacer, content)

def find_prompt_idx():
    """
    Searches for prompt.idx in multiple standard locations, prioritizing the module directory
    to ensure it works reliably in containerized and serverless environments (Docker/Cloud Functions).
    """
    # 1. First, check relative to the prompt_utils module/file directory
    try:
        module_dir = os.path.dirname(os.path.abspath(__file__))
        idx_path = os.path.join(module_dir, "prompt.idx")
        if os.path.exists(idx_path):
            return idx_path
    except NameError:
        pass

    # 2. Walk upwards from module directory to find prompt.idx
    try:
        curr = os.path.dirname(os.path.abspath(__file__))
        for _ in range(4):
            candidate = os.path.join(curr, "prompt.idx")
            if os.path.exists(candidate):
                return candidate
            candidate_sub = os.path.join(curr, "queryGemini", "prompt.idx")
            if os.path.exists(candidate_sub):
                return candidate_sub
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent
    except NameError:
        pass

    # 3. Fallback to current working directory
    if os.path.exists("prompt.idx"):
        return os.path.abspath("prompt.idx")
        
    curr = os.getcwd()
    for _ in range(4):
        candidate = os.path.join(curr, "prompt.idx")
        if os.path.exists(candidate):
            return candidate
        # Try subdirectory match
        candidate_sub = os.path.join(curr, "bopsutils", "TestScript", "queryGemini", "prompt.idx")
        if os.path.exists(candidate_sub):
            return candidate_sub
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
        
    return None

def getPrompt(prompt_name, json_input=None):
    """
    Common library function to load prompt content, process arguments, and return text.
    
    Arguments:
        prompt_name (str): The name of the prompt to look up (e.g. "prompt_agent1")
        json_input (dict or str, optional): JSON string or dict with key value overrides/arguments. Defaults to None.
        
    Returns:
        str: The updated prompt text after variable substitution
    """
    # 1. Parse dynamic JSON input argument
    if json_input is None:
        json_input = {}
    elif isinstance(json_input, str):
        try:
            json_input = json.loads(json_input)
        except Exception as e:
            print(f"Warning: Failed to parse json_input string: {e}")
            json_input = {}

    # 2. Find and open prompt.idx
    idx_path = find_prompt_idx()
    if not idx_path or not os.path.exists(idx_path):
        raise FileNotFoundError("Could not locate 'prompt.idx' file.")

    idx_dir = os.path.dirname(idx_path)
    
    # 3. Search for prompt_name in prompt.idx
    prompt_filepath = None
    env_filepath = None
    
    with open(idx_path, "r", encoding="utf-8") as idx_file:
        # Read header first
        header = idx_file.readline()
        for line in idx_file:
            parsed = parse_idx_line(line)
            if parsed:
                name, p_path, e_path = parsed
                if name == prompt_name:
                    prompt_filepath = p_path
                    env_filepath = e_path
                    break
                    
    if not prompt_filepath:
        raise ValueError(f"Prompt name '{prompt_name}' not found in prompt.idx")
        
    # 4. Resolve absolute paths relative to prompt.idx location
    prompt_abs_path = os.path.abspath(os.path.join(idx_dir, prompt_filepath))
    env_abs_path = os.path.abspath(os.path.join(idx_dir, env_filepath)) if env_filepath else None
    
    # 5. Read prompt file content
    if not os.path.exists(prompt_abs_path):
        raise FileNotFoundError(f"Prompt file not found at: {prompt_abs_path}")
        
    with open(prompt_abs_path, "r", encoding="utf-8") as pf:
        prompt_content = pf.read()
        
    # 6. Resolve any {{file:<path>}} file inclusions first
    prompt_content = resolve_file_inclusions(prompt_content, os.path.dirname(prompt_abs_path))
    
    # 7. Parse env file key-value pairs
    env_vars = {}
    if env_abs_path and os.path.exists(env_abs_path):
        env_vars = parse_env_file(env_abs_path)
    else:
        # Fallback: if the exact env file name is not found, check if there's a file matching without path details
        # or if the user passed it as input_-1.txt etc.
        # But if it isn't there, we just warn or proceed
        if env_abs_path:
            print(f"Warning: env file not found at: {env_abs_path}")
            
    # 8. Merge env_vars and dynamic json_input overrides
    merged_vars = {}
    if env_vars:
        merged_vars.update(env_vars)
    if json_input and isinstance(json_input, dict):
        merged_vars.update(json_input)
        
    # 9. Perform variable substitutions (replace {{KEY}} with VALUE)
    for key, val in merged_vars.items():
        placeholder = f"{{{{{key}}}}}"
        prompt_content = prompt_content.replace(placeholder, str(val))
        
    return prompt_content
