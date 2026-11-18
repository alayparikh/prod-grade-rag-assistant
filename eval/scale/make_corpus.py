"""Generate a synthetic document corpus of any size, for scale benchmarks.

Streams: files are written one at a time from a generator, so a million-file
corpus never sits in memory. Deterministic for a given seed and size.

Every file holds filler prose plus one "needle" fact that no other file has
(`needle0000042` and a made-up owner), so a benchmark can ask for any file
by its needle and know exactly which file must come back.

    python eval/scale/make_corpus.py --files 5000 --out /tmp/corpus
"""
import argparse
import os
import random

DEPARTMENTS = ["engineering", "finance", "hr", "operations", "sales", "legal", "support"]
WORDS = ("order shipment warehouse invoice robot pallet carrier policy approval budget forecast "
         "customer contract renewal incident runbook deploy release audit vendor quote region "
         "inventory sensor firmware battery charger dock lidar camera safety training quarterly "
         "meeting review summary decision owner deadline escalation priority backlog roadmap").split()
NAMES = ["Avery", "Blake", "Casey", "Devon", "Emery", "Finley", "Harper", "Jordan", "Kai", "Logan"]


def needle(i):
    return f"needle{i:07d}"


def relative_path(i):
    dept = DEPARTMENTS[i % len(DEPARTMENTS)]
    year = 2019 + (i // len(DEPARTMENTS)) % 8
    # ~500 files per folder, like a real share: deep enough to exercise the
    # crawler, shallow enough not to be pathological.
    return os.path.join(dept, str(year), f"batch{i // 500:04d}", f"doc{i:07d}.md")


def document(i, rng, paragraphs):
    owner = f"{rng.choice(NAMES)} {rng.choice(NAMES)}son"
    lines = [f"# {DEPARTMENTS[i % len(DEPARTMENTS)].title()} note {i}", ""]
    for p in range(paragraphs):
        lines.append(f"## Section {p + 1}")
        lines.append(" ".join(rng.choice(WORDS) for _ in range(rng.randint(60, 140))) + ".")
        lines.append("")
    lines.append(f"Reference {needle(i)} is owned by {owner}.")
    return "\n".join(lines) + "\n", owner


def generate(count, seed=7, paragraphs=4):
    """Yields (relative_path, text, needle, owner), one file at a time."""
    for i in range(count):
        rng = random.Random(seed * 1_000_003 + i)
        text, owner = document(i, rng, paragraphs)
        yield relative_path(i), text, needle(i), owner


def write(out, count, seed=7, paragraphs=4):
    total_bytes = 0
    for rel, text, _, _ in generate(count, seed, paragraphs):
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        total_bytes += len(text)
    return total_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--files", type=int, default=1000)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--paragraphs", type=int, default=4)
    args = parser.parse_args()
    size = write(args.out, args.files, args.seed, args.paragraphs)
    print(f"Wrote {args.files:,} files ({size / 1e6:.1f} MB) under {args.out}")


if __name__ == "__main__":
    main()
