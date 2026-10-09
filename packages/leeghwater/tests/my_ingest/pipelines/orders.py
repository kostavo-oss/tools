import dlt

import leeghwater
from leeghwater import pipeline


@dlt.resource(write_disposition="append")
def orders(region: str):
    yield {"id": 1, "region": region}
    yield {"id": 2, "region": region}


@pipeline
def orders_pipeline(region: str):
    return leeghwater.run(
        leeghwater.create_pipeline("orders", schema="shop"), orders(region)
    )
