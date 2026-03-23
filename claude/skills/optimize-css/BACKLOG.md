# BACKLOG / IDEAS

## Must Have

- Integrate remaining TODO checks into the appropriate phases (each needs a spec addition in SKILL.md + test scenario):
  - `!important` → Phase 1 (de-nesting often resolves the specificity conflict causing it)
  - Specificity & cross-block coupling → Phase 1 / Phase 2
  - Dead CSS → Phase 1 (after de-nesting, orphaned selectors become visible; aggressive mode only — requires HTML)
  - Wildcard / structural selectors → Phase 1

## Should Have

- Group CSS vars that seem general (colors, typography, spacing used across multiple unrelated components) and suggest moving them to a global or base stylesheet via a comment.
- Hoist CSS vars to the appropriate parent level based on the component hierarchy map (Phase 2 → Phase 5).
- Private layout var pattern: for structural/layout properties (`padding`, `margin`, `gap`, etc.) on components designed to be orchestrated from outside, introduce a private var using the `--_` prefix convention. Name using 2–3 chars from the component name + 1–2 chars for the property (e.g. `.card` + `padding` → `--_crdp`). Use a nested fallback to preserve the global token connection: `padding: var(--_crdp, var(--spacing-md))`. MQ overrides then only set the private var: `--_crdp: var(--spacing-lg)`. Benefits: the actual property appears once, MQ lines are shorter, and the `--_` prefix signals the var is internal to the component (not part of its public API). Needs heuristic to detect layout-orchestrated components — likely requires Phase 2 hierarchy context.

## Should Have (continued)

- Selector compaction using `:is()` and `:where()`: after MQ consolidation, identify groups of selectors in the same block that share identical declarations and can be merged. Use `:is()` when the highest specificity in the group should be preserved (e.g. `.component` and `.component .title` both setting `font-family` → `:is(.component, .component .title)`). Use `:where()` when zero specificity is explicitly desired. Flag cases where the specificity change would alter the cascade.

## Should Have (patterns)

- **Orphan utility selectors in MQ** — `.v-margin`, `.v-padding` and similar layout utilities that have no parent component show up directly in media query blocks (e.g. `@media (max-width: 767px) { .v-margin { margin-top: 2rem } }`). These are candidates for hoisting the value to a `:root`-level var override: declare the base value as a custom property on `:root`, update the utility class to use `var()`, and reduce the MQ block to `@media (…) { :root { --vm: 2rem } }`. This is Phase 5 with `:root` as the parent — the spec currently only hoists to component parents. Needs a cost/benefit gate (var name overhead vs. repetition count). Aggressive only.

## Should Have (config) ← next sprint candidate

- Settings file (`optimize-css.config.json`) in the project root. Needed for correctness, not just convenience — some skill decisions are ambiguous without user intent. CLI arguments take precedence. Key settings identified so far:
  - `duplicate_vars: yes | no | ask` — controls Phase 6 Class 3 behavior: when two tokens share the same value, should the skill consolidate them automatically (`yes`), flag only (`no`), or pause and ask per pair (`ask`)? Default: `no` (flag only). **Why this matters:** company guidelines or design systems may require specific naming even when values coincide — e.g. `--color-interactive` and `--color-brand` might both be `#aa0005` today but diverge on a rebrand. Auto-merging would silently couple them.
  - `mode: defensive | neutral | aggressive` — default mode when no flag is passed
  - `mobile_first: true | false` — declare the file's intended viewport strategy; prevents incorrect desktop-first flagging
  - `ignore_prefixes: []` — class prefixes the skill should never touch (e.g. `woocommerce-`, `yith-`)
  - `phases: []` — opt individual phases on/off
  - Start small: first version only needs `duplicate_vars` and `mode` to be immediately useful

## Could Have

- Rewrite to Mobile First: detect desktop-first patterns (max-width queries, base styles assuming large screen) and convert the file to a mobile-first structure — base styles become the smallest viewport, queries become min-width ascending.
- SCSS deeper support: beyond scope identification (Phase 0), handle SCSS-specific optimization opportunities — e.g. detecting redundant `@include` calls, flagging `$variable` values that duplicate CSS custom properties, and identifying `@extend` chains that could be flattened.

## Research: token cost vs. file size (monetization data)

**Goal:** establish a cost-per-run model as a pricing foundation for a potential web service.

### What drives token cost

Every run has three cost components:

| Component | Scales with | Notes |
| --- | --- | --- |
| SKILL.md (system prompt) | Fixed | ~500 lines / ~6 500 tokens per run — always paid |
| CSS input file | File size | ~1 token per 4 chars; a 90 KB file ≈ 22 500 tokens |
| Output (edits + report) | Mode + change density | Aggressive = more rewrites = more output tokens; defensive is cheapest |

Input tokens dominate. A large CSS file will cost roughly 3–4× more to process than a small one regardless of mode.

### Wildtest.css baseline (2026-03-23 session)

| Metric | Value |
| --- | --- |
| Input file | ~2 660 lines / ~90 KB (GeneratePress child theme) |
| Mode | Aggressive |
| Sessions consumed | 3 (context window compactions occurred twice) |
| Approximate input tokens per interaction | ~30 000 (SKILL.md + file + conversation history) |
| File size reduction | Significant (Phase 3 consolidation + Phase 5 private vars removed ~200+ repeated MQ declarations) |

Exact token counts are not visible inside the tool, but Claude API users can retrieve them from the usage field on each response. **Action: instrument a test harness that logs `usage.input_tokens` and `usage.output_tokens` per API call and accumulates per file run.**

### Data to collect per run (test matrix)

- CSS file size (bytes), line count, selector count
- Mode (defensive / neutral / aggressive)
- Input tokens, output tokens, total cost at current API rate
- Number of edits made, bytes saved, phases triggered
- SKILL.md version (prompt changes affect cost)

Run at minimum: 10 KB / 30 KB / 60 KB / 100 KB files × 3 modes = 12 data points. Look for a cost curve.

### Pricing model hypotheses

1. **Per-file flat tiers** — S / M / L / XL buckets by file size. Simple to communicate, easy to charge. Risk: XL files can vary wildly in complexity.
2. **Per-KB** — linear, transparent. Predictable for the customer. Likely undercharges for aggressive mode on complex files.
3. **Per-KB × mode multiplier** — e.g. 1× defensive, 1.5× neutral, 2.5× aggressive. Closer to actual cost. May confuse users.
4. **Token-pass-through + margin** — charge actual API cost + X%. Developer-friendly, honest. Requires per-user API cost tracking.
5. **Credits** — pre-buy credits, 1 credit ≈ 10 KB in neutral mode. Familiar SaaS pattern; hides the per-token math.

**Hypothesis to test first:** flat tiers cover 80% of real-world files (most stylesheets are under 100 KB). A three-tier model (< 30 KB / 30–100 KB / > 100 KB) × mode may be sufficient for v1 pricing.

### Open questions

- Does SCSS with many `@mixin` / `@include` blocks cost more (more tokens skipped, same input cost)?
- What is the realistic p95 file size for a production stylesheet? (Anecdote: wildtest is ~90 KB unminified, which is large but not unusual for a page-builder-adjacent theme.)
- Minified vs. unminified input: minified files are smaller but harder to read — does output quality drop enough to require unminified input?

## Would Have

- Multi-file mode: accept a folder or list of files and cross-reference selectors across them before flagging dead CSS or suggesting token moves.
- `@property` suggestions: for custom properties used in animations or transitions, suggest typed `@property` declarations for better performance and interpolation.
- Plugin/framework ignore list: accept a list of class prefixes (e.g. `woocommerce-`, `yith-`, `tinv-`, `wapf-`, `bapf_`, `dgwt-`, `irs--`) that the skill should never rename, flag for de-nesting, or attempt to restructure. Phase 1 should skip or annotate selectors matching these prefixes rather than suggesting class renames. Can be passed as a CLI argument or defined in config. Default set of known WordPress/WooCommerce prefixes can be built in.
- Selector obfuscation: a post-processing step (separate skill) that replaces human-readable class names with short opaque codes (e.g. `.pricing-card__feature--disabled` → `.a1b`) across CSS and HTML simultaneously, generating a sourcemap so the transform is reversible. This is a performance optimization — shorter selectors reduce file size and parsing time. Preconditions: styling must be stable, the project must own both CSS and HTML. Assumed convention: classes prefixed with `js-` are never styled and must be left untouched (they are the safe hook for JavaScript). IDs are already excluded from styling (specificity rule), so they are out of scope too.
