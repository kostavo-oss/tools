# Secrets

A source asks dlt for a secret: `access_token: str = dlt.secrets.value`. dlt looks in the
environment, then in `.dlt/secrets.toml`, then in the secret scopes the app or the run
names. Three ways to give it one, and when to use each:

1. **By dlt's name, in a scope.** The path dlt asks for, joined with `-`:

   ```sh
   databricks secrets put-secret ingest sources-github-access_token
   ```

   The default. One secret per value, and no code.

2. **A whole section in one secret.** A secret named `sources-github` (or `sources`,
   `destination-<name>`, `destination`, `dlt_secrets_toml`) is read as a piece of
   `secrets.toml`. It must spell out its own heading:

   ```toml
   [sources.github]
   access_token = "..."
   ```

   Without the heading its values are found as every source's. Use it when a source has
   several secrets that change together.

3. **A secret that exists under another name.** Point at it, as `<scope>/<key>`:

   ```python
   app = App(..., secrets={"sources.github.access_token": "platform-shared/github-token"})
   ```

   or per run, so dev and prod can differ in the bundle:
   `--secret sources.github.access_token=platform-shared/github-token`.
   Use it when somebody else fills the scope.

4. **An Azure Key Vault**, for a team whose secrets live there and not in a scope. Needs
   the extra, `uv add "leeghwater[keyvault]"`, and a vault named in the app or per run:

   ```python
   app = App(..., key_vaults=["https://kv-ingest.vault.azure.net"])
   ```

   A vault is asked after the scopes. Its secrets are named like a scope's, with dashes
   where a Key Vault allows no underscore: `sources-github-access-token`. Whoever
   `DefaultAzureCredential` finds reads it: `az login` on a laptop; a service principal's
   variables or a managed identity elsewhere. A Databricks job has no identity in Azure by
   itself, so there a vault is reachable only through a service principal whose secret
   comes from somewhere else — in practice a Databricks scope — and only when the job's
   network reaches `vault.azure.net`. A Key Vault-backed Databricks scope needs none of
   this: it is a scope, read as in 1.

A scope or a vault is listed once in a run and only the secrets that are there are read.
Only values a source marks as secret are looked up. No value is printed, logged, written to
a file or put in the environment. To make, change or rotate a secret, use the Databricks
CLI or the Azure portal.

In a job a secret is read through `dbutils`, so Databricks redacts it: if your own code
prints one, the job's output shows `[REDACTED]`.
