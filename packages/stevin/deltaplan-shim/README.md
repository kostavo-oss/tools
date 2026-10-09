# deltaplan is now stevin

`deltaplan` — plan/apply migrations for Unity Catalog tables — was renamed
[**stevin**](https://github.com/kostavo-oss/tools). This is the last release under
the old name. It contains no code of its own: it installs stevin, and forwards to it.

```sh
uv tool install --prerelease allow stevin    # instead of: uv tool install deltaplan
stevin plan                                  # instead of: deltaplan plan
```

Nothing changes in your workspace. Tables deltaplan manages are tables stevin manages,
and a `deltaplan.yml` is still found.
[Coming from deltaplan](https://kostavo-oss.github.io/tools/stevin/installation/#coming-from-deltaplan)
has the short list of what to rename.

Until you do:

- the `deltaplan` command still runs — it says its new name on stderr, then does what
  `stevin` does;
- `import deltaplan` still gives you stevin's public names (and `DeltaplanError`), with a
  `DeprecationWarning`.

Community project, not affiliated with or endorsed by Databricks. Apache-2.0.
