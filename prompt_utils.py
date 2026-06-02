# -*- coding: utf-8 -*-
"""
Prompt Loader Utility
Author: Bopaiah Mekerira

Description:
    A utility library to load prompt content, resolve file inclusions, parse
    prompt-specific env files, and substitute placeholders with dynamic variables.

    The location of the prompt index file (prompt.idx) is resolved from the
    environment using:
        PROJECT_ROOT  (set automatically from the .env file location)
        _PROMPT_IDX_PATH  (relative path to prompt.idx, set in .env)

    Full path = PROJECT_ROOT + _PROMPT_IDX_PATH
    Example .env entries:
        _PROMPT_IDX_PATH=prompts/prompt.idx

prompt.idx format (CSV, header row required):
    prompt_name, prompt_filepath, env_filepath
    - prompt_name    : unique key used to look up the prompt
    - prompt_filepath: path to the prompt text file (relative to prompt.idx location)
    - env_filepath   : path to the prompt-specific env/args file (optional; omit or leave blank)

    If env_filepath is provided but the file does not exist, a FileNotFoundError is raised.
    If env_filepath is blank or absent, no env file is loaded (silently skipped).

Placeholder syntax in prompt files:
    {{KEY}}              — replaced with the value of KEY from the env file or json_input
    {{file:./path.txt}}  — replaced with the full contents of the referenced file

Use Cases:
    - Load a named prompt template and substitute variables from its associated env file.
    - Override or extend env file variables at call time via json_input.
    - Compose large prompts from multiple files using {{file:...}} inclusions.

Public API:
    getPrompt(prompt_name, json_input=None) -> str
        Load and return the fully resolved prompt text.

    clear_caches()
        Invalidate all in-memory file/index/env caches (useful in tests or long-running processes).
"""

# --- Standard library imports ---
import os
import re
import json

# --- Local imports ---
from env_utils import get_env

_DOT_PATH_SPLIT_RE = re.compile(r'\.\s+(?=\.?/)')
_FILE_INCLUDE_RE = re.compile(r'\{\{\s*file:([^}]+)\s*\}\}')
_PLACEHOLDER_RE = re.compile(r'\{\{([^{}]+)\}\}')

_FILE_TEXT_CACHE = {}
_ENV_CACHE = {}
_IDX_CACHE = {}


def clear_caches():
    """
    Clears all in-memory caches used by the prompt loader.

    Caches are maintained for:
      - File text content (_FILE_TEXT_CACHE)
      - Parsed env/args files (_ENV_CACHE)
      - Parsed prompt index (_IDX_CACHE)

    Call this in tests or when files may have changed during a long-running process.
    """
    _FILE_TEXT_CACHE.clear()
    _ENV_CACHE.clear()
    _IDX_CACHE.clear()


def _path_signature(filepath):
    """
    Returns a (mtime_ns, size) tuple for the given file path, used as a cache key.
    Returns None if the file does not exist or cannot be stat'd.
    """
    try:
        stat = os.stat(filepath)
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _read_text_cached(filepath, *, warn_label="file", signature=None):
    """
    Reads and returns the UTF-8 text content of a file, using an in-memory cache.
    The cache is keyed by (filepath, signature) where signature = (mtime_ns, size).
    Returns None if the file cannot be read.

    Args:
        filepath (str): Absolute path to the file.
        warn_label (str): Label used in warning messages (e.g. "prompt file", "env file").
        signature (tuple, optional): Pre-computed path signature. Computed if not provided.
    """
    if signature is None:
        signature = _path_signature(filepath)
    if signature is None:
        return None

    cached = _FILE_TEXT_CACHE.get(filepath)
    if cached and cached[0] == signature:
        return cached[1]

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Warning: Could not read {warn_label} at '{filepath}': {e}")
        return None

    _FILE_TEXT_CACHE[filepath] = (signature, content)
    return content


def parse_idx_line(line):
    """
    Parses a single data line from prompt.idx into a (name, prompt_path, env_path) tuple.

    Supported formats:
      - 3-column CSV:  name, prompt_filepath, env_filepath
      - 2-column CSV:  name, prompt_filepath          (env_filepath treated as None)
      - Dot-space sep: name, prompt_filepath. env_filepath  (legacy format)

    Rules:
      - Blank lines return None.
      - A blank or whitespace-only env_filepath column is returned as None.

    Returns:
        tuple: (name, prompt_filepath, env_filepath_or_None), or None if the line is invalid.
    """
    line = line.strip()
    if not line:
        return None
    # Split by comma first
    parts = [p.strip() for p in line.split(',')]
    if len(parts) >= 3:
        e_path = parts[2].strip() or None
        return parts[0], parts[1], e_path
    elif len(parts) == 2:
        name = parts[0]
        rest = parts[1]
        # Check if the second and third columns are separated by dot and space (e.g. ". ")
        sub_parts = _DOT_PATH_SPLIT_RE.split(rest)
        if len(sub_parts) == 2:
            return name, sub_parts[0].strip(), sub_parts[1].strip() or None
        else:
            sub_parts = rest.split(". ")
            if len(sub_parts) >= 2:
                return name, sub_parts[0].strip(), sub_parts[1].strip() or None
        # Only one value after the name — treat as prompt_filepath with no env file
        return name, rest, None
    return None


def parse_env_file(filepath, signature=None):
    """
    Parses a prompt-specific env/args file into a key-value dictionary.

    File format:
      - Lines of the form:  KEY=value
      - Lines starting with '#' are comments and are ignored.
      - Multi-line values are delimited by triple backticks (```):
            KEY=```
            line one
            line two
            ```
      - All other values are read as a single line (everything after '=').
      - Results are cached by (filepath, signature) to avoid redundant I/O.

    Args:
        filepath (str): Absolute path to the env file.
        signature (tuple, optional): Pre-computed path signature. Computed if not provided.

    Returns:
        dict: Parsed key-value pairs. Returns an empty dict if the file cannot be read.
    """
    if signature is None:
        signature = _path_signature(filepath)
    if signature is None:
        return {}

    cached = _ENV_CACHE.get(filepath)
    if cached and cached[0] == signature:
        return cached[1].copy()

    vars_dict = {}
    content = _read_text_cached(filepath, warn_label="env file", signature=signature)
    if content is None:
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

    _ENV_CACHE[filepath] = (signature, vars_dict.copy())
    return vars_dict


def resolve_file_inclusions(content, base_dir):
    """
    Resolves all {{file:<path>}} inclusions in a prompt string.

    Each occurrence of {{file:./relative/path.txt}} is replaced with the full
    UTF-8 text content of the referenced file. Paths are resolved relative to
    base_dir (typically the directory containing the prompt file).

    If a referenced file is not found, a warning is printed and the original
    placeholder is left unchanged.

    Args:
        content (str): The prompt text potentially containing {{file:...}} tags.
        base_dir (str): Base directory for resolving relative file paths.

    Returns:
        str: The prompt text with all resolvable file inclusions substituted.
    """
    def replacer(match):
        rel_path = match.group(1).strip()
        abs_path = os.path.abspath(os.path.join(base_dir, rel_path))
        included = _read_text_cached(abs_path, warn_label="included file")
        if included is not None:
            return included
        if _path_signature(abs_path) is None:
            print(f"Warning: Included file not found at '{abs_path}'")
        return match.group(0)

    return _FILE_INCLUDE_RE.sub(replacer, content)


def _load_prompt_index(idx_path, signature=None):
    """
    Reads and parses prompt.idx into a dict mapping prompt_name -> (prompt_path, env_path).

    The first line (header) is skipped. Results are cached by (idx_path, signature).

    Args:
        idx_path (str): Absolute path to the prompt.idx file.
        signature (tuple, optional): Pre-computed path signature.

    Returns:
        dict: {prompt_name: (prompt_filepath, env_filepath_or_None)}

    Raises:
        FileNotFoundError: If the file cannot be located or read.
    """
    if signature is None:
        signature = _path_signature(idx_path)
    if signature is None:
        raise FileNotFoundError("Could not locate 'prompt.idx' file.")

    cached = _IDX_CACHE.get(idx_path)
    if cached and cached[0] == signature:
        return cached[1]

    content = _read_text_cached(idx_path, warn_label="prompt.idx", signature=signature)
    if content is None:
        raise FileNotFoundError("Could not read 'prompt.idx' file.")

    prompt_index = {}
    for line in content.splitlines()[1:]:  # skip header row
        parsed = parse_idx_line(line)
        if parsed:
            name, p_path, e_path = parsed
            prompt_index[name] = (p_path, e_path)

    _IDX_CACHE[idx_path] = (signature, prompt_index)
    return prompt_index


def _substitute_placeholders(prompt_content, merged_vars):
    """
    Replaces all {{KEY}} placeholders in prompt_content with values from merged_vars.

    Keys and values are both coerced to strings. Unmatched placeholders are left unchanged.

    Args:
        prompt_content (str): The prompt text containing {{KEY}} placeholders.
        merged_vars (dict): Key-value pairs to substitute.

    Returns:
        str: The prompt text with all matched placeholders replaced.
    """
    if not merged_vars:
        return prompt_content

    values = {str(key): str(val) for key, val in merged_vars.items()}

    def replacer(match):
        key = match.group(1)
        return values.get(key, match.group(0))

    return _PLACEHOLDER_RE.sub(replacer, prompt_content)


def getPrompt(prompt_name, json_input=None):
    """
    Loads and returns a fully resolved prompt string for the given prompt name.

    Resolution steps:
      1. Parse json_input (if provided as a JSON string, decode it to a dict).
      2. Locate prompt.idx using PROJECT_ROOT + _PROMPT_IDX_PATH from the environment.
      3. Look up prompt_name in prompt.idx to get (prompt_filepath, env_filepath).
      4. Resolve both paths relative to the prompt.idx directory.
      5. Read the prompt file content.
      6. Resolve any {{file:...}} inclusions in the prompt content.
      7. Parse the associated env file (if specified and exists).
         - If env_filepath is blank/absent: silently skip (no env vars loaded).
         - If env_filepath is specified but the file does not exist: raise FileNotFoundError.
      8. Merge env file variables with json_input overrides (json_input takes precedence).
      9. Substitute all {{KEY}} placeholders with merged variable values.

    Args:
        prompt_name (str): The name of the prompt entry in prompt.idx (e.g. "prompt2").
        json_input (dict or str, optional): Additional variables to inject or override.
            Accepts a dict or a JSON-encoded string. Defaults to None.

    Returns:
        str: The fully resolved prompt text ready to send to a model.

    Raises:
        FileNotFoundError: If prompt.idx, the prompt file, or a specified env file is not found.
        ValueError: If prompt_name is not found in prompt.idx.
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

    # 2. Resolve prompt.idx path via environment variables (PROJECT_ROOT + _PROMPT_IDX_PATH)
    root = get_env("PROJECT_ROOT")
    rel_path = get_env("_PROMPT_IDX_PATH")
    if not root or not rel_path:
        raise FileNotFoundError(
            "Could not locate 'prompt.idx': PROJECT_ROOT or _PROMPT_IDX_PATH not set in environment."
        )
    idx_path = os.path.abspath(root + rel_path)
    idx_signature = _path_signature(idx_path)
    if idx_signature is None:
        raise FileNotFoundError(f"Could not locate 'prompt.idx' at: {idx_path}")

    idx_dir = os.path.dirname(idx_path)

    # 3. Look up prompt_name in prompt.idx
    prompt_index = _load_prompt_index(idx_path, idx_signature)
    prompt_entry = prompt_index.get(prompt_name)

    if not prompt_entry:
        raise ValueError(f"Prompt name '{prompt_name}' not found in prompt.idx")

    prompt_filepath, env_filepath = prompt_entry

    # 4. Resolve absolute paths relative to prompt.idx location
    prompt_abs_path = os.path.abspath(os.path.join(idx_dir, prompt_filepath))
    env_abs_path = os.path.abspath(os.path.join(idx_dir, env_filepath)) if env_filepath else None

    # 5. Read prompt file content
    prompt_signature = _path_signature(prompt_abs_path)
    if prompt_signature is None:
        raise FileNotFoundError(f"Prompt file not found at: {prompt_abs_path}")

    prompt_content = _read_text_cached(prompt_abs_path, warn_label="prompt file", signature=prompt_signature)
    if prompt_content is None:
        raise FileNotFoundError(f"Prompt file not readable at: {prompt_abs_path}")

    # 6. Resolve any {{file:<path>}} file inclusions
    prompt_content = resolve_file_inclusions(prompt_content, os.path.dirname(prompt_abs_path))

    # 7. Parse env file key-value pairs
    env_vars = {}
    env_signature = _path_signature(env_abs_path) if env_abs_path else None
    if env_abs_path and env_signature is not None:
        env_vars = parse_env_file(env_abs_path, env_signature)
    elif env_abs_path:
        raise FileNotFoundError(f"Env file specified but not found at: {env_abs_path}")
    # else: env_filepath was blank in prompt.idx — silently skip

    # 8. Merge env_vars with json_input overrides (json_input takes precedence)
    merged_vars = {}
    if env_vars:
        merged_vars.update(env_vars)
    if json_input and isinstance(json_input, dict):
        merged_vars.update(json_input)

    # 9. Perform variable substitutions (replace {{KEY}} with VALUE)
    return _substitute_placeholders(prompt_content, merged_vars)
