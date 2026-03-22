# BACKLOG / IDEAS

## Must Have

- Integrate TODO checks into the appropriate phases:
  - `!important` → Phase 1 (de-nesting often resolves the specificity conflict causing it)
  - Specificity & cross-block coupling → Phase 1 / Phase 2
  - Token consolidation → Phase 5 (variable extraction)
  - Dead CSS → Phase 1 (after de-nesting, orphaned selectors become visible)
  - Wildcard / structural selectors → Phase 1

## Should Have

- Group CSS vars that seem general (colors, typography, spacing used across multiple unrelated components) and suggest moving them to a global or base stylesheet via a comment.
- Hoist CSS vars to the appropriate parent level based on the component hierarchy map (Phase 2 → Phase 5).

## Could Have

- Rewrite to Mobile First: detect desktop-first patterns (max-width queries, base styles assuming large screen) and convert the file to a mobile-first structure — base styles become the smallest viewport, queries become min-width ascending.
- SCSS support: the skill description mentions SCSS but the process currently assumes flat CSS. Handle `&` nesting, variables (`$var`), and `@mixin` / `@include` patterns.

## Would Have

- Multi-file mode: accept a folder or list of files and cross-reference selectors across them before flagging dead CSS or suggesting token moves.
- `@property` suggestions: for custom properties used in animations or transitions, suggest typed `@property` declarations for better performance and interpolation.
- Config file support: look for an `optimize-css.config.json` in the project root and let its values override defaults. Useful for setting a default mode, toggling phases on/off, ignoring specific selectors, and declaring mobile/desktop-first explicitly. CLI arguments take precedence over config. Revisit once Must Have phases are stable.
