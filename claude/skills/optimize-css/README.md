# optimize-css

A Claude Code skill that optimizes CSS for performance, low specificity, and minimal file size.

## Philosophy

Most tools treat CSS optimization as a linting problem — flag issues, suggest fixes, leave the rest to the developer. This skill treats it as a **build step**.

Source code is semantic by design. Readable class names, tokens, comments, nested selectors — these exist for the developer, during the small percentage of a component's lifecycle where a human is actively reading or modifying it. The rest of the time, that CSS is being served, parsed, and evaluated by a browser that doesn't care what the class names mean.

This skill is a **pre-commit refactoring tool** — like Prettier or ESLint, but for CSS structure. You run it locally, review the output, and commit the result. The rest of the pipeline (PostCSS, minifier, CI/CD) stays deterministic and AI-free.

```text
developer runs optimize-css on src/
  → reviews output (inline comments explain every change)
  → commits
  → CI/CD: PostCSS → minifier → production
```

The output is optimized for the browser, not for the next developer who opens the file. Readability of the output is not a goal — that's the source's job. AI does not run in the pipeline.

## Modes

| Flag | Name | What it does |
| --- | --- | --- |
| `-d` / `defensive` | Defensive | Report only — no edits made |
| `-n` / `neutral` | Neutral | Safe CSS-only edits (default) |
| `-a` / `aggressive` | Aggressive | Full rewrites, edits CSS and HTML |

**Neutral** is the default and safe starting point. It consolidates media queries, moves keyframes, and removes redundant declarations — nothing that changes semantics.

**Aggressive** goes further: it flattens CSS nesting, renames tag selectors to explicit classes (requires HTML), applies the private layout var pattern, extracts brand tokens, and compacts selectors with `:is()`/`:where()`. This is the production build step.

**Defensive** is for audits — full report with line references, no changes made.

## What it optimizes

### Phase 0 — Pre-flight detection

Before any optimization runs, the skill identifies what it is looking at:

- **Bail-out**: utility-first frameworks (Tailwind, UnoCSS) are detected via `@tailwind`, `@apply`, or class-per-property density. The skill stops immediately — optimization does not apply to utility-first CSS.
- **Dialect**: plain CSS proceeds fully. SCSS proceeds with scope limits (see below). SASS indented syntax and LESS are not yet supported — the skill stops and reports.
- **SCSS scope**: `@mixin`, `@function`, `@include`, `@extend`, `%placeholder`, `$variable`, `#{interpolation}`, and `!default` variables are marked out-of-scope. No phase touches them.

The skill is **convention-agnostic** — it works regardless of naming convention (BEM, SMACSS, CUBE CSS, utility-hybrid, or none).

### Phase 1 — De-nesting

Tag selectors inside classes (`.nav a`, `.card ul`) add specificity and create fragile DOM dependencies. Aggressive mode replaces them with explicit element classes in both CSS and HTML.

### Phase 2 — Component hierarchy mapping

Internal phase. Maps parent/child relationships between components to inform where variables should be hoisted in Phase 5. Not included in the report.

### Phase 3 — Media query consolidation

Scattered MQs across a file are hard to maintain and generate redundant parse work. All MQs move to the bottom, duplicate breakpoints merge, and blocks order ascending (mobile-first). Desktop-first files (`max-width`) are flagged but not converted — that's an intentional architecture decision the skill respects.

### Phase 4 — Keyframe placement

`@keyframes` blocks belong at the bottom, after media queries. Mid-file keyframes are moved.

### Phase 5 — Variable extraction

CSS custom properties reduce cascade recalculation when overriding values at breakpoints — setting a variable is cheaper than redeclaring a property. But not every value benefits from tokenization.

The **cost/benefit gate** only substitutes when one of these is true:

1. **Selector elimination** — substitution empties a MQ selector (removes a cascade entry entirely)
2. **Brand/identity property** — `color`, `background-color`, `font-family`, `border-color` — a single source of truth matters more than bytes
3. **Byte neutral or smaller** — `var(--name)` is shorter than the raw value (long font stacks, repeated hex values, etc.)

Structural properties (`padding`, `margin`, `gap`, `width`, etc.) are left as raw values unless selector elimination applies — or the **private layout var pattern** applies.

#### Private layout var pattern

For structural properties orchestrated across breakpoints, a private variable (`--_` prefix) moves the override out of the property declaration:

```css
/* before */
.hero { padding: var(--spacing-md); }
@media (min-width: 768px) { .hero { padding: var(--spacing-lg); } }

/* after */
.hero { padding: var(--_hrp, var(--spacing-md)); }
@media (min-width: 768px) { .hero { --_hrp: var(--spacing-lg); } }
```

The property now appears once. The MQ only sets a variable. The `--_` prefix signals the var is internal — not part of the component's public API.

Variable naming: `--_` + selector abbreviation (max 3 chars) + property abbreviation (max 3 chars). Example: `.hero` + `padding` → `--_hrp`.

## Design decisions

**Why not just use a minifier?**
Standard minifiers strip whitespace and comments. They don't understand the cascade, can't identify dead MQ selectors, and don't know that `transition: all` on 50 elements is a performance liability. Semantic awareness is the gap this skill fills.

**Why flag `transition: all`?**
Every `transition: all` triggers recalculation for every animatable property on every state change, including layout-affecting properties. Replacing with specific property transitions (or a `--transition-base` token scoped to `opacity`, `color`, `transform`) reduces paint work on lower-end devices.

**Why leave desktop-first MQs alone?**
Converting `max-width` to `min-width` rewrites the cascade logic, not just the syntax. That's an architectural decision with UX implications — the skill flags it and defers to the developer.

**Why the `--_` prefix for private vars?**
Convention signals intent. A var prefixed `--_` communicates "this is internal to this component, don't override it from outside." It's the CSS equivalent of a private field. No enforcement mechanism, but clarity for anyone reading the source.

## Traceability

The optimize-css step annotates its changes with inline comments:

```css
/* [optimize-css] de-nested from: .component { .title { … } } */
.component .title { color: var(--col2); }

/* [optimize-css] removed dead rule — color: #00ff00 overridden by #ff00ff (source order) */

@media(width>521px) {
  /* [optimize-css] merged from L13, L23, L28 */
}
```

These comments serve the review step — the developer reads what changed and why before committing. PostCSS preserves them; the minifier strips them. No separate changeset file needed, no tooling required to read them.

The obfuscation step (separate skill) is the exception: class name changes (`pricing-card__feature` → `a1b`) cannot be expressed usefully inline, so that step generates a proper sourcemap for devtools.

## Planned

See [BACKLOG.md](BACKLOG.md) for the full roadmap.
