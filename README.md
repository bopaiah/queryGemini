# queryGemini — Gemini Query & Prompt Utility

A modular Python toolkit for querying Google's Gemini models via CLI or as a library.
Supports named prompt templates, dynamic variable injection, image analysis, image editing,
and seamless local/GCP environment configuration.

Developed by **Bopaiah Mekerira**.

---

## Project Structure

```
queryGemini/
├── query_gemini.py      # CLI entry point — query Gemini from the command line
├── gemini_utils.py      # Core Gemini API utilities (text, image analysis, image editing)
├── prompt_utils.py      # Prompt loader — resolves templates, variables, and file inclusions
├── env_utils.py         # Environment resolver — .env, GCP Secret Manager, caching
├── prompts/
│   ├── prompt.idx       # Prompt index (CSV): maps prompt names to files
│   ├── *.txt            # Prompt template files
│   └── *.txt            # Prompt-specific env/args files
├── .env                 # Local configuration (API keys, model names, paths)
├── requirements.txt     # Python dependencies
└── README.md
```

---

## Features

- **Named Prompt Templates**: Register prompts in `prompt.idx` and load them by name.
- **Dynamic Variable Substitution**: Use `{{KEY}}` placeholders in prompt files; supply values from env files or at call time via JSON.
- **File Inclusions**: Compose large prompts from multiple files using `{{file:./path.txt}}` syntax.
- **Image Analysis**: Upload images and query Gemini for text descriptions or structured analysis.
- **Image Editing**: Use multimodal Gemini models to edit images and save the output.
- **Environment-Aware**: Resolves config from `.env` locally, or GCP Secret Manager in production (`PROD_ENV=TRUE`).
- **Context Caching**: Optional system instruction caching for repeated queries (`_CONTEXT_CACHING=TRUE`).
- **Model Listing**: Built-in `--list` option to enumerate all available Gemini models.

---

## Installation

1. Clone this repository or copy the directory.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration (`.env`)

Create a `.env` file in the project root. Key variables:

```env
# Gemini API Key
GEMINI_API_KEY=AIzaSy...

# Default model for query_gemini.py CLI
MODEL=gemini-2.5-flash

# Prompt index file location (relative to project root)
_PROMPT_IDX_PATH=prompts/prompt.idx

# GEO prefix — used by gemini_utils query_gemini()
GEO_API_KEY={{GEMINI_API_KEY}}
GEO_MODEL=gemini-2.5-flash
GEO_CONFIG={"temperature": 0.1, "top_p": 0.95, "max_output_tokens": 8192}

# IMAGE prefix — used by gemini_utils analyze_image() / edit_image()
IMAGE_API_KEY={{GEMINI_API_KEY}}
IMAGE_MODEL=gemini-2.5-flash-image
IMAGE_CONFIG={"response_modalities": ["IMAGE"]}

# Feature flags
_CONTEXT_CACHING=FALSE
PROD_ENV=FALSE
DEBUG=FALSE

# GCP (for production Secret Manager use)
_GOOGLE_CLOUD_PROJECT=your-gcp-project-id
```

> Values can reference other variables using `{{KEY}}` syntax (e.g. `GEO_API_KEY={{GEMINI_API_KEY}}`).

---

## `prompt.idx` Format

The prompt index is a CSV file with a required header row:

```
prompt_name, prompt_filepath, env_filepath
prompt2,     ./prompt_file.txt
img_edit,    ./img_prompt.txt,  ./img_args.txt
```

| Column          | Required | Description |
|-----------------|----------|-------------|
| `prompt_name`   | Yes      | Unique key used to look up the prompt |
| `prompt_filepath` | Yes    | Path to the prompt text file (relative to `prompt.idx`) |
| `env_filepath`  | No       | Path to a prompt-specific args/env file (omit or leave blank if not needed) |

- If `env_filepath` is **blank or absent**: no env file is loaded (silently skipped).
- If `env_filepath` is **specified but the file does not exist**: a `FileNotFoundError` is raised.

---

## Prompt File Syntax

### Variable placeholders
```
The weather in {{CITY}} on {{CURRENT_DATE}} is {{WEATHER}}.
```
Values are supplied from the associated env file or `json_input` overrides.

### File inclusions
```
{{file:./shared_header.txt}}

Main prompt content here...
```
The referenced file's content is inlined at that position.

### System instructions
```
system_instruction===You are a helpful weather assistant.===system_instruction

What is the weather forecast for {{CITY}}?
```
The system instruction block is extracted and passed as the model's system instruction.

---

## CLI Usage (`query_gemini.py`)

```bash
python query_gemini.py [prompt] [-p PROMPT_NAME] [-a JSON_ARGS] [--model MODEL] [--env PATH] [--list]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `prompt` | Raw prompt string to send directly to the model |
| `-p`, `--prompt-name` | Name of a prompt template in `prompt.idx` |
| `-a`, `--args` | JSON string of variables to substitute into the template |
| `--model` | Gemini model name (overrides `MODEL` in `.env`) |
| `--env` | Path to `.env` file (default: `./.env`) |
| `--list` | List all available Gemini models and exit |

### Examples

```bash
# Raw prompt
python query_gemini.py "Explain the effect of el-nino on weather"

# Named template
python query_gemini.py -p prompt2

# Named template with variable overrides
python query_gemini.py -p prompt2 -a '{"CURRENT_DATE": "2026-06-02", "SEASON": "Summer"}'

# Override model and env file
python query_gemini.py -p prompt2 --env .env --model gemini-2.5-flash

# List available models
python query_gemini.py --list
```

---

## Library Usage

### `prompt_utils.getPrompt`

```python
from prompt_utils import getPrompt

# Load a prompt by name (variables from its env file)
prompt_text = getPrompt("prompt2")

# Load with runtime variable overrides
prompt_text = getPrompt("prompt2", {"CITY": "Tokyo", "SEASON": "Winter"})

# Also accepts a JSON string
prompt_text = getPrompt("prompt2", '{"CITY": "Tokyo"}')
```

### `gemini_utils.query_gemini`

```python
from gemini_utils import query_gemini

result = query_gemini("GEO", prompt_text)
print(result["response_data"]["data"])   # text or parsed JSON
print(result["token_usage"])
```

### `gemini_utils.analyze_image`

```python
from gemini_utils import analyze_image

result = analyze_image("GEO", "Describe this image in detail.", "face.jpg")
print(result["response_data"]["data"])
```

### `gemini_utils.edit_image`

```python
from gemini_utils import edit_image

result = edit_image("IMAGE", "Add a sunset background", "face.jpg", "face_edited.jpg")
print(result["metadata"]["image_saved"])   # True if image was saved
```

### `env_utils.get_env`

```python
from env_utils import get_env

api_key = get_env("GEMINI_API_KEY")
project_root = get_env("PROJECT_ROOT")
```

---

## Module Reference

### `env_utils.py`
| Function | Description |
|----------|-------------|
| `get_env(name, config_json=None)` | Resolve a variable from config, cache, Secret Manager, or `.env` |
| `get_project_root()` | Return the absolute project root path (ends with `/`) |
| `clear_env_cache()` | Clear the in-memory variable cache |

### `prompt_utils.py`
| Function | Description |
|----------|-------------|
| `getPrompt(prompt_name, json_input=None)` | Load and return a fully resolved prompt string |
| `parse_idx_line(line)` | Parse a single `prompt.idx` line into `(name, prompt_path, env_path)` |
| `parse_env_file(filepath)` | Parse a prompt-specific env/args file into a dict |
| `resolve_file_inclusions(content, base_dir)` | Resolve `{{file:...}}` inclusions in prompt text |
| `clear_caches()` | Clear all prompt loader in-memory caches |

### `gemini_utils.py`
| Function | Description |
|----------|-------------|
| `get_gemini_client(api_key, api_version)` | Create a Gemini API client |
| `list_gemini_models(api_key)` | List all available Gemini models |
| `query_gemini(model_prefix, contents)` | Send a text prompt and return response + token usage |
| `analyze_image(model_prefix, prompt, image_path)` | Upload image and get text analysis |
| `edit_image(model_prefix, prompt, image_path, output_path)` | Upload image, edit it, save result |
| `parse_response_text(response_text)` | Parse response into `{"content_type", "data"}` envelope |
| `extract_token_usage(usage)` | Extract token counts from response metadata |

---

## Dependencies

```
google-genai==2.7.0
google-cloud-secret-manager==2.29.0
python-dotenv==1.2.2
Pillow
```

Install with:
```bash
pip install -r requirements.txt
```

---

## License

Created by Bopaiah Mekerira. All rights reserved.
