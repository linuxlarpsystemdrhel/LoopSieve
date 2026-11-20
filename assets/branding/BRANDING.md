# LoopSieve visual identity

[Three vector concepts](concepts.svg) were drawn and compared at icon size.

| Concept | Originality | Scalability | Recognition |
|---|---|---|---|
| Loop and delta | Combines a repeated input stream, a verification loop and an outgoing signal | Solid 8-unit strokes survive 32 px | Distinct open loop and teal arrow |
| Signal merge | Uses branching lines to show multiple log lines becoming one signal | Simple but the meeting strokes crowd at small sizes | Looks like a general merge control |
| Evidence card | Shows the recorded outcome of a verification run | The card outline stays clear at 32 px | Resembles a standard checklist icon |

The selected **Loop and delta** uses short slate strokes for incoming check output, a rounded loop for repeated verification, and an outgoing teal arrow for changed evidence.

| Color | Hex | Use |
|---|---|---|
| Ink | `#142129` | Wordmark and loop on light backgrounds |
| Teal | `#117B6E` | Signal on light backgrounds |
| Muted slate | `#516E73` | Input lines and secondary copy on light backgrounds |
| Canvas | `#F1F7F6` | Light banner background |
| Night | `#111D24` | Social preview background |
| Paper | `#EFF8F7` | Wordmark and loop on dark backgrounds |
| Mint | `#5CDECB` | Signal on dark backgrounds |
| Fog | `#A3BEC1` | Input lines and secondary copy on dark backgrounds |
| Light rule | `#C6DBD9` | Diagram guides on light backgrounds |
| Dark rule | `#2F4951` | Diagram guides on dark backgrounds |

The lockup uses bold Liberation Sans with Arial and system sans-serif fallbacks. Diagram labels use Liberation Mono with a monospace fallback. Font programs are not bundled.

Use `logo-light.svg` (also `logo.svg`) on light surfaces and `logo-dark.svg` on dark surfaces. These variants and `logo.png` have transparent backgrounds. For square uses, prefer `icon.svg` or `icon-512.png` on a light surface. Keep clear space around the symbol of at least the height of one input stroke. Preserve the view box and colors. Switch from the lockup to the icon below 120 px of available width. The icon was checked at 32 and 64 px.

`banner.png` is 1280 × 360 and `social-preview.png` is 1280 × 640. The SVG source geometry was created locally and exported to PNG with librsvg. Regenerate with `python tools/build_branding.py`.
