from leeghwater import App

app = App(pipelines="my_ingest.pipelines")


@app.command()
def backfill(day: str) -> None:
    """Load one day again."""
    import dlt

    print(f"backfill {day} with {dlt.secrets.get('sources.github.access_token')}")
