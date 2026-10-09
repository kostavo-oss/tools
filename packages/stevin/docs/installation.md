# Installation

stevin is a Python 3.11+ CLI, published on [PyPI](https://pypi.org/project/stevin/).

!!! warning "Alpha"
    Every release so far is a pre-release (`0.1.0a1`, …), which installers skip unless
    asked — hence the flags below. Try it on a dev catalog before a production one.

=== "uv tool"

    ```sh
    uv tool install --prerelease allow stevin
    stevin --version
    ```

=== "uvx"

    ```sh
    uvx --prerelease allow stevin plan -t dev
    ```

=== "pipx"

    ```sh
    pipx install --pip-args=--pre stevin
    stevin --version
    ```

=== "pip"

    ```sh
    pip install --pre stevin
    ```

## From source

```sh
git clone https://github.com/kostavo-oss/stevin
cd stevin
uv sync
uv run stevin --version
```

## Connecting to a workspace

stevin delegates authentication to the Databricks SDK's unified auth, so anything
that works for the Databricks CLI works here.

**Per target, with profiles** — the usual setup, since dev and prod tend to be
different workspaces. Log in once per workspace with the Databricks CLI, then name the
profile and a SQL warehouse on each target:

```sh
databricks auth login --host https://adb-1111.1.azuredatabricks.net --profile dev
databricks auth login --host https://adb-2222.2.azuredatabricks.net --profile prod
```

```yaml
targets:
  dev:
    vars: {catalog: dev}
    profile: dev
    warehouse_id: abc123def456
  prod:
    vars: {catalog: prod}
    profile: prod
    warehouse_id: 789ghi012jkl
```

`--profile` on any command overrides the target's.

**From the environment** — what CI does. With no profile set anywhere, the SDK's
defaults apply:

```sh
export DATABRICKS_HOST="https://adb-1234567890.1.azuredatabricks.net"
export DATABRICKS_TOKEN="dapi..."
export DATABRICKS_WAREHOUSE_ID="abc123def456"
```

Statements run on a SQL warehouse via the Statement Execution API, so a warehouse id —
from the target, `--warehouse-id`, or `DATABRICKS_WAREHOUSE_ID` — is required for
everything except `validate` and `show`.

!!! tip "`validate` needs nothing"
    `stevin validate` is a pure spec lint — no credentials, no network. It is the
    right thing to run in a pre-commit hook.

## Coming from deltaplan

Up to 0.2.0a4 stevin was released as `deltaplan`. The rename changed what you type; it
did not change anything in a workspace.

| Before | Now | If you do nothing |
|---|---|---|
| `uv tool install deltaplan` | `uv tool uninstall deltaplan`, then `uv tool install --prerelease allow stevin` | — |
| `deltaplan plan` | `stevin plan` | `deltaplan` still runs: it says its new name on stderr, then does what `stevin` does |
| `deltaplan.yml` | `stevin.yml` | The old file is still found, and the command line says it can be renamed |
| `uses: misja-pronk/deltaplan@v0` | `uses: kostavo-oss/stevin@v0` | — |
| `import deltaplan`, `DeltaplanError` | `import stevin`, `StevinError` | — |

**With `uv tool`, uninstall deltaplan first.** stevin brings a `deltaplan` command of its
own — the one in the table above — so uv won't install it beside the old package, which
has a command of that name too. The install stops with `Executable already exists:
deltaplan`. Take the old one out, then install stevin the way the top of this page says:

```sh
uv tool uninstall deltaplan
```

Nothing is lost by it: the `deltaplan` command comes with stevin from then on.

**What is on your tables stays.** A table deltaplan made carries the property
`deltaplan.managed`, a seeded one `deltaplan.seed`, and a rewrite stages its data in
`<table>__deltaplan_rewrite`. stevin reads and writes those same names, so a table
deltaplan managed is a table stevin manages — nothing is claimed again, and the first plan
after the upgrade is the plan you would have had before it. The same goes for the
`history_schema` your project names: it is yours, whatever it is called.
