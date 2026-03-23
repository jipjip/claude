---
name: optimize-css
description: Optimize CSS for performance, low specificity, and minimal file size. Supports three modes — defensive (report only), neutral (safe CSS-only edits, default), aggressive (full rewrites including HTML). Use when a user requests optimization of CSS, SCSS, or inline styles.
argument-hint: "[-d|-n|-a | defensive|neutral|aggressive] <file>"
license: Complete terms in LICENSE.txt
metadata:
  author: JipJip.com
  version: "0.95"
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

**Config format:** every setting is an object with three keys:

```json
{
  "setting-name": {
    "info": "Human-readable note — shown in the report header and serves as documentation inside the file (JSON has no comment syntax).",
    "default": "the-value",
    "options": {
      "per-signal-key": "override-value"
    }
  }
}
```

- `info` — optional but encouraged. Surfaced in the report so the developer's intent travels with the run.
- `default` — the active value for this setting.
- `options` — optional. Per-signal overrides (see `confirm_generated` below).

**Supported settings:**

| Setting | Values | Default | Effect |
| --- | --- | --- | --- |
| `mode` | `defensive` \| `neutral` \| `aggressive` | `neutral` | Default mode when no CLI flag is passed. CLI flag takes precedence. |
| `duplicate_vars` | `yes` \| `no` \| `ask` | `no` | Controls Phase 6 Class 3 behavior — see Phase 6 for details. |
| `confirm_generated` | `yes` \| `no` \| `ask` | `ask` | What to do when a generated or theme-managed file is detected. `yes` = proceed, `no` = bail out, `ask` = prompt the user. Use `options` for per-signal overrides. |
| `browser_targets` | `modern` \| `broad` \| `legacy` | `broad` | Gates suggestions and edits that require specific browser support. See feature gate table below. |

**`confirm_generated` in detail:**

When a generated file signal is detected (WordPress theme header, page builder output), behavior depends on this setting:

- **`yes`** — proceed without prompting.
- **`no`** — bail out immediately. No edits, no warning comment added.
- **`ask`** (default) — pause and prompt:

```
[optimize-css] WordPress child theme detected (Template: generatepress).
Manual edits may be overwritten on theme update.
Proceed? [y / n / -d / -n / -a]
  y    proceed in current mode
  n    quit — no changes made
  -d   proceed in defensive mode (report only, safest)
  -n   proceed in neutral mode
  -a   proceed in aggressive mode

Tip: set "confirm_generated": { "default": "yes" } in optimize-css.config.json to skip this prompt.
```

Use `options` to set per-signal behavior that differs from `default`:

```json
{
  "confirm_generated": {
    "info": "Editing generated CSS risks losing compatibility. 'no' is the safest option.",
    "default": "ask",
    "options": {
      "wordpress": "no",
      "elementor": "no"
    }
  }
}
```

Valid signal keys for `options`: `wordpress`, `elementor`, `divi`, `beaver`, `wpbakery`, `oxygen`, `bricks`.

**`browser_targets` in detail:**

Controls which modern CSS features the skill may suggest or apply. Default is `broad` — covers the large majority of live traffic without requiring cutting-edge support.

| Feature | `legacy` | `broad` | `modern` | Minimum browsers |
| --- | --- | --- | --- | --- |
| CSS custom properties | suggest only | ✓ apply | ✓ apply | Chrome 49+, FF 31+, Safari 9.1+ |
| `@scope` | ✗ skip | suggest only | ✓ apply | Chrome 118+, FF 128+, Safari 17.4+ |
| `@layer` | ✗ skip | ✗ skip | suggest only | Chrome 99+, FF 97+, Safari 15.4+ — multi-file risk, see backlog |
| `color-mix()` | ✗ skip | suggest only | ✓ apply | Chrome 111+, FF 113+, Safari 16.2+ |
| `oklch()` / `oklch` colors | ✗ skip | suggest only | ✓ apply | Chrome 111+, FF 113+, Safari 15.4+ |
| Nesting (`&`) | ✗ skip | suggest only | ✓ apply | Chrome 112+, FF 117+, Safari 16.5+ |
| `container` queries | ✗ skip | suggest only | ✓ apply | Chrome 105+, FF 110+, Safari 16+ |

When a feature is gated as "suggest only", include an `[optimize-css:warn]` comment on the suggestion line naming the `browser_targets` setting and the minimum browser requirement. Do not apply the edit.

**Precedence:** CLI flag > config file > built-in default.

If a config file is found, include its path, active settings, and any `info` values in the report header:

```
Config: optimize-css.config.json
  duplicate_vars: yes
  confirm_generated: ask (wordpress: no)

  duplicate_vars — Will merge duplicate CSS custom properties that share the same value.
                   Risk: losing cross-file connections if the var is also declared globally.
  confirm_generated — Editing generated CSS risks losing compatibility. 'no' is the safest option.
```

## Step 2 — Pre-flight detection (Phase 0)

Before running any optimization phase, identify what the file is and whether it can be processed. If Phase 0 fails, stop immediately — do not proceed to the optimization phases.

### Bail-out: utility-first frameworks

If any of the following are detected, stop and report — the skill does not apply:

- `@tailwind` directive (any variant: `base`, `components`, `utilities`)
- `@apply` with utility class names
- A class-per-property density suggesting utility-first output (e.g. `.flex`, `.p-4`, `.text-sm`, `.bg-blue-500`)

Report which framework was detected and why optimization does not apply.

### Bail-out: page builder output

If any of the following are detected, stop and report — the file is generated output, not source CSS. Editing it directly will be overwritten on the next build or cache regeneration:

- **Elementor**: `.elementor-` prefix on the majority of selectors, `--e-a-` custom property namespace, `eicon-` keyframe or font-family references
- **Divi**: `.et_pb_` prefix, `.et-` utility selectors, inline `style` attributes referencing `et_pb` modules
- **Beaver Builder**: `.fl-` prefix throughout, `.fl-builder-` selectors
- **WPBakery**: `.vc_` or `.wpb_` prefix on the majority of selectors
- **Oxygen Builder**: `.ct-` prefix with numbered suffixes (e.g. `.ct-section-123456`)
- **Bricks Builder**: `.brxe-` prefix
- **General signal**: a class-per-layout-state density where class names encode responsive behaviour (e.g. `elementor-tablet-align-left`, `elementor-mobile_extra-align-justify`) — these are generated utility matrices, not authored styles

Apply `confirm_generated` behavior (see Step 1b). If the setting resolves to `no` or the user declines the prompt, stop here — report which builder was detected and explain that the source is the builder's settings (database, visual editor), not this file. Note the correct optimization lever (e.g. disable unused breakpoints in Elementor settings, remove unused widget types).

### Warn: WordPress / CMS theme file

If the file contains a theme file header comment (WordPress stylesheet convention), apply `confirm_generated` behavior — a hand-authored child theme is a legitimate optimization target but may be overwritten on theme update. Only hard-bail if the file is also a page builder output (both signals together = generated source).

Signals:
- `Theme Name:` in a block comment near the top of the file (WordPress `style.css` convention)
- `Template:` pointing to a parent theme (child theme indicator)
- WooCommerce or plugin stylesheet headers: `Plugin Name:`, `WC requires at least:`

**Action:** Apply `confirm_generated` (see Step 1b). If proceeding, add a single-line comment at the very top of the CSS file:

```css
/* [optimize-css:warn] WordPress theme stylesheet detected (Template: generatepress). Manual edits may be overwritten on theme update. Confirm edits are safe to commit before applying. */
```

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

### Phase 1 — De-nesting and `!important` resolution

#### De-nesting

Identify all descendant selectors and tag selectors used inside a class (e.g. `.navbar__links a`, `.footer__nav-group ul`).

- **Aggressive**: replace with explicit element classes in both CSS and HTML.
- **Neutral**: flag each one, suggest the explicit class name, but do not edit.
- **Defensive**: flag each one with the suggested class name.

#### Shared base extraction

When 3 or more component-scoped selectors target the same sub-element and share identical declarations, those declarations belong on a shared base rule — not repeated per-component.

**Detection**: scan for a sub-element class (e.g. `.gb-button`, `.wpcf7-submit`) that appears under multiple distinct parent component selectors (e.g. `.home-section1`, `.home-section2`, `.about-section5`). If 3+ instances share ≥ 3 identical property/value pairs, extract.

**Process:**
1. Create (or extend) a base rule targeting the sub-element directly: `.gb-button { … shared declarations … }`.
2. In each per-component rule, remove only the declarations now covered by the base. Leave any component-specific overrides in place.
3. Annotate both the new base rule and the stripped per-component rules.

```css
/* [optimize-css] extracted shared .gb-button base — background-color, border, border-radius, font-size, padding, transition were identical across 7 sections */
.gb-button {
    background-color: var(--main);
    border: 2px solid transparent;
    border-radius: 5px;
    font-size: 14px;
    padding: 13px 29px;
    transition: all .2s ease-in-out;
}

/* [optimize-css] base props removed — now inherited from .gb-button */
.home-section3 .inner-container .gb-button {
    display: flex;          /* section-specific only */
    margin-left: auto;
}
```

**All modes**: apply in neutral and aggressive. In defensive, flag with the suggested base rule.

**Applies inside MQ blocks too**: the same pattern occurs within a breakpoint — many selectors in the same `@media` block all setting the same property on the same sub-element. Extract to a single scoped rule inside that block. Cascade handles exceptions that already have higher specificity.

**Tag selector exception**: when the repeated target is a semantic HTML element (`h2`, `p`, `li`, etc.) rather than a class, a scoped tag selector is acceptable as the extraction result — provided it is scoped to a stable container class (e.g. `.inner-container h2`). This is the one case where a tag selector descendant is produced intentionally rather than flagged. Annotate clearly so it is not later mistaken for a de-nesting candidate:
```css
/* [optimize-css] responsive typography reset — all .inner-container h2 → 25px; exceptions override via higher specificity */
.inner-container h2 { font-size: 25px; }
```

**⚠ Cross-pass interaction — tag selector consolidation + @scope (critical):** Before extracting, check whether any of the affected sections also have a base rule targeting the same property inside an `@scope` block. If so, compute the @scope inner selector's specificity (scope root excluded) and verify the consolidated selector is at least as specific. See `@scope` section below for the full safety check and failure mode.

#### Wildcard / structural selectors

Scan for selectors containing universal wildcards used as structural tools:

- `> *` — universal direct child
- `* + *` — adjacent universal sibling (lobotomised owl pattern)
- `* ~ *` — general universal sibling
- `*` as the sole or primary target (e.g. `.card *`)

For each match, flag with `[optimize-css:warn]`. State what elements are likely targeted (infer from context where possible) and suggest a named alternative. No automatic fix — naming elements requires knowing developer intent.

Note when the lobotomised owl (`* + *`) is detected: it is a known intentional pattern. Flag it but acknowledge the intent.

No edits in any mode — `:warn` only.

```css
/* [optimize-css:warn] > * targets all direct children of .card — fragile if new elements are added; name the intended children instead (e.g. .card__content) */
.card > * { margin-bottom: 16px; }

/* [optimize-css:warn] * + * (lobotomised owl) — targets every sibling pair inside .nav; intentional pattern but fragile; consider .nav__item + .nav__item */
.nav * + * { margin-left: 8px; }
```

#### `!important` detection

Scan every declaration with `!important`. For each one, determine which case applies:

For each `!important`, first check for dead rules it creates, then determine the case.

**Pre-check — dead rules caused by `!important`**: if a lower-specificity rule with `!important` makes a higher-specificity rule for the same property unreachable, that higher-specificity rule is dead. Remove the dead declaration first (neutral/aggressive), then re-evaluate the `!important` — it will often collapse to Case 1. Assume the `!important` reflects developer intent; the dead rule is the collateral damage to clean up.

**Case 1 — Unnecessary**: after any dead rule removal, no higher-specificity conflicting rule remains in the file. The `!important` wins unconditionally and adds no value.
- **Neutral/Aggressive**: remove the `!important`. Annotate: `/* [optimize-css] removed unnecessary !important — no conflicting rule in file */`
- **Defensive**: flag with suggested removal.

**Case 2 — Conflict within this file**: a more specific selector in the same file sets the same property and would otherwise win, and it is not dead. Identify the conflicting selector and suggest the fix.
- **Neutral**: log `[optimize-css:warn]` naming the conflicting selector. Do not edit.
- **Aggressive**: if de-nesting the conflicting rule unambiguously resolves it, apply the de-nest and remove the `!important`.
- **Defensive**: flag with the conflicting selector identified and the suggested fix.

**Case 3 — Ambiguous or likely external**: no conflicting rule in this file, but the selector pattern or context suggests an external conflict. External sources include:
- Plugin or framework class prefixes (e.g. `wc-`, `elementor-`)
- Theme builder–injected inline styles (e.g. GeneratePress page hero `max-width: calc(...)`, Astra container widths) — these appear in the page DOM, not the stylesheet, and cannot be seen in the CSS file
- JavaScript-set styles

When a base `!important` exists across many breakpoints for a structural property like `max-width`, and no conflicting rule appears in the file, inline styles are the most likely source. Note this in the warning.

- **All modes**: log `[optimize-css:warn]`. State that the conflict is likely external and cannot be safely resolved. Do not edit.

Example annotations:
```css
/* [optimize-css] removed dead rule — color: blue unreachable, .button color: red !important always wins */
/* .card .button { color: blue; } */

/* [optimize-css] removed unnecessary !important — no conflicting rule remains after dead rule removal */
color: red;

/* [optimize-css:warn] !important — conflict likely external (wc- prefix suggests WooCommerce); do not remove without checking plugin CSS */
color: green !important;
```

#### Specificity reduction via `@scope`

For components with many deeply-nested selectors, wrapping the component's base rules in `@scope (.component)` removes the section prefix from every selector's specificity — the scope root is not counted in specificity matching. The actual selectors become shorter; each rule drops one specificity unit.

**When to apply (aggressive mode + `browser_targets: modern` only):**
- Component has ≥ 3 nested rules at depth 3+ (e.g. `.section .inner-container .wrapper .element`)
- Component is bounded by a single root class with no naming conflicts
- The component does not need its base rules overridden by anything outside it with lower specificity

**Process:**
1. Leave the root rule outside: `.home-section3 { padding-top: 80px; }`
2. Wrap all nested rules in `@scope (.home-section3) { … }` and strip the `.home-section3` prefix from each inner selector
3. Annotate with specificity delta and browser requirement:
```css
/* [optimize-css] @scope reduces selector depth; deepest rule drops from 0,3,1 to 0,2,1 */
/* [optimize-css:warn] @scope requires Chrome 118+, Safari 17.4+, Firefox 128+ — verify browser targets before deploying */
@scope (.home-section3) {
    .inner-container .gb-grid-wrapper { … }
}
```

**`@scope` and CSS custom property inheritance:** `@scope` is transparent to custom property inheritance. A var set on `.section { --_var: value; }` outside the scope still resolves normally inside the scoped rules. MQ overrides that set vars on the component root work correctly.

---

**⚠ Cross-pass interaction — `@scope` + shared base extraction (critical)**

These two techniques are mutually constraining when they target the same property on the same element type. Applied together without a specificity check, they can silently reverse the intended cascade — MQ overrides stop overriding.

**The failure mode (observed in wildtest.css):**

| | Before | After consolidation | After @scope |
|---|---|---|---|
| Base rule | `.section .inner-container .wrapper>div h2 { font-size: 36px }` **(0,3,1)** | unchanged | `@scope (.section) { .inner-container .wrapper>div h2 }` **(0,2,1)** |
| MQ override | `.section .inner-container .wrapper>div h2 { font-size: 25px }` **(0,3,1)** | `.inner-container h2 { font-size: 25px }` **(0,1,1)** | unchanged |
| Result at MQ | MQ wins (same specificity, later source) ✓ | MQ wins (0,3,1 vs 0,1,1) ✓ | **@scope base wins (0,2,1 vs 0,1,1) ✗** |

Both transforms are individually correct. Combined, the @scope base rule outranks the consolidated MQ override and the MQ override silently fails.

**Safety check — before applying shared base extraction to an MQ override:**
1. For each section whose selector is being consolidated, check if that section has (or will have) an `@scope` base rule for the same property.
2. Compute the @scope inner selector's specificity (exclude the scope root).
3. If the consolidated selector's specificity is lower: **do not consolidate** — keep the per-section MQ selector at its original specificity. Alternatively, adjust the consolidated selector to match the @scope inner selector's depth.

**Safety check — before applying `@scope` to a section:**
1. For each property in the component's base rules, check if any MQ override for that property has already been consolidated to a lower-specificity selector.
2. Compare the @scope inner selector's specificity (scope root excluded) against the consolidated MQ selector's specificity.
3. If the inner selector is more specific: the MQ override will silently fail. Options:
   - (a) Restore the per-section MQ selector at its original specificity — do not consolidate for this section
   - (b) Flatten the @scope inner selector to match or fall below the consolidated MQ rule's specificity
   - (c) Flag with `[optimize-css:warn]` and leave for manual resolution

**Ordering rule:** When both techniques are applied in the same session, verify the full specificity relationship after both passes complete — not just at each pass independently.

---

### Phase 2 — Component hierarchy mapping

Identify the parent block of each component. If a component is used inside another component, note the relationship — it informs where CSS variables should be hoisted in Phase 5.

No edits are made in this phase. Do not include the map in the report.

### Phase 3 — Media query consolidation

- Move all media queries to the bottom of the file (above keyframes).
- Merge duplicate breakpoints into a single block.
- Order breakpoints ascending by value (mobile-first, min-width).
- If max-width queries are detected, flag them as desktop-first and leave them in place — do not reorder or convert them.

Applies in **neutral** and **aggressive** mode. In defensive mode, flag and report only.

**Tooling note — large files**: for files with 50+ scattered `@media` blocks, making individual edits is impractical and error-prone. Use the brace-counting reference script at `tools/phase3-consolidate-mq.py` instead. Key design: single-line blocks (e.g. `:root` var overrides) are detected via `'\n' not in full_block` and left in place; multi-line blocks are extracted, grouped by breakpoint value, and appended at the bottom. Adapt the `@media` regex and the single-line heuristic to the target file's syntax before running.

### Phase 4 — Keyframe placement

Move all `@keyframes` below media queries.

Applies in **neutral** and **aggressive** mode. In defensive mode, flag and report only.

### Phase 5 — Variable extraction from media queries

For each property override inside a media query selector, apply a cost/benefit gate before substituting:

**Only replace a value with a custom property if at least one of these conditions is true:**
1. **Selector elimination** — substituting this value (and others in the same selector) allows the entire MQ selector to become var-only overrides, making it a candidate for removal.
2. **Brand/identity property** — the property is `color`, `background-color`, `font-family`, `border-color`, or similar presentational/brand properties where a single source of truth matters more than byte count.
3. **Byte neutral or smaller** — the var name + `var()` wrapper is equal to or shorter than the raw value. Rule of thumb: a var name of 5+ characters + the 5-character `var()` overhead = 10 characters minimum. A raw value shorter than that is not a candidate.
4. **Specificity bundle** — two or more selectors in the same MQ block share a component root, and converting ALL their properties to private vars allows the entire group to be replaced by a single component-root override. Individual properties may fail conditions 1–3; the joint specificity reduction across ≥ 2 selectors is the gate. Example: `.section .wrapper { flex-direction: column }` (0,2,0) + `.section .wrapper>div { width: 100% }` (0,2,1) → `.section { --_sfd: column; --_sdw: 100% }` (0,1,0). The values `column` and `100%` are both too short to qualify individually — the bundle qualifies them together.

**Structural and layout properties** (`padding`, `margin`, `border-radius`, `z-index`, `line-height`, `gap`, `width`, `height`, etc.) should be left as raw values unless condition 1 (selector elimination) applies — OR the private layout var pattern applies (see below).

**Process — brand/identity properties (conditions 1–3):**
- Use the fallback pattern to initialize the variable at the point of use: `color: var(--card-color, #7c6ef5)`. This keeps the base value where it belongs and avoids an unnecessary var declaration on the parent for the default case.
- Set the var on the parent component only when a breakpoint override is needed: `@media (...) { .parent { --card-color: #9585f8; } }`.
- Use the component hierarchy from Phase 2 to determine the right parent level to hoist the override to.
- If all property overrides in a MQ selector are replaced this way, the selector is now empty — remove it.

**Detection — specificity bundle (condition 4, aggressive only):**

Before scanning individual selectors, group all MQ selectors by component root (the outermost component class in each selector, e.g. `.about-section4`). For each group:
1. Can every selector in the group be reduced to a private var override on the component root?
2. Would that eliminate ≥ 2 selectors from the MQ block?

If yes to both: apply the bundle. For each property in the group, add `property: var(--_varname, fallback)` to the corresponding base rule. Collect all var overrides under a single component-root block in the MQ. Report the specificity reduction per selector eliminated.

**Process — private layout var pattern (aggressive only):**

Apply this pattern to structural/layout properties that are overridden in **3 or more MQ blocks**. The base value may be a raw value or a global token — the threshold is repetition, not token origin.

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
- MQ override: set the var on the **component root** (top-level component class), not on the target element. CSS custom properties inherit through the DOM — the full path is never needed in the MQ.
  - `@media (…) { .hero { --_hrp: var(--spacing-lg); } }` ← correct
  - `@media (…) { .hero .inner-container .card { --_hrp: var(--spacing-lg); } }` ← redundant, do not write this
- Result: the actual property appears once in the base; MQ blocks contain only short component-root overrides.

**Global var detection:**
- If a var is used but not defined in the current file, it is likely defined in a global stylesheet.
- Trace the `<link>` tags in the HTML file to identify candidate global files.
- It is safe to reference undeclared vars in fallbacks — they resolve at runtime from the global scope.

**Neutral**: only substitute using variables that already exist in the file. Do not create new tokens. Private layout vars are aggressive-only.
**Aggressive**: create new tokens where needed. Apply private layout var pattern. Remove selectors that become empty after extraction.
**Defensive**: flag opportunities that pass the cost/benefit gate, suggest token names and initialization values, no edits.

**`@scope` + private var synthesis (aggressive only):**

When Phase 5 is applied to a component that is also wrapped in `@scope` (Phase 1), a tension arises: `@scope` owns the base rules (component axis), while Phase 3 MQ blocks own the breakpoint axis. The private layout var pattern resolves this cleanly:

1. Inside `@scope (.component)`, base property uses the private var with fallback: `min-height: var(--_cmprop, 450px)`.
2. In the Phase 3 MQ block, the override targets the component selector directly (not scoped): `.component { --_cmprop: 300px; }`.
3. `@scope` is transparent to custom property inheritance — the var set outside the scope resolves inside it normally.
4. Result: base rule lives inside `@scope`; all MQ selectors are one-liner var overrides; no selector duplication.

**Second-pass: multi-selector ladder detection**

After the initial extraction pass, scan for selectors not yet using a var whose MQ overrides track the same breakpoint values as an existing `:root` var ladder. These selectors are candidates to adopt the same var.

Detection: for each `:root` var ladder (e.g. `--container-max` overridden at 8 breakpoints with values 1500 / 1300 / 1200 / 900 / 800 / 700 / 350 / 300px), find other selectors that override the same property to the same values at the same breakpoints. A match on 4+ breakpoints is sufficient.

**Process:**
1. Add `property: var(--existing-token)` to the selector's base rule.
2. Remove its per-breakpoint entries from the MQ blocks. If an entry only contained that property, remove the entire selector block. If it also contained other declarations, remove only the property line.
3. Annotate the base rule addition and note lines removed.

**Exception**: if the selector uses `!important` on that property in any breakpoint, the var approach requires `!important` on the base rule too. Flag with `[optimize-css:warn]` and leave for manual decision — do not apply automatically. The `!important` likely indicates an external conflict (inline style, framework override) — see Case 3 in Phase 1.

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

### Specificity
- Flag selectors that climb specificity unnecessarily (chained classes, tag qualifiers, deep descendant selectors).
- Flag modifiers that rely on parent context to work (e.g. `.parent.is-active .child-element`).
- Flag cross-block coupling: one component's state overriding another component's styles (e.g. `.card.is-highlighted .button`).

### Dead CSS
- Flag selectors with no matching element in the HTML (aggressive mode only — requires HTML file).
- In neutral/defensive mode, note that dead CSS check was skipped (no HTML available).

### Longhand-to-shorthand: `inset`
- Flag `top: 0; right: 0; bottom: 0; left: 0` → suggest `inset: 0`. Also applies when all four share the same non-zero value.
- **Neutral/Aggressive**: replace with `inset`. **Defensive**: flag with suggested replacement.
- Annotate: `/* [optimize-css] top/right/bottom/left → inset: 0 */`

### `transition: all` and invalid timing functions
- Flag any `transition: all …` as a performance issue — `all` forces the browser to check every animatable property on every frame. Suggest listing only the properties actually changing.
- **All modes**: `[optimize-css:warn]` — naming the right properties requires knowing the element's behaviour; no automatic fix.
- Separately, scan all timing function values for invalid keywords (e.g. `ease-in-ease-out` — not a valid CSS value; silently falls back to `ease`). Flag with `[optimize-css:warn]` and suggest the correct value (`ease-in-out`).

### `background-size` / `background-position` without `background-image`
- Flag selectors that declare `background-size` or `background-position` but have no `background-image`, `background`, or `background-color` in the same rule.
- These declarations only take effect when an image is present. If the image is set inline or via JS, they are safe — but worth flagging.
- **All modes**: `[optimize-css:warn]` — cannot determine whether image is set externally.

### CSS custom property name length (applies to Phases 5 and 6)
- When generating a new custom property name, keep it to **16 characters or fewer** (excluding the `--` prefix).
- If the natural name would exceed this limit, apply abbreviation: remove vowels from the longest segment first, then shorten further if still over. For font families, abbreviate the family name portion: `--ff-sofia-condensed` → `--ff-sofiac`.
- Annotate if a name was shortened: `/* [optimize-css] --ff-sofia-condensed shortened to --ff-sofiac — name length limit */`

### Responsive typography vars (Phase 5 extension)
- When multiple heading-level selectors on the same base class (e.g. `h1.big-title`, `h2.big-title`, `h3.big-title`) each have MQ overrides for `font-size` and/or `line-height`, introduce per-level vars on the base class rather than repeating each heading selector in the MQ.
- Naming convention: abbreviate base class + heading level: `.big-title` → `--bt`, levels `h1`–`h6` → `--bth1`, `--bth2`, etc.
- Base property: `font-size: 6rem` → `font-size: var(--bth1-fs, 6rem)`
- MQ: instead of `h1.big-title { font-size: 4rem }`, use `.big-title { --bth1-fs: 4rem; --bth2-fs: 3rem; --bth3-fs: 2rem; }` — one selector covers all levels.
- **Aggressive only**: apply transformation. **Neutral/Defensive**: flag the opportunity and suggest the var names.

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
