#!/usr/bin/env python3
"""
CSS structural index — zero-dependency pre-parser for optimize-css.

Parses a CSS file (or inline <style> from HTML) into a compact JSON index
that captures structure without full content. The index is small enough to
feed to an LLM for phase routing and quick-scan analysis, replacing the
need to read the entire file.

USAGE
-----
    python3 parse-structure.py path/to/file.css
    python3 parse-structure.py path/to/page.html          # extracts <style>
    python3 parse-structure.py path/to/file.css -o index.json
    python3 parse-structure.py path/to/file.css --pretty

OUTPUT
------
JSON structural index to stdout (or file with -o). See --help for options.

WHAT IT CAPTURES
----------------
  - Rule blocks: selector, line range, property count, nesting depth
  - Media queries: condition, direction, line range, contained selectors
  - Keyframes: name, line range
  - :root variables: name, value, line
  - @layer declarations and blocks
  - @scope blocks
  - Color frequency: hardcoded hex/rgb/hsl values and their counts
  - !important count and locations
  - Wildcard/structural selector locations
  - File metadata: line count, byte size, dialect, inline extraction info
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Color detection
# ---------------------------------------------------------------------------
HEX_RE = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b"
)
FUNC_COLOR_RE = re.compile(
    r"\b(?:rgb|rgba|hsl|hsla|oklch|oklab|lab|lch|color)\s*\("
)
# Named CSS colors worth flagging (common ones that suggest hardcoding)
NAMED_COLORS = {
    "red", "blue", "green", "black", "white", "gray", "grey",
    "orange", "purple", "yellow", "pink", "cyan", "magenta",
    "navy", "teal", "maroon", "olive", "lime", "aqua", "fuchsia",
    "silver", "coral", "salmon", "tomato", "gold", "khaki",
    "crimson", "indigo", "violet", "plum", "orchid", "turquoise",
}

# Properties that use color values (to avoid false positives on non-color hex)
COLOR_PROPERTIES = {
    "color", "background-color", "background", "border-color",
    "border-top-color", "border-right-color", "border-bottom-color",
    "border-left-color", "border", "border-top", "border-right",
    "border-bottom", "border-left", "outline-color", "outline",
    "text-decoration-color", "box-shadow", "text-shadow",
    "fill", "stroke", "stop-color", "flood-color", "lighting-color",
    "caret-color", "column-rule-color", "accent-color",
}

# ---------------------------------------------------------------------------
# MQ direction detection
# ---------------------------------------------------------------------------
MQ_MIN_RE = re.compile(r"(?:min-width\s*[:>]|width\s*>=?\s*\d)", re.IGNORECASE)
MQ_MAX_RE = re.compile(r"(?:max-width\s*[:>]|width\s*<=?\s*\d)", re.IGNORECASE)
MQ_DEPRECATED_RE = re.compile(
    r"(?:max|min)-device-(?:width|height)", re.IGNORECASE
)
MQ_BP_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(px|em|rem)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Wildcard / structural selector patterns
# ---------------------------------------------------------------------------
WILDCARD_RE = re.compile(
    r"(?:^|\s|,)"          # start or separator
    r"(?:"
    r"\*\s*[+~>]"          # * + , * ~ , * >
    r"|[+~>]\s*\*"         # + * , ~ * , > *
    r"|\.\S+\s+\*"         # .class *
    r"|^\s*\*\s*,"         # * , (universal at start of list)
    r"|,\s*\*\s*(?:,|$)"   # , * , or , * (end)
    r"|^\s*\*\s*$"         # just *
    r")"
)

# ---------------------------------------------------------------------------
# Inline <style> extraction
# ---------------------------------------------------------------------------
STYLE_OPEN_RE = re.compile(r"<style[^>]*>", re.IGNORECASE)
STYLE_CLOSE_RE = re.compile(r"</style>", re.IGNORECASE)


def extract_inline_css(text):
    """Extract CSS from <style> blocks. Returns (css_text, metadata)."""
    blocks = []
    pos = 0
    while pos < len(text):
        m_open = STYLE_OPEN_RE.search(text, pos)
        if not m_open:
            break
        css_start = m_open.end()
        # Line number of CSS start
        start_line = text[:css_start].count("\n") + 1
        m_close = STYLE_CLOSE_RE.search(text, css_start)
        if not m_close:
            break
        css_end = m_close.start()
        blocks.append({
            "css": text[css_start:css_end],
            "start_line": start_line,
            "end_line": text[:css_end].count("\n") + 1,
            "char_offset": css_start,
        })
        pos = m_close.end()

    if not blocks:
        return None, None

    # Concatenate all style blocks (rare to have multiple, but possible)
    combined = "\n".join(b["css"] for b in blocks)
    meta = {
        "style_blocks": len(blocks),
        "ranges": [
            {"start_line": b["start_line"], "end_line": b["end_line"]}
            for b in blocks
        ],
        "line_offset": blocks[0]["start_line"] - 1,
    }
    return combined, meta


# ---------------------------------------------------------------------------
# Brace-counting CSS tokenizer
# ---------------------------------------------------------------------------

class CSSStructureParser:
    """State-machine parser that tracks brace depth and extracts structure."""

    def __init__(self, text, line_offset=0):
        self.text = text
        self.lines = text.split("\n")
        self.line_offset = line_offset  # for inline CSS: offset to map back

        # Results
        self.rules = []
        self.media_queries = []
        self.keyframes = []
        self.root_vars = []
        self.layers = []
        self.scopes = []
        self.important_locations = []
        self.wildcard_locations = []
        self.colors = Counter()
        self.nesting_depth_max = 0

    def parse(self):
        """Main parse loop — single pass, brace counting."""
        text = self.text
        i = 0
        length = len(text)

        while i < length:
            # Skip whitespace
            while i < length and text[i] in " \t\n\r":
                i += 1
            if i >= length:
                break

            # Skip comments
            if text[i:i+2] == "/*":
                end = text.find("*/", i + 2)
                i = end + 2 if end != -1 else length
                continue

            # At-rules
            if text[i] == "@":
                i = self._parse_at_rule(i)
                continue

            # Regular rule
            if text[i] not in "{}":
                i = self._parse_rule(i, context=None)
                continue

            # Stray closing brace (shouldn't happen at top level)
            if text[i] == "}":
                i += 1
                continue

            i += 1

        # Scan for colors and !important across all lines
        self._scan_values()

        return self._build_index()

    def _line_at(self, char_pos):
        """Convert character position to 1-based line number."""
        return self.text[:char_pos].count("\n") + 1 + self.line_offset

    def _find_block_end(self, open_brace_pos):
        """Find matching closing brace using depth counting."""
        depth = 0
        i = open_brace_pos
        while i < len(self.text):
            ch = self.text[i]
            if ch == "/" and i + 1 < len(self.text) and self.text[i+1] == "*":
                end = self.text.find("*/", i + 2)
                i = end + 2 if end != -1 else len(self.text)
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return len(self.text) - 1

    def _extract_inner_selectors(self, inner_text, parent_line):
        """Extract selector names from block inner content (for MQ, layer, scope)."""
        selectors = []
        i = 0
        while i < len(inner_text):
            # Skip whitespace and comments
            while i < len(inner_text) and inner_text[i] in " \t\n\r":
                i += 1
            if i >= len(inner_text):
                break
            if inner_text[i:i+2] == "/*":
                end = inner_text.find("*/", i + 2)
                i = end + 2 if end != -1 else len(inner_text)
                continue

            # Find selector (text before {)
            brace = inner_text.find("{", i)
            if brace == -1:
                break

            selector_text = inner_text[i:brace].strip()
            if selector_text:
                # Find the closing brace for this rule
                depth = 1
                j = brace + 1
                while j < len(inner_text) and depth > 0:
                    if inner_text[j] == "/" and j + 1 < len(inner_text) and inner_text[j+1] == "*":
                        end = inner_text.find("*/", j + 2)
                        j = end + 2 if end != -1 else len(inner_text)
                        continue
                    if inner_text[j] == "{":
                        depth += 1
                    elif inner_text[j] == "}":
                        depth -= 1
                    j += 1

                # Count properties in this rule
                rule_inner = inner_text[brace+1:j-1] if j > brace+1 else ""
                prop_count = rule_inner.count(";")
                # Check for nested rules (has braces inside)
                has_nesting = "{" in rule_inner

                selectors.append({
                    "name": self._clean_selector(selector_text),
                    "properties": prop_count,
                    "nested": has_nesting,
                })
                i = j
            else:
                i = brace + 1

        return selectors

    def _clean_selector(self, s):
        """Normalize a selector string: collapse whitespace, trim."""
        s = re.sub(r"\s+", " ", s.strip())
        # Truncate very long selector lists (e.g. theme customizer)
        if len(s) > 200:
            # Count selectors in the list
            parts = [p.strip() for p in s.split(",")]
            if len(parts) > 3:
                return f"{parts[0]}, {parts[1]}, ... +{len(parts)-2} more"
        return s

    def _parse_at_rule(self, start):
        """Parse @media, @keyframes, @layer, @scope, and other at-rules."""
        text = self.text

        # Find the at-rule keyword
        end_keyword = start + 1
        while end_keyword < len(text) and (text[end_keyword].isalpha() or text[end_keyword] == "-"):
            end_keyword += 1
        keyword = text[start+1:end_keyword].lower()

        if keyword == "media":
            return self._parse_media(start)
        elif keyword == "keyframes" or keyword in ("-webkit-keyframes", "-moz-keyframes"):
            return self._parse_keyframes(start)
        elif keyword == "layer":
            return self._parse_layer(start)
        elif keyword == "scope":
            return self._parse_scope(start)
        else:
            # Other at-rules (@charset, @import, @font-face, @supports, @property, @view-transition, etc.)
            # Find either ; (statement) or {} (block)
            brace = text.find("{", start)
            semi = text.find(";", start)

            if semi != -1 and (brace == -1 or semi < brace):
                # Statement at-rule
                return semi + 1
            elif brace != -1:
                # Block at-rule
                block_end = self._find_block_end(brace)
                return block_end + 1
            else:
                return len(text)

    def _parse_media(self, start):
        """Parse @media block and recursively parse its inner rules."""
        text = self.text
        brace = text.find("{", start)
        if brace == -1:
            return len(text)

        condition = text[start:brace].strip()
        # Remove @media prefix
        condition_text = re.sub(r"^@media\s*", "", condition).strip()
        # Remove "only screen and" prefix if present
        condition_clean = re.sub(
            r"^only\s+screen\s+and\s*", "", condition_text
        ).strip()

        block_end = self._find_block_end(brace)
        inner = text[brace+1:block_end]
        inner_offset = brace + 1  # char offset of inner content in self.text

        start_line = self._line_at(start)
        end_line = self._line_at(block_end)

        # Detect direction
        has_min = bool(MQ_MIN_RE.search(condition_text))
        has_max = bool(MQ_MAX_RE.search(condition_text))
        deprecated = bool(MQ_DEPRECATED_RE.search(condition_text))

        if has_min and has_max:
            direction = "range"
        elif has_min:
            direction = "mobile-first"
        elif has_max:
            direction = "desktop-first"
        else:
            direction = "other"

        # Extract breakpoint value
        bp_match = MQ_BP_RE.search(condition_text)
        breakpoint = None
        if bp_match:
            breakpoint = f"{bp_match.group(1)}{bp_match.group(2)}"

        # Parse inner rules — add them to self.rules and capture :root vars
        inner_rules = self._parse_inner_rules(inner, inner_offset, mq_condition=condition_clean)

        mq = {
            "condition": condition_clean,
            "line": start_line,
            "end_line": end_line,
            "direction": direction,
            "selectors": len(inner_rules),
            "selector_names": [r["selector"] for r in inner_rules[:10]],
        }
        if breakpoint:
            mq["breakpoint"] = breakpoint
        if deprecated:
            mq["deprecated"] = True
        if len(inner_rules) > 10:
            mq["selector_names_truncated"] = True

        self.media_queries.append(mq)
        return block_end + 1

    def _parse_inner_rules(self, inner_text, char_offset, mq_condition=None):
        """Parse rules inside a container block (MQ, layer, scope).
        Adds rules to self.rules and returns the list for the caller."""
        rules_found = []
        i = 0
        while i < len(inner_text):
            # Skip whitespace and comments
            while i < len(inner_text) and inner_text[i] in " \t\n\r":
                i += 1
            if i >= len(inner_text):
                break
            if inner_text[i:i+2] == "/*":
                end = inner_text.find("*/", i + 2)
                i = end + 2 if end != -1 else len(inner_text)
                continue

            # Find selector (text before {)
            brace = inner_text.find("{", i)
            if brace == -1:
                break

            selector_text = inner_text[i:brace].strip()
            if not selector_text:
                i = brace + 1
                continue

            # Find the closing brace for this rule
            depth = 1
            j = brace + 1
            while j < len(inner_text) and depth > 0:
                if inner_text[j] == "/" and j + 1 < len(inner_text) and inner_text[j+1] == "*":
                    end = inner_text.find("*/", j + 2)
                    j = end + 2 if end != -1 else len(inner_text)
                    continue
                if inner_text[j] == "{":
                    depth += 1
                elif inner_text[j] == "}":
                    depth -= 1
                j += 1

            rule_inner = inner_text[brace+1:j-1] if j > brace+1 else ""
            prop_count = rule_inner.count(";")
            has_nesting = "{" in rule_inner

            clean_sel = self._clean_selector(selector_text)
            rule_line = self._line_at(char_offset + i)
            rule_end_line = self._line_at(char_offset + j - 1)

            # Check for :root vars
            if re.match(r"^:root\b", selector_text.strip()):
                self._extract_root_vars(rule_inner, rule_line)

            # Check for wildcard selectors
            if WILDCARD_RE.search(selector_text):
                self.wildcard_locations.append({
                    "selector": clean_sel,
                    "line": rule_line,
                })

            rule = {
                "selector": clean_sel,
                "line": rule_line,
                "end_line": rule_end_line,
                "properties": prop_count,
            }
            if has_nesting:
                rule["nested"] = True
                # Track nesting depth
                max_depth = 0
                d = 0
                for ch in rule_inner:
                    if ch == "{":
                        d += 1
                        max_depth = max(max_depth, d)
                    elif ch == "}":
                        d -= 1
                total_depth = max_depth + 1
                if total_depth > self.nesting_depth_max:
                    self.nesting_depth_max = total_depth

            if self._has_tag_descendant(selector_text):
                rule["tag_descendants"] = True
            if mq_condition:
                rule["in_mq"] = mq_condition

            self.rules.append(rule)
            rules_found.append(rule)
            i = j

        return rules_found

    def _parse_keyframes(self, start):
        """Parse @keyframes block."""
        text = self.text
        brace = text.find("{", start)
        if brace == -1:
            return len(text)

        header = text[start:brace].strip()
        name_match = re.search(r"@(?:-\w+-)?keyframes\s+(\S+)", header)
        name = name_match.group(1) if name_match else "unknown"

        block_end = self._find_block_end(brace)
        start_line = self._line_at(start)
        end_line = self._line_at(block_end)

        self.keyframes.append({
            "name": name,
            "line": start_line,
            "end_line": end_line,
        })
        return block_end + 1

    def _parse_layer(self, start):
        """Parse @layer declaration or block."""
        text = self.text
        brace = text.find("{", start)
        semi = text.find(";", start)

        if semi != -1 and (brace == -1 or semi < brace):
            # Declaration: @layer reset, defaults, layouts;
            decl = text[start:semi].strip()
            names_text = re.sub(r"^@layer\s*", "", decl)
            names = [n.strip() for n in names_text.split(",") if n.strip()]
            self.layers.append({
                "type": "declaration",
                "names": names,
                "line": self._line_at(start),
            })
            return semi + 1
        elif brace != -1:
            # Block: @layer components { ... }
            header = text[start:brace].strip()
            name = re.sub(r"^@layer\s*", "", header).strip()
            block_end = self._find_block_end(brace)
            inner = text[brace+1:block_end]
            selectors = self._extract_inner_selectors(inner, self._line_at(start))

            self.layers.append({
                "type": "block",
                "name": name if name else "(anonymous)",
                "line": self._line_at(start),
                "end_line": self._line_at(block_end),
                "selectors": len(selectors),
            })
            return block_end + 1
        return len(text)

    def _parse_scope(self, start):
        """Parse @scope block."""
        text = self.text
        brace = text.find("{", start)
        if brace == -1:
            return len(text)

        header = text[start:brace].strip()
        block_end = self._find_block_end(brace)

        self.scopes.append({
            "header": re.sub(r"\s+", " ", header),
            "line": self._line_at(start),
            "end_line": self._line_at(block_end),
        })
        return block_end + 1

    def _parse_rule(self, start, context=None):
        """Parse a regular CSS rule block."""
        text = self.text
        brace = text.find("{", start)
        if brace == -1:
            return len(text)

        selector = text[start:brace].strip()
        if not selector:
            # Empty selector — skip
            block_end = self._find_block_end(brace)
            return block_end + 1

        block_end = self._find_block_end(brace)
        inner = text[brace+1:block_end]

        start_line = self._line_at(start)
        end_line = self._line_at(block_end)

        # Count properties
        prop_count = inner.count(";")

        # Detect nesting
        has_nesting = "{" in inner
        if has_nesting:
            # Count nesting depth
            max_depth = 0
            depth = 0
            for ch in inner:
                if ch == "{":
                    depth += 1
                    max_depth = max(max_depth, depth)
                elif ch == "}":
                    depth -= 1
            # +1 for the rule itself
            total_depth = max_depth + 1
            if total_depth > self.nesting_depth_max:
                self.nesting_depth_max = total_depth

        clean_sel = self._clean_selector(selector)

        # Check for :root
        if re.match(r"^:root\b", selector.strip()):
            self._extract_root_vars(inner, start_line)

        # Check for wildcard selectors
        if WILDCARD_RE.search(selector):
            self.wildcard_locations.append({
                "selector": clean_sel,
                "line": start_line,
            })

        rule = {
            "selector": clean_sel,
            "line": start_line,
            "end_line": end_line,
            "properties": prop_count,
        }
        if has_nesting:
            rule["nested"] = True
        # Detect tag selectors inside class context
        if self._has_tag_descendant(selector):
            rule["tag_descendants"] = True

        self.rules.append(rule)
        return block_end + 1

    def _extract_root_vars(self, inner, start_line):
        """Extract custom property declarations from :root block."""
        for line in inner.split("\n"):
            stripped = line.strip()
            match = re.match(r"(--[\w-]+)\s*:\s*(.+?)\s*;", stripped)
            if match:
                name = match.group(1)
                value = match.group(2).strip()
                # Remove inline comments
                comment_pos = value.find("/*")
                if comment_pos != -1:
                    value = value[:comment_pos].strip()
                self.root_vars.append({
                    "name": name,
                    "value": value,
                })

    def _has_tag_descendant(self, selector):
        """Check if selector contains tag elements inside a class context."""
        # Split selector list
        parts = selector.split(",")
        for part in parts:
            tokens = part.strip().split()
            has_class = False
            for token in tokens:
                # Remove combinators
                token = token.strip(">+~")
                if not token:
                    continue
                if token.startswith(".") or token.startswith("#"):
                    has_class = True
                elif has_class and re.match(r"^[a-z][a-z0-9]*$", token, re.IGNORECASE):
                    # Tag selector after a class
                    return True
        return False

    def _scan_values(self):
        """Scan all lines for colors, !important, etc."""
        for i, line in enumerate(self.lines):
            lineno = i + 1 + self.line_offset
            stripped = line.strip()

            # Skip comments
            if stripped.startswith("/*") or stripped.startswith("//"):
                continue

            # !important
            if "!important" in stripped:
                self.important_locations.append(lineno)

            # Hex colors — only count in property value context
            if ":" in stripped and not stripped.startswith("/*"):
                # Get the property name
                colon_pos = stripped.find(":")
                prop_part = stripped[:colon_pos].strip().lower()
                # Remove selectors that happen to contain colons (pseudo-classes)
                if not prop_part.startswith(".") and not prop_part.startswith("&"):
                    value_part = stripped[colon_pos+1:]
                    for m in HEX_RE.finditer(value_part):
                        color = m.group(0).lower()
                        self.colors[color] += 1

    def _build_index(self):
        """Assemble the final index object."""
        # Summarize rules — group by selector pattern type
        # For large files, cap the rules list
        rules_summary = self.rules
        if len(rules_summary) > 100:
            # Keep first 50 and last 50, note truncation
            rules_summary = (
                self.rules[:50]
                + [{"_truncated": True, "total_rules": len(self.rules)}]
                + self.rules[-50:]
            )

        # Color frequency — sort by count, top 20
        color_freq = dict(self.colors.most_common(20))

        index = {
            "meta": {
                "lines": len(self.lines),
                "bytes": len(self.text),
                "nesting_depth_max": self.nesting_depth_max,
            },
            "root_vars": self.root_vars,
            "rules": rules_summary,
            "media_queries": self.media_queries,
            "keyframes": self.keyframes,
            "important": {
                "count": len(self.important_locations),
                "lines": self.important_locations[:20],  # cap
            },
            "colors": color_freq,
        }

        if self.layers:
            index["layers"] = self.layers
        if self.scopes:
            index["scopes"] = self.scopes
        if self.wildcard_locations:
            index["wildcards"] = self.wildcard_locations

        return index


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a structural CSS index for optimize-css"
    )
    parser.add_argument("file", help="CSS or HTML file to parse")
    parser.add_argument("-o", "--output", help="Write JSON to file instead of stdout")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"Error: {filepath} not found", file=sys.stderr)
        sys.exit(1)

    text = filepath.read_text(encoding="utf-8")
    ext = filepath.suffix.lower()

    inline_meta = None
    line_offset = 0

    # Detect inline CSS
    if ext in (".html", ".htm", ".astro", ".svelte", ".vue", ".php"):
        css_text, inline_meta = extract_inline_css(text)
        if css_text is None:
            print(f"Error: no <style> block found in {filepath}", file=sys.stderr)
            sys.exit(1)
        line_offset = inline_meta["line_offset"]
        text = css_text

    # Detect dialect
    dialect = "css"
    if ext == ".scss":
        dialect = "scss"
    elif ext == ".less":
        dialect = "less"
    elif ext == ".sass":
        dialect = "sass"

    # Parse
    p = CSSStructureParser(text, line_offset=line_offset)
    index = p.parse()

    # Add file metadata
    index["meta"]["file"] = str(filepath)
    index["meta"]["dialect"] = dialect
    if inline_meta:
        index["meta"]["inline"] = inline_meta

    # Quick-scan signals (Step 2b helpers)
    signals = compute_signals(index)
    index["signals"] = signals

    # Output
    indent = 2 if args.pretty else None
    output = json.dumps(index, indent=indent, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
        print(f"Index written to {args.output}", file=sys.stderr)
    else:
        print(output)


def compute_signals(index):
    """Compute Step 2b quick-scan optimization signals."""
    signals = {}
    score = 0

    # Signal: has :root custom properties
    var_count = len(index.get("root_vars", []))
    if var_count >= 5:
        signals["root_vars"] = {"present": True, "count": var_count, "weight": "high"}
        score += 3
    elif var_count > 0:
        signals["root_vars"] = {"present": True, "count": var_count, "weight": "low"}
        score += 1

    # Signal: @layer usage
    layers = index.get("layers", [])
    if layers:
        signals["layers"] = {"present": True, "count": len(layers), "weight": "high"}
        score += 3

    # Signal: @scope usage
    scopes = index.get("scopes", [])
    if scopes:
        signals["scopes"] = {"present": True, "count": len(scopes), "weight": "medium"}
        score += 2

    # Signal: native nesting
    nested_rules = sum(1 for r in index.get("rules", []) if r.get("nested"))
    total_rules = len([r for r in index.get("rules", []) if not r.get("_truncated")])
    if total_rules > 0 and nested_rules / total_rules > 0.3:
        signals["native_nesting"] = {
            "present": True,
            "ratio": round(nested_rules / total_rules, 2),
            "weight": "medium",
        }
        score += 2

    # Signal: zero !important
    imp_count = index.get("important", {}).get("count", 0)
    if imp_count == 0:
        signals["zero_important"] = {"present": True, "weight": "medium"}
        score += 2
    else:
        signals["important_count"] = {"count": imp_count, "weight": "negative"}

    # Signal: MQ placement (are they scattered or consolidated?)
    mqs = index.get("media_queries", [])
    if mqs:
        lines = [mq["line"] for mq in mqs]
        total_lines = index["meta"]["lines"]
        # Check if MQs are mostly at the bottom (last 30% of file)
        bottom_threshold = total_lines * 0.7
        bottom_mqs = sum(1 for l in lines if l > bottom_threshold)
        if len(lines) > 0 and bottom_mqs / len(lines) > 0.8:
            signals["mq_consolidated"] = {
                "present": True,
                "bottom_ratio": round(bottom_mqs / len(lines), 2),
                "weight": "medium",
            }
            score += 2

    # Signal: low nesting depth
    max_depth = index["meta"].get("nesting_depth_max", 0)
    if max_depth <= 2:
        signals["low_nesting_depth"] = {
            "present": True, "max": max_depth, "weight": "low"
        }
        score += 1

    # Signal: high hardcoded color count (negative — optimization opportunity)
    color_count = sum(index.get("colors", {}).values())
    unique_colors = len(index.get("colors", {}))
    if unique_colors > 10:
        signals["hardcoded_colors"] = {
            "unique": unique_colors,
            "total_uses": color_count,
            "weight": "negative",
        }
        score -= 2

    # Signal: wildcards (negative)
    wildcards = index.get("wildcards", [])
    if wildcards:
        signals["wildcards"] = {
            "count": len(wildcards),
            "weight": "negative",
        }
        score -= 1

    # Signal: !important (negative, subtract)
    if imp_count > 5:
        score -= 2
    elif imp_count > 0:
        score -= 1

    signals["_score"] = max(score, 0)
    signals["_verdict"] = (
        "well-optimized" if score >= 5
        else "moderate" if score >= 3
        else "needs-optimization"
    )

    return signals


if __name__ == "__main__":
    main()
