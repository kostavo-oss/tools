# sluis

One `plan` and one `apply` for a whole Databricks deploy: pre-deploy steps, the bundle,
post-deploy steps. It covers what a bundle can't deploy: tables, database migrations, and your
own steps.

Design stage. See [docs/DESIGN.md](docs/DESIGN.md).

## The names

About a quarter of the Netherlands lies below sea level. It stays dry through engineering: things
are planned, reviewed and checked before anything opens. These tools bring the same habit to a
Databricks workspace.

- **deltaplan**: after the North Sea flood of 1953, the Dutch drew up the *Deltaplan*, one plan
  for the whole delta, built one work at a time over four decades. deltaplan is one plan for every
  change to your tables, reviewed before anything is altered. And yes, they're Delta tables.
- **sluis**: a *sluis* (a lock) moves a ship between water levels one chamber at a time, and the
  gate behind closes before the gate ahead opens. sluis moves a deploy the same way: pre-deploy
  steps, then the bundle, then post-deploy steps, each stage checked before the next one opens.
- **kluis**: a *kluis* is a vault. It keeps valuables in and shows who holds a key. kluis does that
  for Databricks secrets: browse the scopes, see the ACLs, and reveal only what you mean to.

Deltaplan keeps the sea out, sluis lets ships through, and kluis keeps valuables in.

*sluis* and *kluis* rhyme: roughly "slouse" and "klouse". English has no Dutch *ui*, but "house"
is close enough.
