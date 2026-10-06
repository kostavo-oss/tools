# Installation

## Requirements

- **Python ≥ 3.11**
- A modern terminal on **macOS**, **Linux**, or **Windows**

Caland is distributed on PyPI. No configuration is required before you install or run it — connection details are gathered interactively on launch.

## Install

=== "uvx"

    Run the latest version once, ephemerally, without installing anything:

    ```sh
    uvx caland
    ```

=== "uv tool"

    Install `caland` onto your `PATH`:

    ```sh
    uv tool install caland
    ```

=== "pipx"

    Run once, or install persistently:

    ```sh
    pipx run caland
    ```

    ```sh
    pipx install caland
    ```

## Running

Once installed, launch the app:

```sh
caland
```

It opens the workspace picker. See [Connecting](connecting.md) for what happens next.

## Upgrading

=== "uvx"

    `uvx` always fetches the latest published version, so there is nothing to upgrade. To refresh a cached run:

    ```sh
    uvx caland@latest
    ```

=== "uv tool"

    ```sh
    uv tool upgrade caland
    ```

=== "pipx"

    ```sh
    pipx upgrade caland
    ```

!!! note "No config needed up front"
    Caland ships with sensible defaults and discovers your workspaces at runtime. You do not need to create a config file, set environment variables, or store a token before the first launch.

## Coming from isolinear

Up to 0.4.1 Caland was released as `isolinear`. The rename changed what you type; nothing
you had is lost, and nothing in a workspace is touched.

| Before | Now | If you do nothing |
|---|---|---|
| `uv tool install isolinear` | `uv tool install caland` | — |
| `isolinear`, `iso` | `caland` | Both old commands still run: they say the new name on stderr, then open the app |
| `~/.config/isolinear/settings.json` | `~/.config/caland/settings.json` | The old file is read until you change a preference; that saves the new one, and the old file is left where it is |
| theme `isolinear-violet` (and the other three) | `caland-violet` | A saved theme is still the theme you get |

Workspaces and profiles are found the way they always were — `~/.databrickscfg`, a
bundle's targets, the environment — and none of that carries the tool's name.
