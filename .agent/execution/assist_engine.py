# execution/assist_engine.py
import os
from context.context_builder import ContextBuilder
from inference.router import TaskType
from context.context_router import ContextBuilderEnum

class AssistEngine:
    """Stateless assistant explanation engine."""
    
    def __init__(self, runtime):
        self.runtime = runtime

    def handle(self, prompt: str, editor_state, on_progress=None) -> str:
        if on_progress:
            on_progress("status", "Assembling context for explanation...")

        builder = ContextBuilder(self.runtime.executor.retrieval_pipeline, self.runtime.state_manager)
        
        # Build mock state to hold runtime context for ContextBuilder
        class MockState:
            def __init__(self, rc):
                self.runtime_context = rc
        mock_state = MockState(editor_state)
        
        stage1_context = builder.build_planning_context(prompt, mock_state, mode="inline")
        s1_compressed = self.runtime.context.compressor.compress_chunks(stage1_context.retrieved_chunks)
        s1_text = ""
        for chunk in s1_compressed:
            s1_text += f"\nFILE: {chunk.get('file')}\nSYMBOL: {chunk.get('symbol')}\n{chunk.get('content')}\n"

        prompt1 = f"""You are an expert AI software engineer assistant.
Answer the user's question/assist request using the provided local context.

LOCAL CONTEXT:
{s1_text}

USER GOAL/QUESTION:
{prompt}
"""
        if on_progress:
            on_progress("status", "Generating explanation...")
            token_stream = self.runtime.llm.chat([
                {"role": "user", "content": prompt1}
            ], task_type=TaskType.CHAT, stream=True)
            full_response = []
            for token in token_stream:
                full_response.append(token)
                on_progress("token", token)
            response = "".join(full_response)
        else:
            response = self.runtime.llm.chat([
                {"role": "user", "content": prompt1}
            ], task_type=TaskType.CHAT)

        # Stage 2: Background enrichment
        from runtime.fast_path_router import FastPathRouter
        route_decision = FastPathRouter.route(prompt, editor_state)
        if route_decision.context_mode != ContextBuilderEnum.SELECTION:
            if on_progress:
                on_progress("status", "Performing background repository search...")
            stage2_context = builder.build_planning_context(prompt, mock_state, mode=route_decision.context_mode.value)
            
            s1_chunk_ids = {c.get("chunk_id") for c in stage1_context.retrieved_chunks}
            new_chunks = [c for c in stage2_context.retrieved_chunks if c.get("chunk_id") not in s1_chunk_ids]
            
            if new_chunks:
                if on_progress:
                    on_progress("token", "\n\n### Enriched Background Analysis\n")
                s2_compressed = self.runtime.context.compressor.compress_chunks(new_chunks)
                s2_text = ""
                for chunk in s2_compressed:
                    s2_text += f"\nFILE: {chunk.get('file')}\nSYMBOL: {chunk.get('symbol')}\n{chunk.get('content')}\n"
                
                prompt2 = f"""You are an expert AI software engineer assistant.
Enrich your previous explanation with the following newly retrieved background context.
Only explain new details, do not repeat what you already explained.

PREVIOUS EXPLANATION:
{response}

NEW REPOSITORY CONTEXT:
{s2_text}
"""
                if on_progress:
                    token_stream2 = self.runtime.llm.chat([
                        {"role": "user", "content": prompt2}
                    ], task_type=TaskType.CHAT, stream=True)
                    full_response2 = []
                    for token in token_stream2:
                        full_response2.append(token)
                        on_progress("token", token)
                    response += "\n\n### Enriched Background Analysis\n" + "".join(full_response2)
                else:
                    response2 = self.runtime.llm.chat([
                        {"role": "user", "content": prompt2}
                    ], task_type=TaskType.CHAT)
                    response += "\n\n### Enriched Background Analysis\n" + response2

        return response
