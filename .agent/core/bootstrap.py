# core/bootstrap.py
from core.execution_mode import ExecutionMode
from core.service_container import ServiceContainer

def bootstrap(mode: ExecutionMode) -> ServiceContainer:
    container = ServiceContainer()

    # 1. Initialize Shared Infrastructure Core (No Side Effects in Constructors)
    from models.model_service import ModelService
    from llm.ollama_client import OllamaClient
    from repository.file_manager import FileManager
    from context.assembler import ContextAssembler
    from context.prompt_builder import PromptBuilder

    import os
    core_dir = os.path.dirname(os.path.abspath(__file__))
    agent_dir = os.path.dirname(core_dir)
    repo_root = os.path.dirname(agent_dir)

    container.model_service = ModelService()
    container.llm = OllamaClient()
    container.file_manager = FileManager(repo_root)
    container.context_assembler = ContextAssembler()
    container.prompt_builder = PromptBuilder()

    # 2. Setup DB Schema lazily or safely
    try:
        from repository_intelligence.db.connection import Base, engine
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"[Bootstrap] Warning: Database schema check skipped: {e}")

    # 3. Register Cursor Services
    register_cursor_services(container)

    return container

def register_cursor_services(container: ServiceContainer):
    # Retrieve IDE Bridge and Span Locators
    from memory.state_manager import StateManager
    from execution.executor import Executor
    from ide.bridge import IDEBridge
    from editing.span_locator import SpanLocator

    container.state_manager = StateManager()
    container.executor = Executor(
        container.file_manager,
        state_manager=container.state_manager,
        model_service=container.model_service
    )
    container.ide_bridge = IDEBridge()
    container.span_locator = SpanLocator()
    
    # Preload model eagerly for low-latency cursor editing
    container.model_service.preload()

    # Eagerly run capability check on boot to warm the capabilities.json cache
    try:
        from validation.capability_registry import CapabilityRegistry
        CapabilityRegistry(repo_root=container.file_manager.root)
    except Exception as e:
        print(f"[Bootstrap] Warning: Eager capability registry check failed: {e}")
