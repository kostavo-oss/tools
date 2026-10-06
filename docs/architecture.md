# Architecture

Caland follows a **hexagonal / DDD** design. Dependencies point **inward**, and all I/O sits behind domain ports, so the domain is fully unit-testable with no network.

```
src/caland/
  domain/          model, rules + ports (SecretStore, WorkspaceConnector,
                   ProfileStore, BundleStore, SettingsStore)
  application/     use-cases (WorkspaceService, OnboardingService, Loader),
                   the read model, and what reads a file somebody picked
  infrastructure/  adapters — the ONLY place the Databricks SDK is imported
  interface/web/   the page: a server on this machine, and what it serves
  app.py           the command: reads what was asked, wires it together
```

## Layers

- **`domain/`** — the model, rules, and ports. It imports nothing outward.
- **`application/`** — use-cases and a read model. A change to a workspace goes through `WorkspaceService`, which takes one at a time and asks the workspace what is there *now* before it writes.
- **`infrastructure/`** — the adapters that implement the domain ports. This is the **only** place the Databricks SDK is imported, and the only code that writes `~/.databrickscfg`.
- **`interface/web/`** — the page. `gate.py` decides which requests are answered at all — a pure function; `server.py` answers them; `views.py` says what the page is told; `static/` is the page itself: one HTML file, one stylesheet, one script.
- **`app.py`** — the command.

!!! note "The page never reaches the SDK"
    The boundary is strict: the browser talks to the server on your machine, the server to application services, application to domain ports, and only `infrastructure/` reaches for the Databricks SDK or the network.

## The page and the server

The page holds no secret and no name until it has been let in, and then only what it shows. Every request about a workspace carries the session's token and says which workspace it means; what a workspace says is written as text, never as markup. [How it is kept yours](page.md#how-it-is-kept-yours) has the rules, and `spec/008-the-page.md` in the repository the reasons.

## Threading

The server answers each request on a thread of its own, and a workspace is read in the background, eight scopes at a time. Nothing blocks the page: it draws at once and fills as the workspace arrives.

## Testing

Everything above `infrastructure/` runs against in-memory fakes of the ports (`tests/fakes.py`). The server is asked over real HTTP, and the page is driven in a real browser — Chrome, over its debugging pipe (`tests/chrome.py`): real keys, real files, the real clipboard.
