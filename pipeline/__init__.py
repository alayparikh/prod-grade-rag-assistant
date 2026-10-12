"""Query-pipeline stages that sit around the core engine in rag.py.

Each module here is one stage (tracing, reranking, grading, caching,
chunking, health) with no import of rag.py, so the engine can depend on
them without a cycle and each can be tested on its own.
"""
