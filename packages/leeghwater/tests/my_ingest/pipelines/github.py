from datetime import date

import dlt

import leeghwater
from leeghwater import pipeline


@dlt.source
def github_source(since: str, access_token: str = dlt.secrets.value):
    @dlt.resource(write_disposition="merge", primary_key="id")
    def issues():
        yield [{"id": 1, "since": since, "token_length": len(access_token)}]

    return issues


@pipeline
def github(since: date = date(2024, 1, 1), full: bool = False):
    """Load GitHub issues."""
    p = leeghwater.create_pipeline("github")
    return leeghwater.run(p, github_source(since=since.isoformat()))
