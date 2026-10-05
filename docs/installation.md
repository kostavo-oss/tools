# Installation

## Requirements

- **Python ≥ 3.11**
- A modern terminal on **macOS**, **Linux**, or **Windows**

Maeslant is distributed on PyPI. No configuration is required before you install or run it — connection details are gathered interactively on launch.

## Install

=== "uvx"

    Run the latest version once, ephemerally, without installing anything:

    ```sh
    uvx maeslant
    ```

=== "uv tool"

    Install `maeslant` onto your `PATH`:

    ```sh
    uv tool install maeslant
    ```

=== "pipx"

    Run once, or install persistently:

    ```sh
    pipx run maeslant
    ```

    ```sh
    pipx install maeslant
    ```

## Running

Once installed, launch the app:

```sh
maeslant
```

It opens the workspace picker. See [Connecting](connecting.md) for what happens next.

## Upgrading

=== "uvx"

    `uvx` always fetches the latest published version, so there is nothing to upgrade. To refresh a cached run:

    ```sh
    uvx maeslant@latest
    ```

=== "uv tool"

    ```sh
    uv tool upgrade maeslant
    ```

=== "pipx"

    ```sh
    pipx upgrade maeslant
    ```

!!! note "No config needed up front"
    Maeslant ships with sensible defaults and discovers your workspaces at runtime. You do not need to create a config file, set environment variables, or store a token before the first launch.

## Coming from isolinear

Up to 0.4.1 Maeslant was released as `isolinear`. The rename changed what you type; nothing
you had is lost, and nothing in a workspace is touched.

| Before | Now | If you do nothing |
|---|---|---|
| `uv tool install isolinear` | `uv tool install maeslant` | — |
| `isolinear`, `iso` | `maeslant` | Both old commands still run: they say the new name on stderr, then open the app |
| `~/.config/isolinear/settings.json` | `~/.config/maeslant/settings.json` | The old file is read until you change a preference; that saves the new one, and the old file is left where it is |
| theme `isolinear-violet` (and the other three) | `maeslant-violet` | A saved theme is still the theme you get |

Workspaces and profiles are found the way they always were — `~/.databrickscfg`, a
bundle's targets, the environment — and none of that carries the tool's name.
