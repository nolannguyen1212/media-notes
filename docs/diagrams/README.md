# Diagrams

Source of truth for every diagram embedded in the root `README.md` is the
matching `.d2` file in this directory. Regenerate the SVGs after editing a
source file:

```sh
D2_LAYOUT=dagre d2 --theme 200 architecture.d2 architecture.svg
D2_LAYOUT=dagre d2 --theme 200 step-lifecycle.d2 step-lifecycle.svg
```

Theme 200 is Dark Mauve, rendered as a single fixed-theme SVG (no
`prefers-color-scheme` variant, so it looks the same regardless of the
viewer's OS/browser theme).

`architecture.d2` uses tech-logo icons from `icons/` (sourced from
[Simple Icons](https://simpleicons.org/), recolored to each brand's color
and bundled inline by `d2` at render time — no network access needed to
view the SVG). Reference an icon with a path relative to this directory,
e.g. `icon: icons/go.svg`.
