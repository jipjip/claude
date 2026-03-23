#!/usr/bin/env python3
"""
Phase 3 — Media query consolidation (reference implementation)

Moves all multi-line @media blocks to the bottom of the file, merged by breakpoint.
Single-line blocks (e.g. custom property overrides like `:root { --token: value }`)
are detected and left in place.

USAGE
-----
    python3 phase3-consolidate-mq.py path/to/file.css

ASSUMPTIONS / ADAPT BEFORE REUSE
----------------------------------
1.  Only handles `@media(max-width: Xpx)` syntax — no space after `@media`, no
    `min-width`, no `screen and (...)`. Extend the regex in Step 2 as needed.

2.  "Single-line" detection (`'\n' not in full_block`) is a heuristic that works
    when intentional one-liners are written that way (e.g. consolidated token
    overrides). If the file has legitimately short blocks that span two lines,
    this will incorrectly move them. Adjust the heuristic or replace with a
    content-based check (e.g. skip if inner content contains only `--` vars).

3.  The RESPONSIVE divider cleanup (Step 4) uses regexes tuned to a specific
    comment format. Review and update for the target file's conventions.

4.  Output is ordered largest → smallest breakpoint (desktop-first, preserves
    cascade). For mobile-first files, reverse `sorted(extracted.keys(), reverse=True)`.

5.  No support for `@keyframes`, `@supports`, or nested `@media`. If the file
    contains these, they will be ignored (not moved) but may leave gaps.

WHAT IT DOES
------------
  Step 1  Remove empty single-line blocks: @media(max-width: Xpx) {}
  Step 2  Parse all @media blocks with a brace-counting walker
  Step 3  Extract multi-line non-empty blocks; remove originals (reverse order)
  Step 4  Clean up orphaned RESPONSIVE section divider comments
  Step 5  Collapse 3+ blank lines → 2
  Step 6  Append merged blocks at the bottom, sorted by breakpoint
"""

import re
import sys

if len(sys.argv) < 2:
    print("Usage: phase3-consolidate-mq.py <file.css>")
    sys.exit(1)

filepath = sys.argv[1]
with open(filepath, "r", encoding="utf-8") as f:
    text = f.read()

# ---------------------------------------------------------------------------
# Step 1 — Remove empty single-line blocks
# ---------------------------------------------------------------------------
text = re.sub(r"@media\(max-width:\s*\d+px\)\s*\{\}\n?", "", text)

# ---------------------------------------------------------------------------
# Step 2 — Parse all @media blocks (brace-counting walker)
# ---------------------------------------------------------------------------
# Adapt this pattern for other @media syntaxes as needed.
MEDIA_RE = re.compile(r"@media\(max-width:\s*(\d+)px\)\s*\{")

extracted = {}  # breakpoint (int) → [inner_content, ...]
removals = []   # [(start, end), ...] positions to delete from text

pos = 0
while pos < len(text):
    m = MEDIA_RE.search(text, pos)
    if not m:
        break

    block_start = m.start()
    bp = int(m.group(1))
    brace_open = m.end() - 1  # index of the opening `{`

    # Walk forward counting braces to find the matching `}`
    depth = 0
    j = brace_open
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1

    block_end = j + 1
    full_block = text[block_start:block_end]
    inner = text[brace_open + 1 : j]

    is_single_line = "\n" not in full_block  # ← heuristic, see note 2 above
    is_empty = not inner.strip()

    if not is_single_line and not is_empty:
        extracted.setdefault(bp, []).append(inner)
        # Consume trailing newline so we don't leave a blank line behind
        remove_end = block_end
        if remove_end < len(text) and text[remove_end] == "\n":
            remove_end += 1
        removals.append((block_start, remove_end))

    pos = block_end

# ---------------------------------------------------------------------------
# Step 3 — Remove extracted blocks (reverse order preserves character indices)
# ---------------------------------------------------------------------------
chars = list(text)
for start, end in sorted(removals, reverse=True):
    del chars[start:end]
text = "".join(chars)

# ---------------------------------------------------------------------------
# Step 4 — Clean up orphaned RESPONSIVE divider comments
# Tune these patterns to the target file's comment conventions.
# ---------------------------------------------------------------------------
text = re.sub(r"\n*/\*{4,}\*/?\n/\*\s*RESPONSIVE\s*\*/\n/\*{4,}\*/?\n*", "\n", text)
text = re.sub(r"\n*/\*{3,}\n\s*/\*RESPONSIVE\*/\s*\n\s*/\*{3,}\n*", "\n", text)
text = re.sub(r"\n*/{4,}\n/{4,}\n", "\n", text)

# ---------------------------------------------------------------------------
# Step 5 — Collapse 3+ consecutive blank lines → 2
# ---------------------------------------------------------------------------
text = re.sub(r"\n{3,}", "\n\n", text)

# ---------------------------------------------------------------------------
# Step 6 — Build the merged block and append at the bottom
# desktop-first: largest breakpoint first (see note 4 for mobile-first)
# ---------------------------------------------------------------------------
sorted_bps = sorted(extracted.keys(), reverse=True)

header = (
    "\n\n/************************************************************/\n"
    "/* [optimize-css] consolidated media queries — Phase 3      */\n"
    "/************************************************************/\n"
)

bottom = header
for bp in sorted_bps:
    bottom += f"\n@media(max-width: {bp}px) {{"
    for idx, inner in enumerate(extracted[bp]):
        if idx > 0 and not inner.startswith("\n\n"):
            bottom += "\n"
        bottom += inner
        if not inner.endswith("\n"):
            bottom += "\n"
    bottom += "}\n"

text = text.rstrip() + "\n" + bottom

with open(filepath, "w", encoding="utf-8") as f:
    f.write(text)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
print("Phase 3 done.")
total = 0
for bp in sorted_bps:
    n = len(extracted[bp])
    total += n
    print(f"  max-width: {bp}px  — {n} block(s)")
print(f"Total blocks moved: {total}")
