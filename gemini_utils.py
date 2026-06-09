# -*- coding: utf-8 -*-
"""
Gemini Utilities
Author: Bopaiah Mekerira

Description:
    Utility functions for interacting with Google's Gemini models via the
    google-genai SDK. Provides helpers to:
      - Initialize a Gemini API client
      - Resolve model, API key, and generation config from environment variables
      - Query Gemini with text prompts (with optional context caching)
      - Analyze images using the Gemini Files API
      - Edit/process images using multimodal Gemini models
      - Parse and normalize model responses (text or JSON)
      - Extract token usage metadata from responses

    Environment variable conventions (resolved via env_utils.get_env):
      Each functional area uses a named prefix (e.g. "GEO", "IMAGE") to group
      its configuration variables in .env:
        {PREFIX}_MODEL      — Gemini model name (required)
        {PREFIX}_API_KEY    — Gemini API key (required)
        {PREFIX}_CONFIG     — JSON string of generation config options (optional)

      Global settings:
        _CONTEXT_CACHING    — Set to TRUE to enable context caching for system instructions

    System instruction syntax in prompts:
      Embed a system instruction directly in the prompt text using:
        system_instruction===<your instruction>===system_instruction
      It will be extracted and passed as the system_instruction config parameter.

Public API:
    get_gemini_client(api_key, api_version="v1beta") -> genai.Client
        Create and return a Gemini API client.

    list_gemini_models(api_key) -> list
        Return a list of all available Gemini models.

    query_gemini(model_prefix, contents) -> dict
        Send a text prompt to Gemini and return response_data + token_usage.

    analyze_image(model_prefix, prompt, image_path) -> dict
        Upload an image and query Gemini for a text analysis response.

    edit_image(model_prefix, prompt, image_path, output_path) -> dict
        Upload an image, request an edited image output, and save it to output_path.

    parse_response_text(response_text) -> dict
        Parse a Gemini text response into a typed content envelope
        {"content_type": "json"|"text", "data": ...}.

    extract_token_usage(usage) -> dict
        Extract token usage metadata from a Gemini response usage_metadata object.
"""

# --- Standard library imports ---
import os
import re
import json
import time

# --- Optional third-party imports ---
try:
    from PIL import Image as PIL_Image
except ImportError:
    PIL_Image = None

# --- Local imports ---
from env_utils import get_env


def import_genai():
    """
    Lazily imports and returns the google.genai module.

    Raises:
        ImportError: If the google-genai package is not installed.

    Returns:
        module: The google.genai module.
    """
    try:
        from google import genai
        return genai
    except ImportError:
        raise ImportError("The 'google-genai' library is required. Install it with: pip install google-genai")


def get_gemini_client(api_key, api_version="v1beta"):
    """
    Initializes and returns a Gemini API client.

    Args:
        api_key (str): The Gemini API key.
        api_version (str): API version to use. Defaults to "v1beta" for early-access models.

    Returns:
        genai.Client: An initialized Gemini client instance.
    """
    genai = import_genai()
    return genai.Client(api_key=api_key, http_options={"api_version": api_version})


def list_gemini_models(api_key):
    """
    Returns a list of all available Gemini models for the given API key.

    Args:
        api_key (str): The Gemini API key.

    Returns:
        list: A list of model objects returned by the Gemini API.

    Raises:
        Exception: Propagates any API or network errors.
    """
    try:
        client = get_gemini_client(api_key)
        # Force conversion to list to ensure all pages are fetched
        # while the client is still active in this scope.
        return list(client.models.list())
    except Exception as e:
        raise e


def parse_response_text(response_text):
    """
    Parses a Gemini text response into a typed content envelope.

    Attempts to extract and parse JSON from markdown code fences (```json or ```).
    If the extracted content is valid JSON, returns a json envelope.
    Otherwise returns a text envelope with the cleaned or original text.

    Handles truncated fenced responses (missing closing ```) by taking
    everything after the opening fence.

    Args:
        response_text (str): The raw text response from Gemini.

    Returns:
        dict: A content envelope with keys:
            - "content_type": "json" or "text"
            - "data": parsed JSON object (dict/list) or plain text string
    """
    if not response_text or not isinstance(response_text, str):
        # None or empty string: return a clear empty text envelope
        # (e.g. when the model returns only image parts with no text)
        return {
            "content_type": "text",
            "data": ""
        }

    original_text = response_text
    cleaned = response_text.strip()
    extracted_from_fence = False

    # 1. Try to extract content from markdown fences (```json or ```)
    for fence in ["```json", "```"]:
        if fence in cleaned:
            extracted_from_fence = True
            start_idx = cleaned.find(fence) + len(fence)
            # Find the next closing fence after the start
            end_idx = cleaned.find("```", start_idx)
            if end_idx != -1:
                cleaned = cleaned[start_idx:end_idx].strip()
            else:
                # If closing fence is missing (truncated), take everything until the end
                cleaned = cleaned[start_idx:].strip()
            break

    def _try_parse_json(text):
        """Try strict parse first, then lenient (allows unescaped control chars)."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            return None

    # 2. Attempt JSON parse on the cleaned/fenced content
    parsed = _try_parse_json(cleaned)
    if parsed is not None:
        return {
            "content_type": "json",
            "data": parsed
        }

    # 3. If not extracted from a fence, also try parsing the original text as JSON
    #    (handles cases where the model returns raw JSON without markdown fences)
    if not extracted_from_fence:
        parsed = _try_parse_json(original_text.strip())
        if parsed is not None:
            return {
                "content_type": "json",
                "data": parsed
            }

    return {
        "content_type": "text",
        "data": cleaned if extracted_from_fence else original_text
    }


def extract_token_usage(usage):
    """
    Extracts token usage metadata from a Gemini response usage_metadata object.

    Tries multiple extraction strategies (model_dump, dict, attribute inspection)
    to handle different SDK versions. Always ensures the standard fields
    prompt_token_count, candidates_token_count, and total_token_count are present
    if available.

    Args:
        usage: The usage_metadata object from a Gemini response, or None.

    Returns:
        dict: Token usage fields as a flat dictionary. Empty dict if usage is None.
    """
    token_usage = {}
    if usage is not None:
        if hasattr(usage, "model_dump"):
            try:
                token_usage = usage.model_dump()
            except Exception:
                pass
        if not token_usage and hasattr(usage, "dict"):
            try:
                token_usage = usage.dict()
            except Exception:
                pass
        if not token_usage:
            for attr in dir(usage):
                if not attr.startswith('_'):
                    try:
                        val = getattr(usage, attr)
                        if isinstance(val, (int, str, float, bool, dict, list)) or val is None:
                            token_usage[attr] = val
                    except Exception:
                        pass
        # Ensure standard fields are present
        for attr in ["prompt_token_count", "candidates_token_count", "total_token_count"]:
            val = getattr(usage, attr, None)
            if val is not None and attr not in token_usage:
                token_usage[attr] = val
    return token_usage


def _resolve_gemini_params(model_prefix):
    """
    Resolves model name, API key, and generation config from environment variables.

    Reads the following variables using get_env:
      {model_prefix}_MODEL   — required; Gemini model name
      {model_prefix}_API_KEY — required; Gemini API key
      {model_prefix}_CONFIG  — optional; JSON string of generation config

    Args:
        model_prefix (str): The prefix identifying the model group (e.g. "GEO", "IMAGE").

    Returns:
        tuple: (model: str, api_key: str, gen_config: dict)

    Raises:
        EnvironmentError: If MODEL or API_KEY variables are not set.
    """
    model_var = f"{model_prefix}_MODEL"
    api_key_var = f"{model_prefix}_API_KEY"
    config_var = f"{model_prefix}_CONFIG"

    model = get_env(model_var)
    if not model:
        raise EnvironmentError(f"Model variable '{model_var}' is not set in environment.")

    api_key = get_env(api_key_var)
    if not api_key:
        raise EnvironmentError(f"API Key variable '{api_key_var}' is not set.")

    config_str = get_env(config_var)

    gen_config = {}
    if config_str:
        try:
            gen_config = json.loads(config_str)
        except json.JSONDecodeError:
            print(f"Warning: Failed to parse {config_var} from environment.")

    return model, api_key, gen_config


def _extract_text(response):
    """
    Safely extracts and concatenates all text parts from a Gemini response.

    Handles multimodal responses where non-text parts (e.g. images) may also
    be present — only text parts are collected.

    Args:
        response: A Gemini generate_content response object.

    Returns:
        str: Concatenated text from all text parts, or empty string if none.
    """
    text_parts = []
    if response.candidates:
        for candidate in response.candidates:
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)
    return "".join(text_parts)


def _upload_file(client, file_path):
    """
    Uploads a local file to the Gemini Files API.

    Args:
        client (genai.Client): An initialized Gemini client.
        file_path (str): Absolute or relative path to the file to upload.

    Returns:
        File object: The uploaded file object with .name, .uri, .mime_type, .state attributes.

    Raises:
        FileNotFoundError: If the file does not exist at file_path.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_obj = client.files.upload(file=file_path)
    return file_obj


def _wait_for_file_active(client, file_obj):
    """
    Polls the Gemini Files API until the uploaded file reaches ACTIVE state.

    Files may be in PROCESSING state immediately after upload. This function
    waits (polling every 2 seconds) until the file is ready to use.

    Args:
        client (genai.Client): An initialized Gemini client.
        file_obj: The file object returned by _upload_file.

    Returns:
        File object: The updated file object in ACTIVE state.

    Raises:
        RuntimeError: If the file fails to process (state is not ACTIVE after processing).
    """
    while file_obj.state.name == "PROCESSING":
        time.sleep(2)
        file_obj = client.files.get(name=file_obj.name)

    if file_obj.state.name != "ACTIVE":
        raise RuntimeError(f"File {file_obj.name} failed to process. State: {file_obj.state.name}")

    return file_obj


def query_gemini(model_prefix, contents):
    """
    Sends a text prompt to a Gemini model and returns the response.

    Resolves all model parameters from environment variables using the given prefix.
    Supports optional system instructions embedded in the prompt and optional
    context caching for system instructions (controlled by _CONTEXT_CACHING env var).

    System instruction syntax (embed in prompt text):
        system_instruction===<your instruction text>===system_instruction

    Context caching:
        Set _CONTEXT_CACHING=TRUE in .env to enable. When enabled, the system
        instruction is cached under the display name "query_gemini_cache" with a
        24-hour TTL. Existing caches are reused if found.

    Args:
        model_prefix (str): Prefix for environment variable lookup (e.g. "GEO").
        contents (str): The prompt text to send to the model.

    Returns:
        dict: {
            "response_data": {"content_type": "json"|"text", "data": ...},
            "token_usage": {"prompt_token_count": int, "total_token_count": int, ..., "model": str}
        }

    Raises:
        EnvironmentError: If required model/API key env vars are not set.
        Exception: Propagates any API or network errors.
    """
    try:
        system_instruction = None

        # 1. Resolve Parameters
        model, api_key, gen_config = _resolve_gemini_params(model_prefix)

        # 2. Fetch Caching Setting (Always from _CONTEXT_CACHING)
        use_caching = str(get_env("_CONTEXT_CACHING")).upper() == "TRUE"

        # 3. Extract System Instruction from prompt if present
        pattern = r"system_instruction===(.*?)===system_instruction"
        match = re.search(pattern, contents, re.DOTALL)
        if match:
            system_instruction = match.group(1).strip()
            contents = re.sub(pattern, "", contents, flags=re.DOTALL).strip()

        # 4. Initialize Client
        client = get_gemini_client(api_key)

        generate_kwargs = {
            "model": model,
            "contents": contents
        }

        if system_instruction and "system_instruction" not in gen_config:
            gen_config["system_instruction"] = system_instruction

        # 5. Handle Context Caching
        if gen_config:
            if use_caching and "system_instruction" in gen_config:
                sys_inst = gen_config.pop("system_instruction")
                try:
                    print("Context caching is enabled. Searching for existing cache...")
                    existing_caches = list(client.caches.list())
                    cache_name = None
                    for c in existing_caches:
                        if getattr(c, "display_name", "") == "query_gemini_cache":
                            cache_name = c.name
                            print(f"Reusing existing cache: {cache_name}")
                            break

                    if not cache_name:
                        cache_model = model if "/" in model else f"models/{model}"
                        cache_config = {
                            "system_instruction": sys_inst,
                            "display_name": "query_gemini_cache",
                            "ttl": "86400s"
                        }
                        cache = client.caches.create(
                            model=cache_model,
                            config=cache_config
                        )
                        cache_name = cache.name
                        print(f"Created new cache: {cache_name}")

                    gen_config["cached_content"] = cache_name
                except Exception as e:
                    print(f"Warning: Context caching failed: {e}")
                    print("Falling back to standard un-cached request.")
                    gen_config["system_instruction"] = sys_inst

            generate_kwargs["config"] = gen_config

        # 6. Execute Request
        print(f"generate_kwargs: {generate_kwargs}\n\nOUTPUT:\n")
        response = client.models.generate_content(**generate_kwargs)

        response_text = _extract_text(response)
        response_data = parse_response_text(response_text)

        usage = getattr(response, "usage_metadata", None)
        token_usage = extract_token_usage(usage)
        token_usage["model"] = generate_kwargs.get("model")

        return {
            "response_data": response_data,
            "token_usage": token_usage,
            "metadata": {
                "finish_reason": response.candidates[0].finish_reason.name if response.candidates else "N/A",
                "safety_ratings": [
                    {"category": r.category.name, "probability": r.probability.name}
                    for r in response.candidates[0].safety_ratings
                ] if response.candidates and response.candidates[0].safety_ratings else []
            }
        }
    except Exception as e:
        raise e


def analyze_image(model_prefix, prompt, image_path):
    """
    Uploads an image and queries a Gemini model for a text analysis response.

    Uses the Gemini Files API to upload the image, waits for it to become active,
    then sends the prompt and image URI to the model.

    Args:
        model_prefix (str): Prefix for environment variable lookup (e.g. "GEO").
        prompt (str): The text prompt describing what to analyze in the image.
        image_path (str): Path to the local image file to upload and analyze.

    Returns:
        dict: {
            "response_data": {"content_type": "json"|"text", "data": ...},
            "token_usage": dict,
            "metadata": {
                "finish_reason": str,
                "safety_ratings": [{"category": str, "probability": str}, ...]
            }
        }

    Raises:
        FileNotFoundError: If image_path does not exist.
        EnvironmentError: If required model/API key env vars are not set.
        Exception: Propagates any API or processing errors.
    """
    try:
        # 1. Resolve Parameters
        model, api_key, gen_config = _resolve_gemini_params(model_prefix)
        client = get_gemini_client(api_key)

        # 2. Upload Image and wait for it to be ready
        file_obj = _upload_file(client, image_path)
        file_obj = _wait_for_file_active(client, file_obj)

        # 3. Call Gemini with prompt + image URI
        genai = import_genai()
        response = client.models.generate_content(
            model=model,
            contents=[
                prompt,
                genai.types.Part.from_uri(
                    file_uri=file_obj.uri,
                    mime_type=file_obj.mime_type
                )
            ],
            config=gen_config
        )

        response_text = _extract_text(response)
        token_usage = extract_token_usage(getattr(response, "usage_metadata", None))
        token_usage["model"] = model

        return {
            "response_data": parse_response_text(response_text),
            "token_usage": token_usage,
            "metadata": {
                "finish_reason": response.candidates[0].finish_reason.name if response.candidates else "N/A",
                "safety_ratings": [
                    {"category": r.category.name, "probability": r.probability.name}
                    for r in response.candidates[0].safety_ratings
                ] if response.candidates and response.candidates[0].safety_ratings else []
            }
        }
    except Exception as e:
        raise e


def edit_image(model_prefix, prompt, image_path, output_path):
    """
    Uses a multimodal Gemini model to edit or process an image and save the result.

    Uploads the source image via the Files API, sends it with the prompt to a
    model that supports image output (response_modalities: IMAGE), and saves
    the first image part found in the response to output_path.

    Note: Requires a Gemini model that supports image generation/editing output
    (e.g. gemini-2.5-flash-image or similar). Set IMAGE_MODEL in .env accordingly.

    Args:
        model_prefix (str): Prefix for environment variable lookup (e.g. "IMAGE").
        prompt (str): The editing instruction or description for the output image.
        image_path (str): Path to the source image file.
        output_path (str): Path where the edited output image will be saved.

    Returns:
        dict: {
            "response_data": {"content_type": "json"|"text", "data": ...},
            "token_usage": dict,
            "metadata": {
                "image_saved": bool,
                "output_path": str | None,
                "finish_reason": str,
                "safety_ratings": [{"category": str, "probability": str}, ...]
            }
        }

    Raises:
        FileNotFoundError: If image_path does not exist.
        EnvironmentError: If required model/API key env vars are not set.
        Exception: Propagates any API or processing errors.
    """
    try:
        # 1. Resolve Parameters
        model, api_key, gen_config = _resolve_gemini_params(model_prefix)
        client = get_gemini_client(api_key)

        # 2. Upload Image and wait for it to be ready
        file_obj = _upload_file(client, image_path)
        file_obj = _wait_for_file_active(client, file_obj)

        # 3. Ensure image output modality is requested.
        # If the user has not set response_modalities, default to both TEXT and IMAGE
        # so that any text returned by the model (e.g. image understanding) is captured.
        # If the user explicitly set response_modalities, honour their choice.
        if "response_modalities" not in gen_config:
            gen_config["response_modalities"] = ["TEXT", "IMAGE"]

        genai = import_genai()
        response = client.models.generate_content(
            model=model,
            contents=[
                prompt,
                genai.types.Part.from_uri(
                    file_uri=file_obj.uri,
                    mime_type=file_obj.mime_type
                )
            ],
            config=gen_config
        )

        # 4. Extract and save the image from the response
        image_found = False
        if response.candidates:
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data and part.inline_data.mime_type.startswith('image/'):
                            data = getattr(part.inline_data, 'data', None)
                            if data:
                                with open(output_path, "wb") as f:
                                    f.write(data)
                                image_found = True
                                break
                    if image_found:
                        break

        # 5. Return structured result
        response_text = _extract_text(response)
        token_usage = extract_token_usage(getattr(response, "usage_metadata", None))
        token_usage["model"] = model

        return {
            "response_data": parse_response_text(response_text),
            "token_usage": token_usage,
            "metadata": {
                "image_saved": image_found,
                "output_path": output_path if image_found else None,
                "finish_reason": response.candidates[0].finish_reason.name if response.candidates else "N/A",
                "safety_ratings": [
                    {"category": r.category.name, "probability": r.probability.name}
                    for r in response.candidates[0].safety_ratings
                ] if response.candidates and response.candidates[0].safety_ratings else []
            }
        }

    except Exception as e:
        raise e
