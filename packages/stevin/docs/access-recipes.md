# Access recipes

Three shapes cover most of what a team needs, and each is a few lines of spec. What
makes access hard on Databricks is not writing them; it is what the last section says.

## Groups per schema

**Goal:** engineers write, analysts read, per schema, and every new table gets it.

```yaml title="tables/sales/_schema.yml"
schema: ${catalog}.sales
grants:
  - {principal: data_engineers, privileges: [USE SCHEMA, CREATE TABLE, MODIFY, SELECT]}
  - {principal: analysts, privileges: [USE SCHEMA, SELECT]}
```

A grant on a schema is inherited by every table in it, the ones made tomorrow included,
so this is the whole recipe. The plan shows the grants as steps on the schema and
nothing on the tables. On a table, stevin ignores inherited grants — they are the
schema's, never the table's to revoke; only a principal a *table* spec names has its
privileges on that table made to match. A schema is shared ground: principals the schema spec doesn't
name are reported and left alone.

**Gotcha:** `USE CATALOG` on the catalog is still needed, and catalogs are not stevin's.
Grant it once, in Terraform or by hand.

## Rows by region

**Goal:** a sales rep sees the orders of their region; a regional lead sees the region.

A mapping table says who belongs where, a function reads it, the table carries the
filter. Three specs, one plan.

```yaml title="tables/security/region_members.yml"
table: ${catalog}.security.region_members
comment: Which account groups may see which region's rows
columns:
  - {name: region, type: string, nullable: false}
  - {name: group_name, type: string, nullable: false}
constraints:
  - primary_key: [region, group_name]
seed:
  - {region: EMEA, group_name: sales_emea}
  - {region: APAC, group_name: sales_apac}
grants:
  - {principal: sales_leads, privileges: [SELECT, MODIFY]}
```

```yaml title="tables/security/by_region.yml"
function: ${catalog}.security.by_region
comment: Rows of a region, for its members; everything for sales_leads
parameters:
  - {name: region, type: string}
returns: boolean
body: |
  is_account_group_member('sales_leads')
  OR EXISTS (
    SELECT 1 FROM ${catalog}.security.region_members m
    WHERE m.region = region AND is_account_group_member(m.group_name)
  )
```

```yaml title="tables/sales/orders.yml"
table: ${catalog}.sales.orders
columns:
  - {name: order_id, type: bigint, nullable: false}
  - {name: region, type: string, nullable: false}
  - {name: amount, type: "decimal(18,2)"}
row_filter:
  function: ${catalog}.security.by_region
  columns: [region]
```

[`is_account_group_member`](https://docs.databricks.com/aws/en/sql/language-manual/functions/is_account_group_member)
is true when the session user is a direct or indirect member of the account-level group;
it is the one to use under Unity Catalog, not the workspace-level `is_member`. The
function spec is valid only because a row filter names it; a function nothing names is
refused.

The plan creates the function first, then the mapping table with its rows, then
`orders` with the filter already on — a new table never exists unprotected. On an
existing table, the filter is an `ALTER TABLE … SET ROW FILTER`, checked first that the
function is there.

**Gotchas:** the function runs for every row of every query on the table, and a lookup
in it is paid every time; keep the mapping table small and the predicate simple. The
filter is additive: stevin sets or replaces it and never removes one — remove it by hand,
on purpose. A table with a filter is not rewritten by stevin, since the staged copy would
hold what the applying principal can see.

## PII columns by tag

**Goal:** every column tagged as PII, in every table of a schema, is masked for everyone
but a few — including the tables dbt and dlt make, which stevin doesn't shape.

Two parts, two owners. stevin tags the columns. One policy on the schema does the
masking, and it is written in Terraform or SQL, not by stevin.

```yaml title="tables/raw/customers.yml"
table: ${catalog}.raw.customers          # dlt lands it: a governance-only spec
columns:
  - {name: email, tags: {pii: email}}
  - {name: phone, tags: {pii: phone}}
```

```yaml title="tables/sales/orders.yml"
table: ${catalog}.sales.orders           # stevin's own table: the same tag
columns:
  - {name: order_id, type: bigint, nullable: false}
  - {name: customer_email, type: string, tags: {pii: email}}
```

The policy, once per schema, in Terraform with the
[`databricks_policy_info`](https://registry.terraform.io/providers/databricks/databricks/latest/docs/resources/policy_info)
resource:

```hcl
resource "databricks_policy_info" "mask_pii" {
  on_securable_type     = "SCHEMA"
  on_securable_fullname = "prod.sales"
  name                  = "mask_pii"
  policy_type           = "POLICY_TYPE_COLUMN_MASK"
  for_securable_type    = "TABLE"
  to_principals         = ["account users"]

  match_columns = [{ condition = "hasTag('pii')", alias = "c" }]

  column_mask = {
    function_name = "prod.security.redact"
    on_column     = "c"
  }
}
```

or in SQL, from the
[ABAC policies](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/policies)
page's grammar:

```sql
CREATE POLICY mask_pii
ON SCHEMA prod.sales
COLUMN MASK prod.security.redact
TO `account users` EXCEPT pii_readers
FOR TABLES
MATCH COLUMNS has_tag('pii') AS c
ON COLUMN c;
```

Creating a policy needs `MANAGE` on the schema and `EXECUTE` on the function, and —
this is the part that trips teams — the tag has to be a **governed tag**: a key an
account admin defined at account level. A tag with a key nobody governed is just a
label, and the policy won't match it. stevin sets tags with the same `SET TAGS` either
way; make `pii` a governed key before you rely on the policy.

What the plan shows: the tag steps on each table, and nothing about the policy — stevin
doesn't write policies. Showing the policies that apply to a table, in the plan and in
drift, is planned.

**Gotcha:** a table-level mask on a column the policy also masks is a conflict, and
Databricks resolves a conflict by blocking access. Pick one: the schema policy for
everything tagged, table-level masks for the few tables with their own rules.

## What stays hard

Plainly, because no tool removes it:

- **Groups come from your identity provider**, through SCIM to the account. stevin names
  them; it can't make them. The group a spec names has to exist before the plan runs.
- **Governed tags are an account admin's.** Defining `pii` as a governed key, with its
  allowed values, happens in the account console or Terraform, once.
- **A slow row filter slows every query** on that table, for everyone, every time. Test
  the function on the table's real size before the spec names it.
- **Governed tables have limits**, from
  [row filters and column masks](https://docs.databricks.com/aws/en/tables/row-and-column-filters):
  no deep or shallow clone, so `plan --clone` cannot back one up (the clone step fails
  on the workspace; take a `CREATE TABLE … DEEP CLONE` of the *unprotected* source
  before adding the filter if you need one); `MERGE` into a table whose filter or mask
  has nesting, aggregation, a window, a limit or a non-deterministic function is
  refused; no time travel through a filter or mask; and **Delta Sharing does not share
  a table with a row filter or a column mask**. The sharing shape is a filtered view, and
  a [view](spec.md#views) is a stevin spec.
- **There is no run-as on a warehouse.** Nobody can check what another user sees except
  that user. Ask one person from each group to run the query before the go-live.
