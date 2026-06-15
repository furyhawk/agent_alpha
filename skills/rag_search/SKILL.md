---
name: rag-search
description: "Search ingested documents using vector retrieval. Use this when the user asks about information that may be in uploaded documents (PDFs, DOCX, TXT, MD files)."
tags: [rag, retrieval, documents, search]
version: "1.0.0"
---

# RAG Search

Retrieves relevant document chunks from the vector database using semantic search.
Results include the chunk content, relevance score, source filename, and page number.

## When to use

- The user asks a question about documents they've uploaded
- The user wants to find information across ingested files
- The user references "my documents", "the PDF", "the uploaded file", etc.

## How it works

1. The query is embedded using the configured embedding model
2. Milvus performs a cosine similarity search against all document chunks
3. Top results are returned with content, score, and source metadata

## Example

```
User: "What does the report say about revenue growth?"
Agent: [calls rag_search(query="revenue growth") → gets relevant chunks]
Agent: "Based on the documents, the revenue grew by 15% in Q3..."
```
