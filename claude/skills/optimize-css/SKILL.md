---
name: optimize-css
description: Optimize CSS for performance, low specificity, and minimal file size. Supports three modes — defensive (report only), neutral (safe CSS-only edits, default), aggressive (full rewrites including HTML). Use when a user requests optimization of CSS, SCSS, or inline styles.
argument-hint: "[-d|-n|-a | defensive|neutral|aggressive] <file>"
license: Complete terms in LICENSE.txt
metadata:
  author: JipJip.com
  version: "0.3"
disable-model-invocation: true
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

For each property override inside a media query selector:
- Check if the value can be expressed as a CSS custom property.
- If yes, initialize the variable on the component root with the base (mobile-first) value, and override only the variable inside the media query.
- Use the component hierarchy from Phase 2 to determine the right level to initialize the variable — hoist to the parent component root if the child lives inside one.
- If all property overrides in a media query selector are replaced this way, the selector may become obsolete — remove it if so.

**Neutral**: only replace with variables that already exist in the file. Do not create new tokens.
**Aggressive**: create new tokens where needed. Remove selectors that become empty after extraction.
**Defensive**: flag opportunities, suggest token names and initialization values, no edits.

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
