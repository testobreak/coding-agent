# repository/context_builder.py
"""Repository Context Builder

This module provides a thin wrapper around the existing heavy ``ContextBuilder``
implementation. It isolates the repository‑wide context assembly logic so that
the rest of the system can invoke it only when the ``ContextRouter`` determines
that a full‑repo context is required.

The class mirrors the public API of ``ContextBuilder`` that is used by the
autonomous agent engine, but it lives in the ``repository`` package to make the
dependency graph clearer and to avoid circular imports.
"""

from typing import Optional

# Import the existing heavy‑weight builder. It lives in ``context.context_builder``.
from context.context_builder import ContextBuilder, ContextRadius


class RepositoryContextBuilder:
    """Facade for building a full repository‑wide ``ContextPackage``.

    Parameters
    ----------
    retrieval_pipeline: Any
        The retrieval pipeline used by the original ``ContextBuilder``.
    state_manager: Optional[Any]
        Optional state manager – the original builder accepts this for storing
        intermediate state.
    """

    def __init__(self, retrieval_pipeline, state_manager: Optional[object] = None):
        # The heavy ``ContextBuilder`` does all the heavy lifting.
        self._builder = ContextBuilder(retrieval_pipeline, state_manager)

    def build_planning_context(
        self,
        query: str,
        state,
        radius: Optional[ContextRadius] = None,
        mode: Optional[str] = None,
        **kwargs
    ):
        """Delegate to the underlying ``ContextBuilder``.

        This method forwards the call to ``ContextBuilder.build_planning_context``
        and returns the resulting ``ContextPackage``.
        """
        return self._builder.build_planning_context(
            query, state, radius=radius, mode=mode, **kwargs
        )
