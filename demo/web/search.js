// The query half of the pipeline, in the browser.
//
// Mirrors rag.py's retrieve -> fuse -> rerank -> offline answer path. The
// constants come from index.json, which demo/build_index.py writes from the
// Python source, so they are never copied by hand. Where this file has to
// reimplement behaviour (BM25, fusion), the Python it mirrors is named.

const TRANSFORMERS = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.7.1";

// search/keyword.py: FTS5 unicode61 with URL/email punctuation as separators,
// so in effect "runs of letters and digits", lower-cased.
export function tokenize(text) {
  return (text.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "")
    .match(/[\p{L}\p{N}]+/gu)) || [];
}

// keyword.to_match_expression: punctuation becomes a space, one-letter words
// are dropped, the rest are OR-ed.
function queryTerms(question) {
  const words = question.replace(/[^\p{L}\p{N}\s]/gu, " ").split(/\s+/).filter((w) => w.length > 1);
  return [...new Set(words.flatMap(tokenize))];
}

class Bm25 {
  // FTS5's bm25(): k1 = 1.2, b = 0.75, and an IDF floored just above zero so
  // a term present in most documents still counts a little.
  constructor(docs) {
    this.docs = docs.map((d) => {
      const tf = new Map();
      for (const t of tokenize(d.text)) tf.set(t, (tf.get(t) || 0) + 1);
      return { id: d.id, tf, len: [...tf.values()].reduce((a, b) => a + b, 0) };
    });
    this.avgdl = this.docs.reduce((a, d) => a + d.len, 0) / this.docs.length;
    this.df = new Map();
    for (const d of this.docs) for (const t of d.tf.keys()) this.df.set(t, (this.df.get(t) || 0) + 1);
  }

  // `allowed` filters candidates, not statistics: IDF stays corpus-wide, as
  // it does in FTS5 when the Python index filters by group.
  search(question, k, allowed) {
    const terms = queryTerms(question);
    const n = this.docs.length;
    const scored = [];
    for (const d of this.docs) {
      if (allowed && !allowed(d.id)) continue;
      let score = 0;
      for (const t of terms) {
        const f = d.tf.get(t);
        if (!f) continue;
        const df = this.df.get(t);
        const idf = Math.max(Math.log((n - df + 0.5) / (df + 0.5)), 1e-6);
        score += idf * (f * 2.2) / (f + 1.2 * (1 - 0.75 + 0.75 * d.len / this.avgdl));
      }
      if (score > 0) scored.push({ id: d.id, score });
    }
    return scored.sort((a, b) => b.score - a.score).slice(0, k).map((s) => s.id);
  }
}

// LangChain EnsembleRetriever.weighted_reciprocal_rank: each list adds
// weight / (rank + c) with rank starting at 1; ties keep first-seen order.
function fuse(lists, weights, c) {
  const scores = new Map();
  lists.forEach((ids, i) => ids.forEach((id, rank) => {
    scores.set(id, (scores.get(id) || 0) + weights[i] / (rank + 1 + c));
  }));
  return [...scores.entries()].sort((a, b) => b[1] - a[1]).map(([id]) => id);
}

export class Engine {
  constructor(index) {
    this.config = index.config;
    this.chunks = index.chunks;
    this.bm25 = new Bm25(index.chunks);
    this.embedder = null;
    this.reranker = null;
  }

  // Embedder first, then the reranker. `lib` is the Transformers.js module;
  // the browser loads it from the CDN, the CI check passes in its own copy
  // because Node cannot import from a URL.
  async load(onProgress, lib) {
    const { pipeline, AutoTokenizer, AutoModelForSequenceClassification } = lib ?? await import(TRANSFORMERS);
    const progress = (model) => (p) => {
      if (p.status === "progress" && p.total) onProgress?.(model, p.loaded, p.total);
    };
    this.embedder = await pipeline("feature-extraction", this.config.embedding_model,
      { dtype: "q8", progress_callback: progress("embedder") });
    onProgress?.("embedder-ready");
    this.rerankerReady = (async () => {
      const id = this.config.rerank_model;
      const tokenizer = await AutoTokenizer.from_pretrained(id);
      const model = await AutoModelForSequenceClassification.from_pretrained(id,
        { dtype: "q8", progress_callback: progress("reranker") });
      this.reranker = { tokenizer, model };
      onProgress?.("reranker-ready");
    })();
    return this.rerankerReady;
  }

  async embed(text) {
    const out = await this.embedder(text, { pooling: "mean", normalize: true });
    return out.data;
  }

  async score(question, chunks) {
    const { tokenizer, model } = this.reranker;
    const inputs = tokenizer(new Array(chunks.length).fill(question),
      { text_pair: chunks.map((c) => c.text), padding: true, truncation: true });
    const { logits } = await model(inputs);
    return Array.from(logits.data);
  }

  // `allow` is the set of source files the searcher may open. It is applied
  // before retrieval, as the Python app's group filter is, so a file outside
  // it can never be ranked, scored or quoted.
  async search(question, { allow } = {}) {
    const cfg = this.config;
    const t = performance.now();
    const timings = {};
    const allowed = allow ? (id) => allow.has(this.chunks[id].source) : null;

    const q = await this.embed(question);
    const vector = this.chunks
      .filter((c) => !allowed || allowed(c.id))
      .map((c) => ({ id: c.id, sim: c.embedding.reduce((s, x, i) => s + x * q[i], 0) }))
      .sort((a, b) => b.sim - a.sim).slice(0, cfg.k).map((s) => s.id);
    const keyword = this.bm25.search(question, cfg.k, allowed);
    timings.retrieve = performance.now() - t;

    const fused = fuse([vector, keyword], cfg.weights, cfg.rrf_c);

    let ranked = fused.map((id) => ({ id, score: null }));
    const reranked = Boolean(this.reranker);
    if (reranked) {
      const t2 = performance.now();
      const candidates = fused.map((id) => this.chunks[id]);
      const scores = await this.score(question, candidates);
      ranked = fused.map((id, i) => ({ id, score: scores[i] }))
        .sort((a, b) => b.score - a.score).slice(0, cfg.rerank_top_n);
      timings.rerank = performance.now() - t2;
    }

    // rag.ExtractiveAnswerChain: without a model there is nothing to say "I
    // don't know", so a passage must clear the reranker threshold to count.
    const passages = ranked
      .filter((r) => r.score === null || r.score >= cfg.min_score)
      .slice(0, cfg.max_passages)
      .map((r) => ({ ...r, chunk: this.chunks[r.id] }));

    timings.total = performance.now() - t;
    return { vector, keyword, fused, ranked, passages, reranked, timings };
  }
}
