# Kostavo tools

**Small tools for the ugly gaps on Databricks.**
Databricks does most things well. A few it leaves to you: the tables no pipeline owns
and the grants and masks around them, the steps before and after a bundle deploy, a dlt
pipeline that has to run on a laptop before it runs in a job, and the secrets in a scope
you can only reach with an API. Each of those is a setup notebook or a brittle script in
most workspaces. These are four small tools, one per gap, each with a closed scope.

[![ci](https://github.com/kostavo-oss/tools/actions/workflows/ci.yml/badge.svg)](https://github.com/kostavo-oss/tools/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-kostavo--oss.github.io%2Ftools-1f9e9a.svg)](https://kostavo-oss.github.io/tools/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/kostavo-oss/tools/blob/main/LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

| tool | the gap | |
|---|---|---|
| [**stevin**](packages/stevin) | puts in place the tables and access that your transformation tool doesn't own — a plan for Unity Catalog tables that knows which Delta changes are free and which rewrite 400 GB | [![PyPI](https://img.shields.io/pypi/v/stevin.svg)](https://pypi.org/project/stevin/) [docs](https://kostavo-oss.github.io/tools/stevin/) |
| [**lely**](packages/lely) | one plan for your whole Databricks deploy — the bundle and the steps around it, reviewed before anything runs | [![PyPI](https://img.shields.io/pypi/v/lely.svg)](https://pypi.org/project/lely/) [docs](https://kostavo-oss.github.io/tools/lely/) |
| [**leeghwater**](packages/leeghwater) | your dlt pipeline, the same on your laptop and in a Databricks job | [![PyPI](https://img.shields.io/pypi/v/leeghwater.svg)](https://pypi.org/project/leeghwater/) [docs](https://kostavo-oss.github.io/tools/leeghwater/) |
| [**caland**](packages/caland) | Databricks secrets, by hand: a keyboard-driven page in your browser, served from your own machine | [![PyPI](https://img.shields.io/pypi/v/caland.svg)](https://pypi.org/project/caland/) [docs](https://kostavo-oss.github.io/tools/caland/) |

Every tool is a package of its own on PyPI, with its own version, changelog and docs;
none needs another. They share this repository: one lock file, one test gate, one site.
A fifth is in the making, as a spec and no code:
[contracts](packages/contracts), a consumer's gate for data contracts.
A data product that uses them together starts from
[data-product-template](https://github.com/kostavo-oss/data-product-template), a template.

## Where they fit

Each does one job and none needs another: Terraform sets up the platform, an Asset
Bundle deploys the code, dbt, Lakeflow or SQLMesh build the tables they build, and these
tools take the pieces in between. Kostavo is the company behind them: it builds
[a governance platform for Databricks workspaces](https://kostavo.com), and the tools
are complete without it.

Community project, not affiliated with or endorsed by Databricks.

## Named after

Dutch water engineers: Simon Stevin designed sluices and introduced decimal notation,
Cornelis Lely drew the plan that closed the Zuiderzee, Jan Adriaanszoon Leeghwater
drained the lakes north of Amsterdam, and Pieter Caland cut Rotterdam's way to the sea.
Precision before action.

## Development

The repository is a [uv](https://docs.astral.sh/uv/) workspace, with
[mise](https://mise.jdx.dev) to pin the tools and the Astral stack
([ruff](https://docs.astral.sh/ruff/), [ty](https://docs.astral.sh/ty/)).

```sh
mise install     # pinned Python + uv
uv sync          # one .venv with every package and the dev tools

mise run check   # lint + format check + types + unit tests, every package
mise run test    # the unit tests alone
mise run docs    # the site at localhost:8000
mise tasks       # the rest
```

A change to one package is a pull request about that package; a release is that
package's version bumped and its changelog moved, merged — see
[CONTRIBUTING.md](CONTRIBUTING.md). Each package's own `CLAUDE.md` and `CONTRIBUTING.md`
say what holds inside it.

## License

[Apache-2.0](LICENSE), every package.
