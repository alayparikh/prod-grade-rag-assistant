"""Assemble the adversarial corpus: the fixture docs plus injected documents.

    python eval/adversarial/build_corpus.py --out /tmp/adv_docs

Kept out of eval/fixtures/docs on purpose: the demo, the browser check and
the retrieval baseline index that folder, and none of them should carry
injected instructions. See eval/adversarial/injection.yaml.
"""
import argparse
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DOCS = os.path.join(os.path.dirname(HERE), "fixtures", "docs")
ADVERSARIAL_DOCS = os.path.join(HERE, "docs")


def build(out):
    os.makedirs(out, exist_ok=True)
    copied = 0
    for source in (FIXTURE_DOCS, ADVERSARIAL_DOCS):
        for name in sorted(os.listdir(source)):
            path = os.path.join(source, name)
            if os.path.isfile(path):
                shutil.copy2(path, os.path.join(out, name))
                copied += 1
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    print(f"Copied {build(args.out)} files to {args.out}")


if __name__ == "__main__":
    main()
