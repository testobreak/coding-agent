# execution/executor.py
#
# Services Coordinator — exposing core developer/editor utility subsystems.
# Does NOT contain planning, reflection, criticism, or autonomous loop execution.

import os
from context.assembler import ContextAssembler
from context.prompt_builder import PromptBuilder
from execution.validators import ExecutionValidator
from repository.git_manager import GitManager
from repository.patch_manager import PatchManager
from repository.write_manager import WriteManager
from repository.patch_generator import PatchGenerator
from execution.test_runner import TestRunner
from execution.compile_validator import CompileValidator
from analysis.impact_analyzer import ImpactAnalyzer
from llm.ollama_client import OllamaClient


class Executor:
    """
    Lightweight services coordinator exposing core developer/editor utility subsystems.
    Does NOT contain planning, reflection, criticism, or autonomous loop execution.
    """
    def __init__(self, file_manager, state_manager=None, model_service=None):
        self.file_manager = file_manager
        self.state_manager = state_manager
        self.assembler = ContextAssembler()
        self.prompt_builder = PromptBuilder()

        # Semantic retrieval
        from retrieval.service import RetrievalFacade
        self.retrieval_facade = RetrievalFacade.get_instance(model_service=model_service)
        self.retriever = self.retrieval_facade.retriever
        self.retrieval_pipeline = self.retrieval_facade.pipeline

        self.validator = ExecutionValidator()
        self.git = GitManager(file_manager.root)
        self.patch_manager = PatchManager(file_manager.root)
        self.writer = WriteManager(file_manager.root)
        self.patch_generator = PatchGenerator()
        self.llm = OllamaClient()
        self.tests = TestRunner(file_manager.root)
        self.compile_validator = CompileValidator(repo_root=file_manager.root)
        self.impact_analyzer = ImpactAnalyzer(repo_root=file_manager.root)
