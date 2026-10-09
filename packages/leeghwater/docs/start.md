# Start a project

[data-product-template](https://github.com/kostavo-oss/data-product-template) is the way to start: a copier
template for a data product — dlt to land the data, run by leeghwater; dbt to shape it; one
job; the schemas as bundle resources; every task behind `mise run`.

```sh
uvx copier copy gh:kostavo-oss/data-product-template my-product
```

To add leeghwater to a project you have: `uv add leeghwater`, write the two files above, and
pass the schemas' deployed names from the bundle as shown under [In a job](run.md#in-a-job).
