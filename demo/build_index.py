"""Build demo/web/index.json for the in-browser demo.

The browser cannot run Python, so the ingest half of the pipeline runs
here - the real loaders, the real heading-aware chunker, the real
embedding model - and its output is shipped as data. The query half is
re-implemented in demo/web/search.js; the constants it needs are written
into the index from the Python source of truth rather than copied by hand.

    python demo/build_index.py            # writes demo/web/index.json
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import rag  # noqa: E402
from pipeline import chunking, rerank  # noqa: E402

DOCS = os.path.join(ROOT, "eval", "fixtures", "docs")
OUT = os.path.join(ROOT, "demo", "web", "index.json")
GOLDEN_IN = os.path.join(ROOT, "eval", "fixtures", "golden_set.yaml")
# For demo/check_search.mjs; Node has no YAML parser built in.
GOLDEN_OUT = os.path.join(ROOT, "demo", "golden.json")


def main():
    paths = sorted(
        os.path.join(DOCS, name) for name in os.listdir(DOCS)
        if not name.startswith(".")
        and os.path.splitext(name)[1].lower() in rag.LOADABLE_EXTENSIONS
    )
    chunks = []
    for path in paths:
        chunks.extend(chunking.split_documents(rag.load_file(path)))

    texts = [c.page_content for c in chunks]
    vectors = rag.get_embeddings().embed_documents(texts)

    index = {
        # Read by the browser so the two halves cannot silently disagree.
        "config": {
            "embedding_model": "Xenova/" + rag.EMBEDDING_MODEL.split("/")[-1],
            "rerank_model": "Xenova/" + rerank.RERANK_MODEL.split("/")[-1],
            "k": rag.compute_k(len(chunks)),
            "rrf_c": 60,  # LangChain EnsembleRetriever default
            "weights": [0.5, 0.5],
            "rerank_top_n": rerank.RERANK_TOP_N,
            "min_score": rag.OFFLINE_MIN_SCORE,
            "max_passages": rag.OFFLINE_MAX_PASSAGES,
            "passage_chars": rag.OFFLINE_PASSAGE_CHARS,
        },
        "files": sorted({os.path.basename(p) for p in paths}),
        "chunks": [
            {
                "id": i,
                "source": os.path.basename(c.metadata["source"]),
                "section": c.metadata.get("section", ""),
                "text": c.page_content,
                "embedding": [round(x, 5) for x in v],
            }
            for i, (c, v) in enumerate(zip(chunks, vectors))
        ],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(index, f, separators=(",", ":"))
    import yaml
    with open(GOLDEN_IN) as f, open(GOLDEN_OUT, "w") as out:
        json.dump(yaml.safe_load(f), out, indent=1)

    print(f"Wrote {OUT}: {len(chunks)} chunks from {len(paths)} files, "
          f"{os.path.getsize(OUT) // 1024} KB")


if __name__ == "__main__":
    main()
