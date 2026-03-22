---
name: optimize-css
description: Optimize CSS for performance, low specificity, and minimal file size. Supports three modes — defensive (report only), neutral (safe CSS-only edits, default), aggressive (full rewrites including HTML). Use when a user requests optimization of CSS, SCSS, or inline styles.
argument-hint: "[-d|-n|-a | defensive|neutral|aggressive] <file>"
license: Complete terms in LICENSE.txt
metadata:
  author: JipJip.com
  version: "0.4"
---

Review and optimize the CSS in `$ARGUMENTS`.

## Step 1 — Determine mode and target

Parse `$ARGUMENTS`:
- If the first word is a mode flag, extract it and treat the remainder as the target file(s).
  - Defensive: `defensive` or `-d` → report only, no edits
  - Neutral: `neutral` or `-n` → safe CSS-only edits (default)
  - Aggressive: `aggressive` or `-a` → full rewrites, edits CSS and HTML
- If no mode flag is present, default to **neutral**.
- The remaining argument(s) are the target file path(s).

In aggressive mode, also search for a corresponding HTML file alongside the CSS target to enable dead CSS checks and HTML edits.

## Step 2 — Optimization process

Run these phases in order.

### Phase 1 — De-nesting

Identify all descendant selectors and tag selectors used inside a class (e.g. `.navbar__links a`, `.footer__nav-group ul`).

- **Aggressive**: replace with explicit element classes in both CSS and HTML.
- **Neutral**: flag each one, suggest the explicit class name, but do not edit.
- **Defensive**: flag each one with the suggested class name.

### Phase 2 — Component hierarchy mapping

Identify the parent block of each component. If a component is used inside another component, note the relationship — it informs where CSS variables should be hoisted in Phase 5.

No edits are made in this phase. Do not include the map in the report.

### Phase 3 — Media query consolidation

- Move all media queries to the bottom of the file (above keyframes).
- Merge duplicate breakpoints into a single block.
- Order breakpoints ascending by value (mobile-first, min-width).
- If max-width queries are detected, flag them as desktop-first and leave them in place — do not reorder or convert them.

Applies in **neutral** and **aggressive** mode. In defensive mode, flag and report only.

### Phase 4 — Keyframe placement

Move all `@keyframes` below media queries.

Applies in **neutral** and **aggressive** mode. In defensive mode, flag and report only.

### Phase 5 — Variable extraction from media queries

For each property override inside a media query selector, apply a cost/benefit gate before substituting:

**Only replace a value with a custom property if at least one of these conditions is true:**
1. **Selector elimination** — substituting this value (and others in the same selector) allows the entire MQ selector to become var-only overrides, making it a candidate for removal.
2. **Brand/identity property** — the property is `color`, `background-color`, `font-family`, `border-color`, or similar presentational/brand properties where a single source of truth matters more than byte count.
3. **Byte neutral or smaller** — the var name + `var()` wrapper is equal to or shorter than the raw value. Rule of thumb: a var name of 5+ characters + the 5-character `var()` overhead = 10 characters minimum. A raw value shorter than that is not a candidate.

**Structural and layout properties** (`padding`, `margin`, `border-radius`, `z-index`, `line-height`, `gap`, `width`, `height`, etc.) should be left as raw values unless condition 1 (selector elimination) applies — OR the private layout var pattern applies (see below).

**Process — brand/identity properties (conditions 1–3):**
- Use the fallback pattern to initialize the variable at the point of use: `color: var(--card-color, #7c6ef5)`. This keeps the base value where it belongs and avoids an unnecessary var declaration on the parent for the default case.
- Set the var on the parent component only when a breakpoint override is needed: `@media (...) { .parent { --card-color: #9585f8; } }`.
- Use the component hierarchy from Phase 2 to determine the right parent level to hoist the override to.
- If all property overrides in a MQ selector are replaced this way, the selector is now empty — remove it.

**Process — private layout var pattern (aggressive only):**

Apply this pattern to structural/layout properties that are overridden in at least one MQ and whose base value uses a global token.

Introduce a private custom property using the `--_` prefix. Derive the name from:
- **Selector abbreviation** (max 3 chars):
  - Single word → remove vowels, max 3: `.card` → `crd`, `.header` → `hdr`, `.container` → `ctr`
  - Hyphenated → first letter of each part, max 3: `.image-slider` → `isl`, `.pricing-card` → `pc`
  - BEM element (`__`) → abbreviate block + element: `.footer__nav` → `fn`
- **Property abbreviation** (max 3 chars):
  - Short single word → 1 char: `padding` → `p`, `width` → `w`, `margin` → `m`, `gap` → `g`
  - Multi-word → first letter of each word: `background-color` → `bgc`, `grid-template-columns` → `gtc`, `max-height` → `mh`, `border-radius` → `br`, `padding-inline` → `pi`
- **Collision handling**: if two different selector+property combinations produce the same abbreviation, add one extra character to distinguish. Flag the collision in the report and suggest the resolution — do not silently pick one.

**Transformation:**
- Base property: `padding: var(--spacing-md)` → `padding: var(--_hrp, var(--spacing-md))`
- MQ override (same selector, not hoisted to parent): `padding: var(--spacing-lg)` → `--_hrp: var(--spacing-lg)`
- Result: the actual property appears once; all MQ selectors only contain var overrides.

**Global var detection:**
- If a var is used but not defined in the current file, it is likely defined in a global stylesheet.
- Trace the `<link>` tags in the HTML file to identify candidate global files.
- It is safe to reference undeclared vars in fallbacks — they resolve at runtime from the global scope.

**Neutral**: only substitute using variables that already exist in the file. Do not create new tokens. Private layout vars are aggressive-only.
**Aggressive**: create new tokens where needed. Apply private layout var pattern. Remove selectors that become empty after extraction.
**Defensive**: flag opportunities that pass the cost/benefit gate, suggest token names and initialization values, no edits.

## TODO

Integrate these checks into the appropriate phases above.

### `!important`
Flag every usage. Determine whether it exists because of a specificity conflict, and if so identify the conflicting selector and the structural fix.

### Specificity
- Flag selectors that climb specificity unnecessarily (chained classes, tag qualifiers, deep descendant selectors).
- Flag modifiers that rely on parent context to work (e.g. `.parent--mod .block__el`).
- Flag cross-block coupling: one block's modifier overriding another block's styles (e.g. `.card--highlighted .btn--ghost`).

### Token consolidation
- Flag hardcoded values already covered by an existing custom property.
- Flag raw values repeated 2+ times that are longer than a reasonable variable name — suggest a new token name.
- Flag near-duplicate tokens that serve the same purpose.

### Dead CSS
- Flag selectors with no matching element in the HTML (aggressive mode only — requires HTML file).
- In neutral/defensive mode, note that dead CSS check was skipped (no HTML available).

### Wildcard / structural selectors
- Flag `> *`, `* + *`, and similar structural selectors that create invisible specificity or fragile DOM dependencies. Suggest named elements instead.

## Step 3 — Report

Structure output differently per mode:

### Defensive
Full report, no changes made:
1. **Issues found** — grouped by phase, each with line references
2. **Suggested fixes** — concrete rewrites for each issue

### Neutral / Aggressive
Lead with what changed:
1. **Changes made** — list each edit with before/after and line reference
2. **Remaining issues** — items out of scope for this mode, with a note on which mode would address them
3. **Suggestions** — anything requiring manual judgement that the skill intentionally left alone
