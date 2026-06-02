# -*- coding: utf-8 -*-
"""
Environment Utilities
Author: Bopaiah Mekerira

Description:
    Provides a unified interface for resolving environment variables and secrets
    across local development and Google Cloud production environments.

    On module load:
      - Locates and loads the nearest .env file using python-dotenv.
      - Derives PROJECT_ROOT from the .env file location (or falls back to cwd).
      - Caches PROJECT_ROOT so it is immediately available via get_env("PROJECT_ROOT").

    Variable resolution priority (in get_env):
      1. config_json argument  — caller-supplied overrides (ignored in PROD_ENV=TRUE)
      2. In-memory cache       — previously resolved values
      3. GCP Secret Manager    — only when PROD_ENV=TRUE and key does not start with '_'
      4. Local environment     — os.getenv() / .env file values (with {{KEY}} placeholder support)

    .env conventions:
      - PROD_ENV=TRUE          enables GCP Secret Manager lookups
      - DEBUG=TRUE             enables verbose debug logging throughout this module
      - _GOOGLE_CLOUD_PROJECT  GCP project ID (leading '_' prevents Secret Manager lookup)
      - Variables starting with '_' are always resolved locally (never from Secret Manager)
      - Values may reference other env vars using {{KEY}} syntax (resolved recursively)

Public API:
    get_env(variable_name, config_json=None) -> str | None
        Resolve an environment variable using the priority chain above.

    get_project_root() -> str
        Convenience wrapper; returns the absolute project root path (ends with '/').

    clear_env_cache()
        Clears the in-memory cache. Useful in tests or after .env changes.
"""

# --- Standard library imports ---
import os
import re

# --- Third-party imports ---
from dotenv import load_dotenv, find_dotenv

# In-memory cache for resolved environment variables to minimize I/O and API calls
_ENV_CACHE = {}
_SECRET_CLIENT = None
IS_DEBUG = str(os.getenv("DEBUG", "")).upper() == "TRUE"


def _update_debug_mode():
    """Updates the global IS_DEBUG flag from the current environment."""
    global IS_DEBUG
    IS_DEBUG = str(os.getenv("DEBUG", "")).upper() == "TRUE"


# --- Module initialisation: locate and load .env, derive PROJECT_ROOT ---
_dotenv_path = find_dotenv()
print(f"[init] find_dotenv() -> '{_dotenv_path}'")
load_dotenv(_dotenv_path)
print(f"[init] load_dotenv() complete")

if _dotenv_path:
    project_root = os.path.dirname(os.path.abspath(_dotenv_path))
    print(f"[init] project_root derived from .env path: '{project_root}'")
else:
    # Fallback if no .env file is found
    project_root = os.getcwd()
    print(f"[init] No .env found; project_root fallback to cwd: '{project_root}'")

if not project_root.endswith('/'):
    project_root += '/'

_ENV_CACHE["PROJECT_ROOT"] = project_root
print(f"[init] PROJECT_ROOT cached as: '{project_root}'")


def get_project_root():
    """
    Returns the absolute path to the project root directory (where .env is located).

    The path always ends with '/'. Derived at module load time from the .env file
    location, or falls back to the current working directory.

    Returns:
        str: Absolute project root path ending with '/'.
    """
    _update_debug_mode()
    if IS_DEBUG:
        print("[get_project_root] Called")
    result = get_env("PROJECT_ROOT")
    if IS_DEBUG:
        print(f"[get_project_root] Returning: '{result}'")
    return result


def _get_secret_client():
    """
    Lazily initializes and returns the Google Cloud Secret Manager client.

    The client is created once and cached in _SECRET_CLIENT. If the
    google-cloud-secret-manager library is not installed, returns None.

    Returns:
        SecretManagerServiceClient | None
    """
    global _SECRET_CLIENT
    _update_debug_mode()
    if IS_DEBUG:
        print("[SECRET] _get_secret_client() called")
    if _SECRET_CLIENT is None:
        if IS_DEBUG:
            print("[SECRET] Client not yet initialized; creating SecretManagerServiceClient...")
        try:
            if IS_DEBUG:
                print("[SECRET] Step 1/3: importing google.cloud.secretmanager...")
            from google.cloud import secretmanager
            if IS_DEBUG:
                print("[SECRET] Step 2/3: import OK; calling SecretManagerServiceClient() constructor...")
            _SECRET_CLIENT = secretmanager.SecretManagerServiceClient()
            if IS_DEBUG:
                print("[SECRET] Step 3/3: constructor returned — client ready")
        except ImportError:
            if IS_DEBUG:
                print("[SECRET][ERROR] google-cloud-secret-manager library is not installed. Secret Manager will not be queried.")
        except Exception as e:
            if IS_DEBUG:
                print(f"[SECRET][ERROR] Failed to initialize Secret Manager client: {type(e).__name__}: {e}")
    else:
        if IS_DEBUG:
            print("[SECRET] Returning already-cached Secret Manager client")
    return _SECRET_CLIENT


def _get_gcp_project_id():
    """
    Resolves the GCP Project ID using the following priority:
      1. _GOOGLE_CLOUD_PROJECT environment variable
      2. GOOGLE_CLOUD_PROJECT environment variable (standard Cloud Functions variable)
      3. GCP_PROJECT_ID environment variable (legacy fallback)
      4. Auto-discovery via google.auth.default()

    Returns:
        str | None: The GCP project ID, or None if it cannot be determined.
    """
    _update_debug_mode()
    if IS_DEBUG:
        print("[_get_gcp_project_id] Called")

    project_id = os.getenv("_GOOGLE_CLOUD_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    if project_id:
        if IS_DEBUG:
            print(f"[_get_gcp_project_id] Found via env var: '{project_id}'")
        return project_id

    if IS_DEBUG:
        print("[_get_gcp_project_id] Not found in env vars; trying google.auth.default()...")
    try:
        import google.auth
        _, project_id = google.auth.default()
        if IS_DEBUG:
            print(f"[_get_gcp_project_id] google.auth.default() returned: '{project_id}'")
        return project_id
    except Exception as e:
        if IS_DEBUG:
            print(f"[_get_gcp_project_id] google.auth.default() failed: {e}")
        return None


def _mask_debug_value(value):
    """
    Returns a masked string representation suitable for debug logging.
    Short values (<=4 chars) are fully masked as '***'.
    Longer values show first and last character only: 'A***Z'.
    """
    s = str(value)
    if len(s) <= 4:
        return "***"
    return f"{s[0]}***{s[-1]}"


def _fetch_from_secret_manager(variable_name):
    """
    Fetches the latest version of a secret from Google Cloud Secret Manager.

    Only called when PROD_ENV=TRUE and the variable name does not start with '_'.

    Args:
        variable_name (str): The secret name in Secret Manager.

    Returns:
        str | None: The decoded secret payload, or None if not found or on error.
    """
    _update_debug_mode()
    if IS_DEBUG:
        print(f"[SECRET] _fetch_from_secret_manager() called for secret: '{variable_name}'")

    client = _get_secret_client()
    if not client:
        if IS_DEBUG:
            print(f"[SECRET][ERROR] No Secret Manager client available; cannot fetch '{variable_name}'")
        return None

    project_id = _get_gcp_project_id()
    if not project_id:
        if IS_DEBUG:
            print(f"[SECRET][ERROR] Could not determine GCP project ID; cannot fetch '{variable_name}'")
        return None

    # Construct the secret version resource name
    name = f"projects/{project_id}/secrets/{variable_name}/versions/latest"
    if IS_DEBUG:
        print(f"[SECRET] Accessing secret path: '{name}'")
    try:
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        if IS_DEBUG:
            print(f"[SECRET] Successfully retrieved secret '{variable_name}' (value: {_mask_debug_value(payload)}, length: {len(payload)})")
        return payload
    except Exception as e:
        # Secret doesn't exist, permission denied, or other error
        if IS_DEBUG:
            print(f"[SECRET][ERROR] Failed to retrieve '{variable_name}': {type(e).__name__}: {e}")
        return None


def get_env(variable_name, config_json=None):
    """
    Resolves an environment variable or secret using a prioritised lookup chain.

    Priority order:
      1. config_json argument  — caller-supplied dict (skipped when PROD_ENV=TRUE)
      2. In-memory cache       — previously resolved and cached values
      3. GCP Secret Manager    — only when PROD_ENV=TRUE and name does not start with '_'
      4. Local environment     — os.getenv() / .env loaded values
         Values containing {{KEY}} placeholders are resolved recursively.

    Notes:
      - Variables whose names start with '_' are always resolved locally (step 4),
        never from Secret Manager. This is used for internal/config variables like
        _PROMPT_IDX_PATH, _CONTEXT_CACHING, _GOOGLE_CLOUD_PROJECT.
      - Resolved values are stored in the in-memory cache for subsequent calls.
      - PROJECT_ROOT is pre-populated in the cache at module load time.

    Args:
        variable_name (str): The environment variable or secret name to resolve.
        config_json (dict, optional): Caller-supplied overrides. Not used in PROD_ENV=TRUE.

    Returns:
        str | None: The resolved value, or None if not found anywhere.
    """
    _update_debug_mode()
    is_prod = str(os.getenv("PROD_ENV", "")).upper() == "TRUE"

    if IS_DEBUG:
        print(f"[get_env] Resolving: {variable_name}")

    # 1. Check Config Argument (config_json). Not saved to cache.
    # Ignored if PROD_ENV=TRUE to prevent overriding production secrets.
    if not is_prod and config_json and variable_name in config_json:
        val = config_json[variable_name]
        if IS_DEBUG:
            print(f"  -> [Config] Found in config_json: {_mask_debug_value(val)}")
        return val

    # 2. Check In-Memory Cache
    if variable_name in _ENV_CACHE:
        val = _ENV_CACHE[variable_name]
        if IS_DEBUG:
            print(f"  -> [Cache] Found in _ENV_CACHE: {_mask_debug_value(val)}")
        return val

    # 3. Check GCP Secret Manager (PROD only; skipped for names starting with '_')
    if is_prod and not variable_name.startswith('_'):
        if IS_DEBUG:
            print(f"[SECRET] get_env() -> querying Secret Manager for '{variable_name}'")
        secret_value = _fetch_from_secret_manager(variable_name)
        if secret_value is not None:
            masked = (secret_value[:2] + "***" + secret_value[-2:]) if len(secret_value) > 4 else "***"
            if IS_DEBUG:
                print(f"  -> [SecretManager] Found '{variable_name}' (value: {masked}); cached.")
            _ENV_CACHE[variable_name] = secret_value
            return secret_value
        else:
            if IS_DEBUG:
                print(f"[SECRET] Secret Manager: '{variable_name}' not found; falling through to local env.")
    else:
        if IS_DEBUG:
            reason = "variable starts with '_'" if variable_name.startswith('_') else "PROD_ENV not set"
            print(f"  -> [SecretManager] Skipped for '{variable_name}' ({reason})")

    # 4. Check Local Environment (os.getenv / .env)
    if IS_DEBUG:
        print(f"  -> [LocalEnv] Checking os.getenv('{variable_name}')...")
    env_value = os.getenv(variable_name)
    if env_value is not None:
        if IS_DEBUG:
            print(f"  -> [LocalEnv] Found: {_mask_debug_value(env_value)}")
        # Resolve {{KEY}} placeholders recursively
        resolved_value = _resolve_placeholders(env_value, config_json)
        if IS_DEBUG and resolved_value != env_value:
            print(f"  -> [LocalEnv] Resolved to: {_mask_debug_value(resolved_value)}")
        _ENV_CACHE[variable_name] = resolved_value
        return resolved_value

    if IS_DEBUG:
        print(f"  -> [get_env] Not found.")
    return None


def _resolve_placeholders(text, config_json=None):
    """
    Recursively resolves {{KEY}} placeholders within a string value.

    Each {{KEY}} token is replaced by calling get_env(KEY), which itself
    supports the full priority chain (cache, Secret Manager, local env).
    Unresolved placeholders are left unchanged.

    Args:
        text (str): The string potentially containing {{KEY}} tokens.
        config_json (dict, optional): Passed through to get_env for config overrides.

    Returns:
        str: The string with all resolvable placeholders substituted.
    """
    _update_debug_mode()
    if IS_DEBUG:
        print(f"[_resolve_placeholders] Called with text: '{_mask_debug_value(text)}'")

    if not isinstance(text, str) or "{{" not in text:
        if IS_DEBUG:
            print(f"[_resolve_placeholders] No placeholders found; returning as-is: '{_mask_debug_value(text)}'")
        return text

    def replace(match):
        key = match.group(1).strip()
        if IS_DEBUG:
            print(f"[_resolve_placeholders] Resolving placeholder key: '{key}'")
        val = get_env(key, config_json)
        if val is not None:
            if IS_DEBUG:
                print(f"[_resolve_placeholders] '{key}' -> '{_mask_debug_value(val)}'")
            return str(val)
        if IS_DEBUG:
            print(f"[_resolve_placeholders] '{key}' not found; keeping original placeholder")
        return match.group(0)

    resolved = re.sub(r"\{\{(.*?)\}\}", replace, text)
    if IS_DEBUG:
        print(f"[_resolve_placeholders] Final resolved text: '{_mask_debug_value(resolved)}'")
    return resolved


def clear_env_cache():
    """
    Clears the in-memory environment variable cache.

    After clearing, the next call to get_env() for any variable will re-resolve
    it from config_json, Secret Manager, or the local environment.

    Note: PROJECT_ROOT is NOT automatically re-populated after clearing.
    If needed, re-import or re-initialize the module.
    """
    _update_debug_mode()
    global _ENV_CACHE
    if IS_DEBUG:
        print(f"[clear_env_cache] Clearing cache with {len(_ENV_CACHE)} entries: {list(_ENV_CACHE.keys())}")
    _ENV_CACHE.clear()
    if IS_DEBUG:
        print("[clear_env_cache] Cache cleared")
