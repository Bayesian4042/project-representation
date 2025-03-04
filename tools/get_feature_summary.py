import os
import openai
from typing import Dict, List

from tools.get_app_folder_dependencies import get_app_folder_dependencies

openai.api_key = os.environ.get("OPENAI_API_KEY")

def read_file_content(file_path: str) -> str:
    """Safely read text from a file. Return an empty string on error."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return ""

def generate_feature_summary(file_list: List[str]) -> str:
    """
    Given a list of file paths, read their contents and send them to an LLM
    to generate a summary of the feature they collectively implement.
    """
    code_snippets = []
    for fp in file_list:
        content = read_file_content(fp)
        if content:
            code_snippets.append(f"--- FILE: {fp}\n{content}\n")

    combined_code = "\n".join(code_snippets)

    messages = [
        {"role": "system", "content": "You are a helpful AI that summarizes code."},
        {
            "role": "user",
            "content": (
                "You are given several TypeScript/TSX files from a Next.js project. "
                "Please describe the feature they collectively implement, including:\n"
                "- The main functionality\n"
                "- Any important components\n"
                "- How they work together\n\n"
                f"Here are the files:\n{combined_code}"
            ),
        },
    ]

    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return "Error or no response from LLM."
