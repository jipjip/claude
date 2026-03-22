---
name: optimize-css
description: Optimize CSS for performance, low specificity, and minimal file size. Supports three modes — defensive (report only), neutral (safe CSS-only edits, default), aggressive (full rewrites including HTML). Use when a user requests optimization of CSS, SCSS, or inline styles.
argument-hint: "[-d|-n|-a | defensive|neutral|aggressive] <file>"
license: Complete terms in LICENSE.txt
metadata:
  author: JipJip.com
  version: "0.6"
---

Review and optimize the CSS in `$ARGUMENTS`.

## Step 1 — Determine mode and target

### 1a — Parse arguments

Parse `$ARGUMENTS`:
- If the first word is a mode flag, extract it and treat the remainder as the target file(s).
  - Defensive: `defensive` or `-d` → report only, no edits
  - Neutral: `neutral` or `-n` → safe CSS-only edits (default)
  - Aggressive: `aggressive` or `-a` → full rewrites, edits CSS and HTML
- If no mode flag is present, mode is not yet set — check config next.
- The remaining argument(s) are the target file path(s).

In aggressive mode, also search for a corresponding HTML file alongside the CSS target to enable dead CSS checks and HTML edits.

### 1b — Load config

Look for `optimize-css.config.json`, searching from the target file's directory upward to the project root (first file found wins). If no config is found, all settings use their defaults.

Supported settings (v1):

| Setting | Values | Default | Effect |
| --- | --- | --- | --- |
| `mode` | `defensive` \| `neutral` \| `aggressive` | `neutral` | Default mode when no CLI flag is passed. CLI flag takes precedence. |
| `duplicate_vars` | `yes` \| `no` \| `ask` | `no` | Controls Phase 6 Class 3 behavior — see Phase 6 for details. |

**Precedence:** CLI flag > config file > default.

If a config file is found, note it in the report header so the developer knows which settings are active.

## Step 2 — Pre-flight detection (Phase 0)

Before running any optimization phase, identify what the file is and whether it can be processed. If Phase 0 fails, stop immediately — do not proceed to the optimization phases.

### Bail-out: utility-first frameworks

If any of the following are detected, stop and report — the skill does not apply:

- `@tailwind` directive (any variant: `base`, `components`, `utilities`)
- `@apply` with utility class names
- A class-per-property density suggesting utility-first output (e.g. `.flex`, `.p-4`, `.text-sm`, `.bg-blue-500`)

Report which framework was detected and why optimization does not apply.

### Dialect detection

Identify the CSS dialect from extension and content:

| Dialect | Signals | Supported |
| --- | --- | --- |
| Plain CSS | `.css`, no preprocessor syntax | Yes |
| SCSS | `.scss`, `$variable`, `@mixin`, `@include`, `&` nesting with braces | Yes — see scope below |
| SASS (indented) | `.sass`, indented syntax without braces or semicolons | No — stop and report |
| LESS | `.less`, `@variable: value`, `.mixin()` calls | No — stop and report |

### SCSS scope identification

If SCSS is detected, mark these constructs as out-of-scope before any phase runs. Do not edit, rename, or flag them:

- `@mixin` and `@function` blocks — reusable patterns, skip entirely
- `@include` calls — mixin invocations, output is dynamic
- `@extend` and `%placeholder` selectors — complex specificity implications, skip
- `$variable` declarations — the source token system, do not touch
- `#{interpolation}` — dynamic selector fragments, unpredictable output
- Variables flagged `!default` — library convention, hands off

Report what was detected and what will be skipped before proceeding to Phase 1.

## Step 3 — Optimization process

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
  - Double-underscore separator (`__`) → abbreviate both parts: `.footer__nav` → `fn`
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

### Phase 6 — Token consolidation

Scan the full file for three classes of issues. In SCSS files, only CSS custom properties (`--var`) are in scope — `$variable` declarations are out-of-scope and are not touched.

**Class 1 — Hardcoded value matches an existing token**

For each `--custom-property: value` declared in the file, scan all other declarations for the same raw value used as a literal. Flag each occurrence as "should be `var(--token-name)`".

- **Neutral**: substitute — token already exists, this is a safe reference fix.
- **Aggressive**: substitute.
- **Defensive**: flag with the suggested substitution.

**Class 2 — Repeated raw value with no token**

Find raw values appearing more than once where creating a token would be byte-neutral or shorter. Apply threshold by property type:

- Brand/identity properties (`color`, `background-color`, `font-family`, `border-color`): flag at 2+ occurrences.
- All other properties: flag at 3+ occurrences.

Only flag if the value is long enough to warrant a token (value length > suggested var name + `var()` overhead).

Suggest a token name and the correct scope to declare it (`:root` for global, or the nearest shared ancestor selector for component-scoped).

- **Neutral**: flag only — do not create new tokens.
- **Aggressive**: create the token at the suggested scope and substitute all occurrences.
- **Defensive**: flag with suggested token name and declaration.

**Class 3 — Near-duplicate tokens**

Find two or more `--custom-property` declarations that share the same value. Flag them as near-duplicates — they may have different semantic intent (e.g. `--color-interactive` and `--color-brand` might both be `#aa0005` today but diverge on a rebrand).

Behavior is controlled by the `duplicate_vars` setting (default: `no`):

- **`no`** (default): flag the pair only, no edits. If a raw value (Class 1) matches both tokens, defer that substitution too — report it as blocked pending duplicate resolution.
- **`yes`**: pick the more semantically specific name (a name describing *purpose* beats one describing *appearance* — e.g. `--brand-red` over `--color-dark`), delete the losing declaration, and apply any matching Class 1 substitutions using the winning token. Annotate the deletion with `/* [optimize-css] removed duplicate --losing-name — same value as --winning-name (duplicate_vars: yes) */`.
- **`ask`**: for each near-duplicate pair, present both names and their value, ask which to keep, then proceed as `yes` with the chosen winner.

Until a config file is supported, default to `no` and note in the report that `duplicate_vars: yes` would resolve this automatically.

## TODO

Integrate these checks into the appropriate phases above.

### `!important`
Flag every usage. Determine whether it exists because of a specificity conflict, and if so identify the conflicting selector and the structural fix.

### Specificity
- Flag selectors that climb specificity unnecessarily (chained classes, tag qualifiers, deep descendant selectors).
- Flag modifiers that rely on parent context to work (e.g. `.parent.is-active .child-element`).
- Flag cross-block coupling: one component's state overriding another component's styles (e.g. `.card.is-highlighted .button`).

### Dead CSS
- Flag selectors with no matching element in the HTML (aggressive mode only — requires HTML file).
- In neutral/defensive mode, note that dead CSS check was skipped (no HTML available).

### Wildcard / structural selectors
- Flag `> *`, `* + *`, and similar structural selectors that create invisible specificity or fragile DOM dependencies. Suggest named elements instead.

## Step 4 — Report

Structure output differently per mode:

### Defensive
Full report, no changes made:
1. **Issues found** — grouped by phase, each with line references
2. **Suggested fixes** — concrete rewrites for each issue

### Neutral / Aggressive
For every edit or notable condition, add an inline comment using one of three tags. Place it on the line directly above the affected declaration or block.

**Tag variants:**

- `/* [optimize-css] … */` — a change was made. State what and why in one line.
- `/* [optimize-css:warn] … */` — something needs attention but no edit was made (e.g. near-duplicate token, desktop-first MQ). Cross-reference any lines it affects.
- `/* [optimize-css:blocked] … */` — the skill wanted to make an edit but couldn't. State why and what to do to unblock. Cross-reference the source of the block.

**Cross-referencing:** when a `:warn` and a `:blocked` are related, each should name the other's location. The developer should be able to understand the full picture from either comment without reading the report.

**Examples:**

```css
/* [optimize-css] de-nested from: .component { .title { … } } */
/* [optimize-css] merged from L13, L23, L28 */
/* [optimize-css] removed dead rule — color: #00ff00 overridden by #ff00ff (source order) */
/* [optimize-css] extracted font-family stack → --ff-serif */
/* [optimize-css] private var --_hrp introduced for padding (overridden in 2 MQs) */
/* [optimize-css:warn] near-duplicate: --gray-dark and --color-dark share #1a1a1a — blocks background-color in .header (L23) */
/* [optimize-css:blocked] #1a1a1a matches --gray-dark + --color-dark (L18–L19) — resolve duplicate or set duplicate_vars: yes */
```

These comments are greppable and cost nothing in production — PostCSS preserves them, the minifier strips them:
- `grep '[optimize-css]'` — all activity
- `grep '[optimize-css:warn]'` — all attention items
- `grep '[optimize-css:blocked]'` — all deferred edits with reasons

Then output the conversation report:
1. **Changes made** — list each edit with before/after and line reference
2. **Remaining issues** — items out of scope for this mode, with a note on which mode would address them
3. **Suggestions** — anything requiring manual judgement that the skill intentionally left alone
