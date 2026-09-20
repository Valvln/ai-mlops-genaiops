"""Cut docs/exam-notes/*.md into retrievable chunks, measuring before cutting.

FR-002 IS THE ORDER OF THE TWO OPERATIONS, NOT THE CHUNKING ITSELF. Learn
recommends 512 tokens with 25 % overlap and, on the same page, 200 words with
10-15 % overlap; the two are not reconcilable and neither is derived from
anything about this corpus. So the token distribution is measured and printed
first, and the cap is applied second — a recommended constant applied to an
unmeasured corpus is a number that cannot be wrong, because nothing was ever
checked against it.

The corpus is the working tree at a commit. No copy is made: `corpus_commit`
travels on every chunk, so a run is reproducible from the repository rather than
from a snapshot that has to be kept in sync with it.

Usage:
    uv run chunk_corpus.py --report        # measure and print, write nothing
    uv run chunk_corpus.py                 # measure, print, and write chunks.jsonl
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import tiktoken

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "docs" / "exam-notes"
OUT_PATH = Path(__file__).resolve().parent / "chunks.jsonl"

# The encoding text-embedding-3-large actually uses. Counting with a different
# tokenizer would make every number below approximately right and specifically
# wrong, which is the failure mode this script exists to avoid.
ENCODING = "o200k_base"

# data-model.md § 2. 512 with 128 overlap is the first of Learn's two mutually
# inconsistent recommendations; the choice is recorded rather than resolved, and
# the sweep that could resolve it is out of scope by decision (it would re-embed
# the whole corpus once per cell).
MAX_TOKENS = 512
OVERLAP_TOKENS = 128

# Splits on H2 only. H3 would cut mid-argument in these notes - several of them
# carry the actual finding in a sub-section under a neutral H2 - and H1 is one
# per file, which is no split at all.
H2 = re.compile(r"^## ", re.MULTILINE)


def corpus_commit() -> str:
    """The revision the corpus was read at, with the same -dirty honesty as
    block 3's prompt_version: a chunk attributed to a clean commit whose content
    is not what was embedded would make every run after it unreproducible in a
    way nothing announces."""
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%h", "--", str(CORPUS_DIR)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    ).stdout.strip()
    if not commit:
        return "uncommitted"
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", str(CORPUS_DIR)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    ).stdout.strip()
    return f"{commit}-dirty" if dirty else commit


def sections(text: str) -> list[tuple[str, str]]:
    """Split one note into (heading, body) pairs on H2 boundaries.

    Everything before the first H2 - the title and any preamble - is kept under
    a synthetic heading rather than dropped. In these notes that preamble is
    often the sentence that says what the note is *for*, which is exactly the
    text a title-field semantic ranker wants to see.
    """
    parts = H2.split(text)
    out = [("(preamble)", parts[0].strip())] if parts[0].strip() else []
    for part in parts[1:]:
        line, _, body = part.partition("\n")
        out.append((line.strip(), f"## {line.strip()}\n{body}".strip()))
    return out


def window(tokens: list[int], enc: tiktoken.Encoding) -> list[str]:
    """Slide a MAX_TOKENS window over a section that exceeds the cap.

    Stride is MAX_TOKENS - OVERLAP_TOKENS = 384. The overlap is what stops a
    definition from being severed from the sentence that qualifies it; the cost
    is that the corpus is embedded at ~1.33x its own length, which is priced in
    the cost model rather than discovered afterwards.
    """
    stride = MAX_TOKENS - OVERLAP_TOKENS
    out = []
    for start in range(0, len(tokens), stride):
        piece = tokens[start:start + MAX_TOKENS]
        if not piece:
            break
        out.append(enc.decode(piece))
        if start + MAX_TOKENS >= len(tokens):
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true",
                    help="measure and print the distribution, write nothing")
    args = ap.parse_args()

    enc = tiktoken.get_encoding(ENCODING)
    commit = corpus_commit()
    notes = sorted(CORPUS_DIR.glob("*.md"))
    if not notes:
        print(f"No notes under {CORPUS_DIR}", file=sys.stderr)
        return 2

    # --- Measure first (FR-002) ---------------------------------------------
    print(f"corpus: {CORPUS_DIR.relative_to(REPO_ROOT)} @ {commit}")
    print(f"tokenizer: {ENCODING}  cap: {MAX_TOKENS}  overlap: {OVERLAP_TOKENS}\n")
    print(f"{'note':<46}{'tokens':>8}{'H2':>5}")
    print("-" * 59)

    per_note = []
    for note in notes:
        text = note.read_text(encoding="utf-8")
        secs = sections(text)
        n_tokens = len(enc.encode(text))
        per_note.append((note, secs, n_tokens))
        print(f"{note.name:<46}{n_tokens:>8}{len(secs):>5}")

    total = sum(n for _, _, n in per_note)
    print("-" * 59)
    print(f"{'total':<46}{total:>8}")
    print(f"\n{len(notes)} notes, {total} tokens, "
          f"mean {total // len(notes)} tokens/note")

    # --- Then cut ------------------------------------------------------------
    chunks = []
    oversize = 0
    for note, secs, _ in per_note:
        slug = note.stem
        for heading, body in secs:
            tokens = enc.encode(body)
            pieces = [body] if len(tokens) <= MAX_TOKENS else window(tokens, enc)
            if len(pieces) > 1:
                oversize += 1
            for piece in pieces:
                chunks.append({
                    # Positional and stable for a given corpus commit. The index
                    # key must be URL-safe, which rules out the heading text.
                    "chunk_id": f"{slug}--{len(chunks):03d}",
                    "note": note.name,
                    "heading": heading,
                    "content": piece,
                    "token_count": len(enc.encode(piece)),
                    "corpus_commit": commit,
                })

    sizes = sorted(c["token_count"] for c in chunks)
    print(f"\nchunks: {len(chunks)}  "
          f"({oversize} sections exceeded the cap and were windowed)")
    print(f"token_count  min {sizes[0]}  "
          f"median {sizes[len(sizes) // 2]}  max {sizes[-1]}")
    # The number the embedding bill is actually charged on: overlap means this
    # exceeds the corpus's own token count, and by how much is worth seeing.
    embedded = sum(sizes)
    print(f"tokens to embed: {embedded} "
          f"({embedded / total:.2f}x the corpus, from the overlap)")
    # 4 bytes per float32 dimension. A prediction, which SC-006 replaces with
    # the service's own measurement after ingestion.
    print(f"predicted vector index size: "
          f"{len(chunks) * 3072 * 4 / 1_048_576:.2f} MB "
          f"({len(chunks)} x 3072 x 4 B)")

    if args.report:
        print("\n--report: nothing written.")
        return 0

    with OUT_PATH.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"\nwrote {OUT_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
