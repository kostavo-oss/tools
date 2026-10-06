# isolinear is now caland

`isolinear` — the terminal UI for Databricks secrets — was renamed
[**Caland**](https://github.com/kostavo-oss/caland). This is the last release under
the old name. It contains no code of its own: it installs caland, and forwards to it.

```sh
uv tool install caland    # instead of: uv tool install isolinear
caland                    # instead of: isolinear, or iso
```

Nothing you had is lost. Your settings and your theme are picked up from where isolinear
kept them, and nothing in a workspace carries either name.
[Coming from isolinear](https://kostavo-oss.github.io/caland/installation/#coming-from-isolinear)
has the short list of what moved.

Until you switch, the `isolinear` and `iso` commands still run — they say the new name on
stderr, then open the app.

Community project, not affiliated with or endorsed by Databricks. Apache-2.0.
