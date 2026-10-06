# Installation

## Requirements

- **Python ≥ 3.11**
- A browser, on **macOS**, **Linux**, or **Windows**

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

Once installed:

```sh
caland
```

It starts a small server on your machine, opens a tab in your browser, and says so:

```
caland is at http://127.0.0.1:53124/ — opened in your browser.
enter: a new link · ctrl+c: stop
```

See [Connecting](connecting.md) for which workspace it shows, and [Using the page](page.md)
for the rest. If no tab opens, `caland --no-open` prints the link instead; it works once.

Until 0.6 `caland` opened a terminal app. [That app is isolinear](#if-you-want-a-terminal-app).

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

## If you want a terminal app

Caland was a terminal app until 0.6, under its former name too: **isolinear**. That app is
still on PyPI as it was — `uvx isolinear` — and Caland no longer has it. The two are
separate tools and can be installed side by side; they share nothing but your
`~/.databrickscfg`.

isolinear gets nothing new, and that includes two fixes Caland has: it deletes a secret that
is renamed to the same name in another case, and it mis-reads a `.env` value quoted over
several lines. Don't do either there.
