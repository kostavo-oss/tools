# A project

What a project that uses leeghwater looks like, and the commands it gets.

The app, which is the project's console script:

```python
# src/my_ingest/cli.py
from leeghwater import App

app = App(pipelines="my_ingest.pipelines", secret_scopes=["ingest"])
```

```toml
# pyproject.toml
[project.scripts]
ingest = "my_ingest.cli:app"
```

And a pipeline: a function marked `@pipeline`, anywhere in the package the app names.

```python
# src/my_ingest/pipelines/github.py
from datetime import date

import dlt
import leeghwater
from leeghwater import pipeline


@dlt.source
def github_source(since: date, access_token: str = dlt.secrets.value): ...


@pipeline
def github(since: date = date(2024, 1, 1)):
    """Load GitHub issues."""
    p = leeghwater.create_pipeline("github")
    return leeghwater.run(p, github_source(since=since))
```

`create_pipeline` and `run` stand in for `dlt.pipeline()` and `pipeline.run()`, and a
pipeline never calls those two itself. Where a run loads, into which schema and through
which staging schema is the run's to say, not the code's: `create_pipeline` sets them on
the dlt destination it makes, and a plain `dlt.pipeline()` gets none of it. What you get
back is dlt's own pipeline and dlt's own load info, and anything else the two dlt calls
take is passed on.

```sh
ingest list                                  # the pipelines and their parameters
ingest run github --since 2024-06-01         # run one
ingest doctor                                # what would be set up, checked, nothing run
```
