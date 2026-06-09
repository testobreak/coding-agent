# editing/patch_generator.py
#
# Generates localized SEARCH/REPLACE patches for specific symbol AST nodes.

import json
from editing.ast_locator import ASTNodeInfo
from llm.ollama_client import OllamaClient

class PatchGenerator:
    def __init__(self, llm=None):
        self.llm = llm or OllamaClient()

    def generate_patch(
        self,
        symbol_info: ASTNodeInfo,
        instruction: str,
        file_path: str,
        execution_context: str = "",
        edit_request = None
    ) -> str:
        system_prompt = """You are a repository-aware software engineer specializing in surgical code modifications.
You are given the source code of a specific target symbol (e.g., class or method) and must modify it to address the user's instruction.

To apply modifications, you must return a Search-and-Replace block of this format:
<<<<<<< SEARCH
[exact original code snippet within the symbol to be modified]
=======
[new modified code replacement]
>>>>>>> REPLACE

Or, if replacing the entire symbol is cleaner, target the entire original symbol:
<<<<<<< SEARCH
[entire original symbol code]
=======
[entire modified symbol code]
>>>>>>> REPLACE

Rules:
1. Return ONLY the Search-and-Replace block. Do not include markdown code fences (like ```diff or ```), explanations, or conversational text.
2. Match the SEARCH block EXACTLY, character-for-character, including indentation and spacing.
"""

        dependencies_str = ""
        if edit_request and edit_request.dependencies:
            dependencies_str = "\nDEPENDENCIES AND USAGES:\n" + "\n".join(edit_request.dependencies) + "\n"

        user_prompt = f"""TASK/INSTRUCTION:
{instruction}

TARGET FILE:
{file_path}

TARGET SYMBOL NAME:
{symbol_info.name} (type: {symbol_info.node_type})

EXECUTION CONTEXT:
{execution_context}
{dependencies_str}
ORIGINAL SYMBOL SOURCE CODE:
{symbol_info.content}

OUTPUT SEARCH/REPLACE PATCH:
"""

        response = self.llm.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        return response.strip()
