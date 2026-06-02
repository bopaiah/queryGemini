# CLI Gemini Query Utility

A powerful, robust Command Line Interface (CLI) tool to query Google's Gemini models using the official `google-genai` SDK. This tool is useful to run iterations for prompt engineering or for testing prompt templates.

Developed by **Bopaiah Mekerira**.

---

## Features

- **Prompt Index Support**: Integrate seamlessly with `prompt_utils` to load named prompt templates from `prompt.idx`.
- **Flexible Template Variables**: Automatically substitute double-brace placeholders (e.g., `{{my_variable}}`) using variable maps.
- **Dynamic Variable Injection**: Supply variable overrides directly via the CLI as a JSON string.
- **File Inclusions**: Automatically resolves `{{file:filepath}}` syntax inside prompt files to stitch multiple files together.
- **Environment Aware**: Configurable via local `.env` files for easy management of API keys and default models.
- **Graceful CLI Experience**: Shows auto-help usage when executed without any parameters.
- **Model Listing**: Built-in option to query and list all available models using `--list`.

---

## Installation

1. Clone this repository or copy the directory.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Create a `.env` file in the same directory as the script with your API key and target model:

```env
# Your Google Gemini API Key
GEMINI_API_KEY=AIzaSy...

# Target Model Name (e.g., gemini-2.5-flash, gemini-3-flash-preview)
MODEL=gemini-3-flash-preview
```

---

## Usage

Run the utility without parameters to print the standard help message:
```bash
python query_gemini.py
```

### Examples

#### 1. Querying with a template from prompt.idx:
Loads the prompt template registered under the name `prompt2` in `prompt.idx`:
```bash
python query_gemini.py -p prompt2
```

#### 2. Querying with custom template arguments:
Supply arguments as a JSON string to dynamically override placeholders in your template:
```bash
python query_gemini.py -p prompt2 -a '{"CURRENT_DATE": "2026-06-02", "SEASON": "Summer"}'
```

#### 3. Overriding model and env path:
```bash
python query_gemini.py -p prompt2 --env .env --model gemini-2.5-flash
```

#### 4. Direct Prompt String:
```bash
python query_gemini.py "Explain the effect of el-nino on weather"
```

#### 5. List All Available Models:
```bash
python query_gemini.py --list
```

---

## License
Created by Bopaiah Mekerira. All rights reserved.
