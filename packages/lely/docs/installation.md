# Installation

lely is a Python tool (3.11 or newer), on [PyPI](https://pypi.org/project/lely/).

## In a project

With [uv](https://docs.astral.sh/uv/), as a development dependency of the project that has
the bundle:

```sh
uv add --dev lely
uv run lely --version
```

A plugin that is a package of yours is found this way, because lely is installed next to it.

## On its own

```sh
uvx lely --version        # run it once, installing nothing
uv tool install lely      # or keep the command
```

Installed this way lely has the plugins it comes with and a class in your repository
(`./ops/steps.py:Class`), and not a plugin that is a package of its own.

## From a checkout

```sh
git clone https://github.com/kostavo-oss/tools && cd lely
uv sync
uv run lely --version
```

## What else it needs

- **The [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install)**, for the
  `bundle` plugin — a version with the direct engine (generally available since v1.3.0).
  lely has been run with v1.19.0.
- **Credentials for a workspace**, the way the Databricks CLI and SDK already read them: a
  profile in `~/.databrickscfg` (`--profile`), or the `DATABRICKS_*` variables.
- **git**, if plans are saved to files: a plan file is held to the git tree it was made on.

```sh
lely doctor
```

says which of these it finds, which workspace it reaches and as whom, and whether each
program a step runs is there.

## For your editor

```sh
lely schema -o lely.schema.json
```

writes a JSON Schema of the config, built from the plugins this project uses. Make

```yaml
# yaml-language-server: $schema=lely.schema.json
```

the first line of `lely.yml`, and the editor completes `uses:` and checks each step's
`with:` against its plugin's own options as you type.
