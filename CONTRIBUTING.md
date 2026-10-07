# Contributing to leeghwater

Thanks for your interest! Issues and pull requests are very welcome.

## How changes land

Every change is a pull request, merged once **`ci`** passes: ruff (lint and format) and
the tests on Python 3.11–3.13. The workflow itself is shared by all the Kostavo tools and
lives in [`kostavo-oss/.github`](https://github.com/kostavo-oss/.github).

## Toolchain

leeghwater uses [`uv`](https://docs.astral.sh/uv/) (env / deps / run),
[`ruff`](https://docs.astral.sh/ruff/) (lint + format) and
[`pytest`](https://docs.pytest.org/).

```sh
uv sync                   # creates .venv and installs deps + dev tools
uvx pre-commit install    # optional: ruff on every commit
```

## Day-to-day

```sh
uv run leeghwater                              # run the CLI
uv run pytest                                 # tests
uv run ruff check . && uv run ruff format .   # lint + format
```

## Conventions

- `CHANGELOG.md` gets a line under `## [Unreleased]` for anything a user would notice.
- By contributing you agree your work is licensed under the project's
  [Apache-2.0 License](LICENSE).

## Releasing

A release is a tag. `pyproject.toml` says which version it is, and the tag has to agree.

In a pull request, bump the version and move the changelog notes under it:

```sh
uv version --bump patch   # or minor / major, or: uv version 0.2.0
```

In `CHANGELOG.md`, rename `## [Unreleased]` to `## [0.2.0] - <date>` and start a fresh,
empty `## [Unreleased]` above it. Merge it once `ci` passes, then tag that commit:

```sh
git switch main && git pull
git tag v0.2.0 && git push origin v0.2.0
```

The [`release`](.github/workflows/release.yml) workflow runs on the tag: it checks that
the tag and `pyproject.toml` name the same version, runs the gate, builds the wheel and
sdist, and publishes them to **PyPI** with Trusted Publishing — no API token.

A tag that disagrees with `pyproject.toml` fails before anything is built, so nothing is
published; delete it, fix what is wrong, and tag again.

## Previewing the docs

```sh
uv run --group docs mkdocs serve
```
