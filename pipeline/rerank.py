"""Cross-encoder reranking.

Retrieval is tuned for recall (wide k, two retrievers); the reranker turns
that into precision. A cross-encoder reads the question and each chunk
together, which is far better at "does this chunk answer this" than the
bi-encoder similarity that ranked it. Keeping only the top N is what lets
k stay wide without the prompt - and the per-question cost - growing
with it.

Runs locally on CPU like the embeddings; no document text leaves the box.
"""
import os

# MiniLM is English-only. For a share with Hindi or Gujarati documents use
# BAAI/bge-reranker-v2-m3 (multilingual, ~2GB, noticeably slower on CPU).
RERANK_MODEL = os.environ.get("RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANK_TOP_N = int(os.environ.get("RAG_RERANK_TOP_N", 10))
RERANK_ENABLED = os.environ.get("RAG_RERANK", "1") != "0"


class Reranker:
    def __init__(self, model_name=RERANK_MODEL, top_n=RERANK_TOP_N, model=None):
        self.model_name = model_name
        self.top_n = top_n
        self._model = model  # injectable for tests

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query, docs):
        if len(docs) <= 1:
            return list(docs)
        scores = self.model.predict([(query, d.page_content) for d in docs])
        ranked = sorted(zip(docs, scores), key=lambda pair: float(pair[1]), reverse=True)
        kept = []
        for doc, score in ranked[: self.top_n]:
            doc.metadata["rerank_score"] = round(float(score), 4)
            kept.append(doc)
        return kept


def get_reranker():
    return Reranker() if RERANK_ENABLED else None
