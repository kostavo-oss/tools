# Editor support

YAML specs and `stevin.yml` have JSON Schemas, so an editor with a YAML language
server — VS Code with the [Red Hat YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml),
JetBrains IDEs, Neovim with `yaml-language-server` — completes keys, shows what each
one means, and underlines a typo as you type it.

| File | Schema |
|---|---|
| A table, view or function spec | <https://kostavo-oss.github.io/tools/stevin/schema/spec.json> |
| `stevin.yml` | <https://kostavo-oss.github.io/tools/stevin/schema/project.json> |

## Per file

Put this on the first line — `stevin import` writes it for you:

```yaml
# yaml-language-server: $schema=https://kostavo-oss.github.io/tools/stevin/schema/spec.json
table: ${catalog}.sales.orders
```

## For a whole project, in VS Code

In `.vscode/settings.json`, with the paths your specs live in:

```json
{
  "yaml.schemas": {
    "https://kostavo-oss.github.io/tools/stevin/schema/spec.json": ["tables/**/*.yml"],
    "https://kostavo-oss.github.io/tools/stevin/schema/project.json": ["stevin.yml"]
  }
}
```

## Offline, or pinned to your version

The published schemas follow the latest release. `stevin schema` prints the one for
the version you have installed:

```sh
stevin schema spec > .stevin/spec.json
stevin schema project > .stevin/project.json
```

and point `yaml.schemas` (or the `$schema=` line) at those files instead.

## What the schema can't check

The schema catches unknown keys, wrong types and misspelt privileges. `stevin
validate` checks everything else — that a name has three parts, that a primary key's
columns are `NOT NULL`, that a clustering key is a column — and stays the authority:
both are built from the same list of keys, and the tests hold them to it. SQL specs
don't have a schema; sqlglot is their validator.
