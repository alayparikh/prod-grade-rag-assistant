// Runs the golden set through the browser's search code (demo/web/search.js)
// so the JavaScript copy of the query pipeline cannot drift from the Python
// one unnoticed. CI fails if this exits non-zero.
//
//   python demo/build_index.py                      # writes index.json + golden.json
//   npm install --prefix demo/.node @huggingface/transformers@3.7.1
//   node demo/check_search.mjs
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { Engine } from "./web/search.js";

const require = createRequire(new URL("./.node/", import.meta.url));
// Node resolves the package's CommonJS build; its exports sit on `default`.
const mod = await import(require.resolve("@huggingface/transformers"));
const lib = mod.pipeline ? mod : mod.default;

const index = JSON.parse(readFileSync(new URL("./web/index.json", import.meta.url)));
const golden = JSON.parse(readFileSync(new URL("./golden.json", import.meta.url)));

// Cases offline search cannot pass by design: there is no model to count,
// to resolve "they" in a follow-up, or to notice that a resume about Jane
// says nothing about her salary. The Python --live eval covers these.
const NEEDS_A_MODEL = new Set([
  "negative-salary", "safety-prompt-injection", "roster-count-engineers",
]);

const engine = new Engine(index);
await engine.load(null, lib);

let failed = 0, checked = 0;
for (const item of golden) {
  if (item.mode === "find_file" || item.turns || NEEDS_A_MODEL.has(item.id)) continue;
  const r = await engine.search(item.question);
  const text = r.passages.map((p) => p.chunk.text).join("\n").toLowerCase();
  let ok = true, why = "";
  if (item.expect_refusal) {
    ok = r.passages.length === 0;
    why = `expected no passage, got ${r.passages.map((p) => p.chunk.source).join(", ")}`;
  } else if (item.expect_answer_contains_any) {
    ok = item.expect_answer_contains_any.some((k) => text.includes(k.toLowerCase()));
    why = `none of ${JSON.stringify(item.expect_answer_contains_any)} in the top passages`;
  } else if (item.expect_answer_contains_all) {
    ok = item.expect_answer_contains_all.every((k) => text.includes(k.toLowerCase()));
    why = `not all of ${JSON.stringify(item.expect_answer_contains_all)} in the top passages`;
  }
  checked++;
  if (!ok) failed++;
  const top = r.passages[0];
  console.log(`${ok ? "PASS" : "FAIL"}  ${item.id.padEnd(30)} ${ok ? (top ? `${top.chunk.source} (${top.score.toFixed(2)})` : "refused") : why}`);
}
console.log(`\n${checked - failed} passed, ${failed} failed`);
// Release the ONNX sessions first: exiting with them open aborts the
// process in onnxruntime's teardown, and a crash would fail CI on a pass.
await engine.embedder.dispose();
await engine.reranker.model.dispose();
process.exitCode = failed ? 1 : 0;
