# editing/symbol_resolver.py
#
# Resolves a string symbol identifier into one or more SymbolHandle objects.

import os
from typing import List

class SymbolResolutionError(Exception):
    pass
from context.symbol_resolver import SymbolResolver as ContextResolver
from editing.symbol_handle import SymbolHandle

class SymbolResolutionError(Exception):
    """Raised when a symbol cannot be resolved in the database or AST and fallback is disabled."""
    pass

class SymbolResolver:
    def __init__(self, db_session=None, state_manager=None):
        self._inner = ContextResolver()
        self.db_session = db_session
        self.state_manager = state_manager

    def resolve(self, symbol_name: str, file_path: str = None, allow_fallback: bool = False) -> List[SymbolHandle]:
        """
        Resolves the symbol name. If not found in DB, attempts AST-based resolution or raises SymbolResolutionError.
        """
        # Determine execution mode from state_manager
        exec_mode = None
        if self.state_manager:
            try:
                state = self.state_manager.get_state()
                active_goal = getattr(state, "goal", "")
                if active_goal:
                    from runtime.fast_path_router import FastPathRouter
                    route_decision = FastPathRouter.route(active_goal)
                    exec_mode = route_decision.execution_mode
            except Exception as e:
                print(f"[SymbolResolver] Failed to determine execution mode: {e}")

        # For PATCH mode, never fallback. Only allow fallback in AGENT mode.
        from core.execution_mode import TaskIntentMode as ExecutionMode
        if exec_mode is not None:
            if exec_mode != ExecutionMode.AGENT:
                allow_fallback = False

        resolved_symbols = self._inner.resolve(symbol_name, session=self.db_session)
        
        # Filter by file path if provided
        if file_path and resolved_symbols:
            filtered = [s for s in resolved_symbols if s.file_path == file_path]
            if filtered:
                resolved_symbols = filtered
                
        handles = []
        for i, s in enumerate(resolved_symbols):
            handles.append(SymbolHandle(
                symbol_id=f"sym_{i}_{s.name}",
                fqn=symbol_name,
                kind=s.symbol_type or "unknown",
                file_path=s.file_path,
                start_line=s.start_line if s.start_line is not None else 1,
                end_line=s.end_line if s.end_line is not None else 1
            ))
            
        # Build fallback handle or raise exception if no symbols were resolved from database but file_path exists
            repo_root = getattr(self, "repo_root", None) or os.getcwd()
            full_path = os.path.abspath(os.path.join(repo_root, file_path))
            if os.path.exists(full_path):
                # Attempt to locate via dynamic AST parsing on the fly
                from editing.ast_locator import ASTLocator
                try:
                    locator = ASTLocator()
                    node_info = locator.find_symbol(full_path, symbol_name)
                    if node_info:
                        handles.append(SymbolHandle(
                            symbol_id=f"sym_ast_{symbol_name}",
                            fqn=symbol_name,
                            kind=node_info.node_type or "unknown",
                            file_path=file_path,
                            start_line=node_info.start_line,
                            end_line=node_info.end_line
                        ))
                except Exception as e:
                    print(f"[SymbolResolver] AST locator resolution failed: {e}")

                if not handles:
                    if not allow_fallback:
                        raise SymbolResolutionError(
                            f"Could not resolve symbol '{symbol_name}' in database or AST of '{file_path}'"
                        )
                    
                    try:
                        from ide.virtual_workspace import VirtualWorkspace
                        lines_count = len(VirtualWorkspace.get_instance().read_file(full_path).splitlines()) or 1
                    except Exception:
                        lines_count = 1
                        
                    handles.append(SymbolHandle(
                        symbol_id=f"sym_fallback_{symbol_name}",
                        fqn=symbol_name,
                        kind="fallback",
                        file_path=file_path,
                        start_line=1,
                        end_line=lines_count
                    ))
                
        return handles
