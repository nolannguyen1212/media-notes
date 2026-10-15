# Diagrams

Source of truth for every diagram embedded in the root `README.md` is the
matching `.d2` file in this directory. Regenerate the SVGs after editing a
source file:

```sh
D2_LAYOUT=tala d2 --theme 200 architecture.d2 architecture.svg
python3 smooth.py architecture.svg right --bend 0.15
D2_LAYOUT=tala d2 --theme 200 processing.d2 processing.svg
python3 smooth.py processing.svg down
for f in upload step-lifecycle; do
  D2_LAYOUT=dagre d2 --dagre-nodesep 120 --theme 200 $f.d2 $f.svg
  python3 smooth.py $f.svg down
done
```

`architecture.d2` and `processing.d2` place every node by hand with
`top`/`left` (TALA only) so the layout stays balanced and the main path sits
on one straight line. `smooth.py` redraws every edge as a straight line
between box sides and bends it only when it would touch another box or a
parallel edge. `--bend 0.15` arcs diagonal edges, bowing up toward a higher
target and down toward a lower one.

Theme 200 is Dark Mauve, rendered as a single fixed-theme SVG (no
`prefers-color-scheme` variant, so it looks the same regardless of the
viewer's OS/browser theme).

`architecture.d2` uses tech-logo icons from `icons/` (sourced from
[Simple Icons](https://simpleicons.org/), recolored to each brand's color
and bundled inline by `d2` at render time — no network access needed to
view the SVG). Reference an icon with a path relative to this directory,
e.g. `icon: icons/go.svg`.
