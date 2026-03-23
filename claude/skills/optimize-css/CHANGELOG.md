# CHANGELOG — optimize-css

## Versioning convention

Pre-release versions use a single decimal (`0.10`, `0.91`, …). Each session that adds or changes something increments by `0.01`.

From v1.0.0 onward: **semantic versioning** — `v[MAJOR].[MINOR].[PATCH]`

| Segment | Increments when… | Resets… |
| --- | --- | --- |
| MAJOR | Breaking change — a phase is removed, output format changes, config schema changes in a way that invalidates prior configs | MINOR and PATCH → 0 |
| MINOR | New feature — a phase added, an existing phase extended, a new check promoted from TODO | PATCH → 0 |
| PATCH | Bug fix — incorrect annotation, edge case correction, wording fix, wrong default behavior | — |

---

## Pre-release history

### 0.94 — 2026-03-23

- Added `browser_targets` setting: `modern | broad | legacy` (default: `broad`) — gates which modern CSS features the skill may suggest or apply
- Feature gate table added: `@scope`, `@layer`, `color-mix()`, `oklch`, nesting, container queries — each mapped to `legacy/broad/modern` tier and minimum browser versions
- Phase 5 private layout var threshold corrected: was "base value must use a global token" → now "property overridden in 3+ MQ blocks" regardless of whether base value is a raw value or token
- `@scope` + private var synthesis pattern added to Phase 5: documents how `@scope` (base rules) and private vars (MQ overrides) combine cleanly — `@scope` is transparent to custom property inheritance

### 0.93 — 2026-03-23

- New config format: every setting is an object with `info`, `default`, and optional `options` keys — `info` surfaces in the report header and replaces JSON's missing comment syntax
- Added `confirm_generated` setting: `yes | no | ask` (default: `ask`) — applies to all generated/theme-managed file detections, not just WordPress
- `confirm_generated.options`: per-signal overrides (e.g. `"wordpress": "no"`)
- Confirmation prompt accepts `y / n / -d / -n / -a` — user can switch mode on the spot without re-running
- Phase 0 WordPress and page builder sections now both delegate to `confirm_generated` instead of having hardcoded behaviors
- Updated scenario 08 config to new object format
- Dropped plain string shorthand for config values — object format only

### 0.92 — 2026-03-23

- Extended Phase 1 shared base extraction: pattern now explicitly covers MQ blocks (not just base rules)
- Added tag selector exception: semantic elements (`h2`, `p`, `li`) scoped to a stable container are acceptable extraction targets — annotate to prevent future de-nesting flags

### 0.91 — 2026-03-23

- Added Phase 5 second-pass: multi-selector breakpoint ladder detection (adopt existing `:root` var ladder across additional selectors)
- Added Phase 1: shared base extraction pattern (`.gb-button` lesson — 3+ components sharing identical sub-element declarations)
- Extended Phase 1 `!important` Case 3: theme builder inline styles explicitly named as external conflict sources
- Added Phase 3 tooling note: reference script for files with 50+ scattered `@media` blocks (`tools/phase3-consolidate-mq.py`)
- Added `tools/phase3-consolidate-mq.py` — brace-counting Phase 3 reference implementation with inline adaptation notes
- Versioning convention established; CHANGELOG created

### 0.9 — 2026-03-23

- Integrated wildcard/structural selector detection into Phase 1 (flag `> *`, `* + *`, `* ~ *`, `.card *`; `:warn` only, no auto-fix)
- Integrated `!important` detection into Phase 1 (Cases 1–3: unnecessary, in-file conflict, external conflict)
- Added Phase 6: token consolidation (Class 1 hardcoded→token, Class 2 repeated raw value, Class 3 near-duplicate tokens)
- Added `duplicate_vars` config setting controlling Phase 6 Class 3 behavior
- Added Step 1b config loading (`optimize-css.config.json`, upward directory search)
- Added TODO section: specificity, dead CSS, `inset` shorthand, `transition: all`, `background-size` without image, var name length limit, responsive typography vars

### 0.8 — 2026-03-23

- Added Phase 0 warn: WordPress / CMS theme file header detection (`Theme Name:`, `Template:`, `Plugin Name:`) — warn + proceed, do not bail
- Added page builder bail-out detection (Elementor, Divi, Beaver Builder, WPBakery, Oxygen, Bricks)
- Established `[optimize-css]`, `[optimize-css:warn]`, `[optimize-css:blocked]` annotation tag system
- Added cross-referencing requirement between `:warn` and `:blocked` tags

### 0.7 and earlier

_Pre-changelog. Core phases established: Phase 0 dialect detection, Phase 1 de-nesting, Phase 2 hierarchy mapping, Phase 3 MQ consolidation, Phase 4 keyframe placement, Phase 5 variable extraction (brand/identity + private layout var pattern), report structure._
