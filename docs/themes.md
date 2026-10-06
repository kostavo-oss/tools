# Themes

!!! note "This is about the terminal version"
    `caland --tui` — Caland as it was. It gets nothing new; what `caland` opens now is
    [the page](page.md), and [its keys](page.md#keys) differ in places.

Caland ships with a calm, near-neutral default and a few optional skins.

| Theme | Look |
|-------|------|
| **Graphite** | The default — a calm, near-neutral palette. |
| **violet** | The original look. |
| **amber** | An Okudagram-inspired skin. |
| **phosphor** | A green phosphor skin. |

## Per-section accents

Whichever theme is active, each browser section keeps its own accent colour on its border, title, and selection:

- **Scopes** — violet
- **Secrets** — cyan
- **Detail** — amber

This keeps the three panes visually distinct at a glance.

## Switching themes

Open the command palette with ++ctrl+p++ and choose **Change theme**, then pick a skin from the list. Your choice is remembered across sessions (in `~/.config/caland/settings.json`).
