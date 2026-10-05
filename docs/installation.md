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
