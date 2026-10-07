# 003 — secrets

**Status:** built, in `src/leeghwater/secrets.py`; tested in `tests/test_secrets.py` against
a stand-in scope; read from a real scope on 2026-10-07, as a job's identity and from a
laptop.

## Why

A Databricks team's secrets are in secret scopes. dlt reads secrets from the environment,
from `secrets.toml` and from three vaults, and a secret scope is none of them *(dlt)*. So the
top of a pipeline reads:

```python
os.environ["SOURCES__GITHUB__ACCESS_TOKEN"] = dbutils.secrets.get(
    "ingest", "github-token"
)
```

That runs on Databricks and nowhere else, has to be written again for each secret, and puts
the value in the environment of everything the process starts.

The owner asked for "a custom secrets provider for databricks secrets".

## Requirements

- **R1 — A dlt config provider that reads secret scopes.** `prepare()` registers it with
  dlt, and dlt asks it like any other. It comes after the ones dlt has: an environment
  variable wins, then the developer's own `secrets.toml`, then the scope. In a job there is
  no `secrets.toml`, and the scope answers. *(owner; dlt for the order)*
- **R2 — One way of reading, on a laptop and on Databricks: the client's `dbutils`.** A
  value is read with the Databricks SDK's `WorkspaceClient().dbutils.secrets.get`. Off
  Databricks that is a call to the Secrets API, as the developer. On Databricks it is the
  runtime's own `dbutils`, as the run's identity. The client is made when the first secret
  is asked for. *(decided; run)*

  Why `dbutils` and not the SDK's secrets API: redaction. In a serverless wheel task, a
  value read through the API and then printed was in the task's output as it is. Read
  through `dbutils`, every print of it came out as `[REDACTED]` *(run)*. R9 does not lean on
  that — leeghwater prints no value — but a project's own `print` might.
- **R3 — The project names its scopes.** One or more, in the app; a run can name others with
  `--secret-scope`, which is how dev and prod read different scopes. They are asked in the
  order given and the first that has the secret answers. With no scope named there is no
  provider, and dlt is as it was. On a laptop without `--profile` no scope is read, and the
  first lines say so. *(decided)*
- **R4 — A secret is found by the path dlt has for it, joined with `-`.** dlt asks for a
  value by a path: `sources.github.access_token`. The secret `sources-github-access_token`
  in the scope is the answer. It is how dlt's Google provider names a secret *(dlt)*. When a
  secret is missing, dlt's error lists where each provider looked, with the scope's name and
  the name with `-`, so it can be copied from the error into the scope *(run)*. *(decided)*
- **R5 — Only secrets are asked for.** A value whose type in the source isn't a secret is
  never looked up in a scope: it is config, and belongs on the command line or in
  `config.toml`. *(decided; dlt has it as `only_secrets`)*
- **R6 — A secret can hold a whole section.** As in dlt's other vaults, a secret named
  `sources-github`, `sources`, `destination-<name>`, `destination` or `dlt_secrets_toml` is
  read as a piece of TOML, as if it stood in `secrets.toml`. A team can keep one secret per
  source instead of one per value. A piece is laid at the root of the document *(dlt)*, so a
  secret `sources-github` spells out its own `[sources.github]` heading. Without the heading
  its values are still found, but as every source's: `api_key = "…"` becomes the `api_key`
  of any source that asks for one. The README says so with an example, because the name
  suggests otherwise.
- **R7 — A scope is listed once in a run, and only what is there is fetched.** dlt tries
  several paths for every value and most don't exist. Listing first keeps a run at one list
  per scope and one read per secret used, and keeps a trail of failed reads out of the
  workspace's audit log. A list gives names and no values. Because the names are known,
  single values are looked up as well as sections. *(decided; dlt has it as `list_secrets`;
  run as a job's identity)*
- **R8 — A secret that already exists under another name can be pointed at.** A team whose
  scope was filled by somebody else says which secret is which:

  ```python
  app = App(
      pipelines="my_ingest.pipelines",
      secrets={"sources.github.access_token": "platform-shared/github-token"},
  )
  ```

  The left side is dlt's name, the right side a scope and a key, split at the first `/`.
  What is pointed at wins over what R4 would find, and loses to the environment and
  `secrets.toml` like any scope. A run can say the same, so that dev and prod point at
  different scopes from the bundle:
  `--secret sources.github.access_token=platform-shared/github-token`. *(decided)*
- **R9 — A value goes to dlt and nowhere else.** It is not printed, not logged, not written
  to a file, and not copied into the environment. The first lines of a run and `doctor` name
  the scopes and what is pointed at, never a value; `doctor` says which names a scope holds.
  Tests read what a run printed and look for the values.
  → [000/R10](000-what-leeghwater-is.md#what-it-does) *(decided)*
- **R10 — An error says what to do next.** *(decided)*
  - **A scope that doesn't exist:** an error at the first secret asked for, naming the scope
    and the command that makes it. Without it every secret is reported missing and nothing
    says why.
  - **A scope that can't be listed:** an error naming the scope, the identity that tried and
    the permission it lacks.
  - **A pointer at a secret that isn't there:** an error naming the scope, the key, and the
    names the scope does hold.
  - **One key that isn't there, or is empty:** not an error. dlt asks for many keys that
    don't exist, on purpose. The provider answers "not here" and dlt looks on; when nothing
    has it, dlt's own error lists the places it looked.
  - **Anything else** — the network, the sign-in: raised as it came.
- **R11 — Registering twice changes nothing.** A second `prepare()` with the same scope
  finds the provider that is there and adds none. *(decided)*

## Not in this spec

- **Making, changing and rotating secrets.** The Databricks CLI, or caland. The README
  points there.
- **Writing back** — a refreshed token, for one. The provider only reads.
- **Other vaults.** dlt has them, and they keep working beside this one.
- **Rewriting a scope's name per target.** A bundle says which scope a target reads, with a
  variable.

## Done when

In the tests, with a scope that is a dictionary — all of these pass:

- an argument of a real `@dlt.source` marked `dlt.secrets.value` is filled from the scope;
- a value is found by dlt's name for it, and a section by its name;
- a section without its own heading is every source's, and the test shows it;
- the environment wins over the scope, and the first scope over the second;
- a secret that was pointed at is found, and wins over the scope's own;
- a value that isn't a secret is never asked of a scope;
- a run lists each scope once and reads only secrets that exist;
- no value appears in anything a run or `doctor` prints;
- a missing scope, a refused scope and a pointer at nothing are each an error with a name.

And on a workspace *(run)*: a throwaway secret in a throwaway scope was read by a source in a
serverless wheel task, and printing it showed `[REDACTED]`; the same scope was read from a
laptop with a profile.
