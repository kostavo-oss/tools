# In a notebook, and commands of your own

## Without an app

```python
import leeghwater

setup = leeghwater.prepare(secret_scopes=["ingest"], catalog="main", warehouse="<id>")
print("\n".join(setup.lines()))

p = leeghwater.create_pipeline("github", schema="github")
leeghwater.run(p, github_source())
```

`prepare()` is everything the app does before a run, and returns what it decided;
`create_pipeline` and `run` go by the last `prepare()`, and `create_pipeline` by a
`setup=` when you pass it one.
A later `prepare()` starts from nothing. What an earlier call set in the environment is
put back, and the scopes and vaults it registered with dlt are taken out. A `prepare()`
that is refused leaves no setup: call it again before you make a pipeline.
Importing `leeghwater` changes nothing and does not import dlt.

## Asking where it runs

```python
here = leeghwater.where()
if here.on_databricks:
    ...
```

`where()` reads `DATABRICKS_RUNTIME_VERSION` and nothing else. `here.on_databricks` is
true when the variable is set, `here.runtime` is what it holds, and `here.serverless` is
true when that starts with `client.`.

## Commands of your own

```python
@app.command()
def backfill(day: str):
    """Load one day again."""
    ...
```

`ingest backfill 2024-06-01` is prepared as a pipeline is, with the app's own settings, and
finds the same secrets.
