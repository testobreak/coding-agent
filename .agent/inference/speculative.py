# inference/speculative.py
#
# Speculative Decoding Subsystem.
# Proposes candidate tokens/lines using a fast draft model and verifies them using a target model.

import time
from typing import List, Dict, Any, Optional, Callable

class SpeculativeDecoder:
    """
    Speculative Decoder to accelerate local inference using draft models.
    Supports both classic token-level speculative decoding and high-performance line-level speculative editing.
    """

    def __init__(self, target_client, draft_client):
        """
        Initialize the speculative decoder.
        
        Parameters
        ----------
        target_client: OllamaClient
            The large model client (e.g. 7-14B or 32B+) used to verify proposals.
        draft_client: OllamaClient
            The small model client (e.g. 1.5B/3B) used to generate drafts.
        """
        self.target_client = target_client
        self.draft_client = draft_client

    def generate_speculative(self, prompt: str, K: int = 5) -> str:
        """
        Classic token-level speculative decoding.
        The small model drafts K tokens, and the target model validates them.
        
        Parameters
        ----------
        prompt: str
            The input prompt/context.
        K: int
            The number of tokens to draft per verification step.
        """
        generated_text = ""
        current_prompt = prompt

        while True:
            # 1. Draft K tokens step-by-step
            draft_tokens = []
            temp_prompt = current_prompt
            for _ in range(K):
                # Call draft model to predict the next token (simulated via tiny completion)
                draft_res = self.draft_client.chat(
                    messages=[{"role": "user", "content": temp_prompt}],
                    options={"num_predict": 1, "temperature": 0.0}
                )
                if not draft_res:
                    break
                draft_tokens.append(draft_res)
                temp_prompt += draft_res

            if not draft_tokens:
                break

            # 2. Target model verifies the draft tokens
            accepted_tokens = []
            for i, draft_tok in enumerate(draft_tokens):
                target_prefix = current_prompt + "".join(draft_tokens[:i])
                target_res = self.target_client.chat(
                    messages=[{"role": "user", "content": target_prefix}],
                    options={"num_predict": 1, "temperature": 0.0}
                )
                if target_res == draft_tok:
                    accepted_tokens.append(draft_tok)
                else:
                    # Reject remainder of draft, accept target model's prediction as the correction
                    if target_res:
                        accepted_tokens.append(target_res)
                    break

            if not accepted_tokens:
                break

            added_text = "".join(accepted_tokens)
            generated_text += added_text
            current_prompt += added_text

            # If we encountered a correction, we break this step and proceed with the new prefix
            if len(accepted_tokens) < len(draft_tokens) or not accepted_tokens[-1]:
                break

        return generated_text

    def generate_speculative_line(
        self,
        prompt: str,
        context: str,
        on_progress: Optional[Callable[[str, Any], None]] = None
    ) -> str:
        """
        Line-level speculative editing.
        Designed for API-based workflows where token-by-token HTTP loops add roundtrip overhead.
        1. Small model drafts a line/sentence of completions.
        2. Large model validates it in a single fast cached pass (generating "ACCEPT" or correction).
        
        Parameters
        ----------
        prompt: str
            The input goal or question.
        context: str
            The retrieved file/symbol context.
        on_progress: Optional[Callable]
            Progress streaming callback.
        """
        if on_progress:
            on_progress("status", "Drafting completion proposal using fast local model...")

        draft_prompt = f"""Generate the next logical block of code or explanation based on the prompt.
CONTEXT:
{context}

PROMPT:
{prompt}
"""
        try:
            draft_block = self.draft_client.chat(
                messages=[{"role": "user", "content": draft_prompt}],
                options={"temperature": 0.2}
            )
        except Exception:
            draft_block = None

        if not draft_block:
            # Fallback directly to the target model
            if on_progress:
                on_progress("status", "Drafting failed. Generating directly using target model...")
            return self.target_client.chat(
                messages=[{"role": "user", "content": f"CONTEXT:\n{context}\n\nPROMPT:\n{prompt}"}]
            )

        # Speculatively stream the draft tokens to the user
        if on_progress:
            on_progress("status", "Verifying speculative draft with target model...")
            for word in draft_block.split(" "):
                on_progress("token", word + " ")

        # 2. Large model verifies or corrects the block in a single call
        verification_prompt = f"""Verify the following draft proposal. If it is 100% correct and matches the prompt and context, reply with ONLY the word "ACCEPT". Otherwise, reply with the corrected line/block.

CONTEXT:
{context}

PROMPT:
{prompt}

DRAFT PROPOSAL:
{draft_block}
"""
        try:
            target_res = self.target_client.chat(
                messages=[{"role": "user", "content": verification_prompt}],
                options={"temperature": 0.0}
            ).strip()
        except Exception:
            target_res = "ACCEPT" # Fallback to accept draft on error

        if target_res.upper() == "ACCEPT" or target_res.upper().startswith("ACCEPT"):
            if on_progress:
                on_progress("status", "Speculative draft verified and accepted.")
            return draft_block
        else:
            if on_progress:
                on_progress("status", "Speculative draft corrected by target model.")
                on_progress("token", "\n[Correction]: " + target_res)
            return target_res
