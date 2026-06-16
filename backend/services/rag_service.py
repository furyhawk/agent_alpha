from pydantic_ai.tools import Tool
from typing import List

# These are imported from the existing skills structure
try:
    from skills.rag_search.search import rag_search, rag_search_by_document, rag_list_collections
except ImportError:
    # Fallback if the package isn't installed but we want to maintain the code structure
    pass

class RagService:
    """Handles RAG tool construction."""

    def get_rag_tools(self) -> List[Tool]:
        """Builds and returns RAG search tools for document retrieval."""
        return [
            Tool(rag_search, name="rag_search"),
            Tool(rag_search_by_document, name="rag_search_by_document"),
            Tool(rag_list_collections, name="rag_list_collections"),
        ]
