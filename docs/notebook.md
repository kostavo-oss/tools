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
`create_pipeline` and `run` go by the last `prepare()`, or by a `setup=` you pass them.
Importing `leeghwater` changes nothing and does not import dlt.


## Commands of your own

```python
@app.command()
def backfill(day: str):
    """Load one day again."""
    ...
```

`ingest backfill 2024-06-01` is prepared as a pipeline is, with the app's own settings, and
finds the same secrets.
