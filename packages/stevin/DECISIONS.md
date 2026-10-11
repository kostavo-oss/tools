# Decisions

Why stevin is the way it is, oldest first. An entry is here only when it says why, or
what was tried and put aside. What must be true of the code is in [RULES.md](RULES.md).

**An entry is never edited.** A decision that changes gets a new entry at the end that
names the one it supersedes. "The design" is the document stevin was built from in
September 2026 (entry 22). Entries 1 to 21 were written on 2026-10-11 from that
document, the changelog and git; each carries the date of the decision.

1. **2026-09-18 — Unity Catalog is the state; there is no state file** (OWN-1). Why:
   nothing to store, lock or repair, no import step for a table that already exists,
   and a change made by hand shows up as drift.
2. **2026-09-18 — The differ and the planner are pure** (PLAN-1). Why: everything
   between reading and running is then tested without a workspace, and the same input
   gives the same plan.
3. **2026-09-18 — The loader validates by hand** (SPEC-1). Why: every error can point
   at its file, line and column. It replaced the design's Pydantic or msgspec.
4. **2026-09-18 — A rename is declared with `renamed_from`, never inferred.** Why: a
   renamed column looks exactly like a drop and an add, and a wrong guess destroys
   data.
5. **2026-09-18 — `is_applied` asks the model whether a step is already done** (APL-2).
   Why: it reuses tested code, where a check query per step would be SQL nobody can
   verify offline. It replaced the design's precheck and postcheck on every step; those
   two stay only for a precondition a statement would fail on, and for a staged copy.
6. **2026-09-18 — A rewrite is staged in two statements** (RW-2). Why: the expensive
   step is then safe to repeat and is checked before the table is touched. It replaced
   the design's single `CREATE OR REPLACE TABLE … AS SELECT`. Since 2026-09-20 a
   rewrite that converts no value is one statement again: a staged copy could catch
   nothing there, and the data is written once.
7. **2026-09-18 — A spec may be SQL, for what sqlglot parses into structure.** It
   replaced the design's non-goal of SQL as a source. Put aside: parsing around sqlglot
   to give SQL a feature. Such a feature goes into YAML, which stays the complete
   format.
8. **2026-09-18 — Schemas, volumes and functions are never dropped** (OWN-4). Why:
   nothing on them says stevin made them, and a dropped volume loses its files.
9. **2026-09-19 — A nested field's NOT NULL is an ordinary ALTER, and a map's key
   widens in place.** The design guessed a rewrite for both. A workspace said otherwise,
   and the probes hold the evidence.
10. **2026-09-20 — A bundle is resolved by asking the Databricks CLI.** Why: its answer
    carries the variables, the lookups and the names a deploy really uses. It replaced
    reading `databricks.yml` and interpreting it. Since 2026-09-22 a CLI that is there
    and fails stops the command; reading the file is only for a machine without a CLI,
    and says *unknown* where it cannot know.
11. **2026-09-22 — `manage:` hands part of a table to another tool** (ACC-6). Why: two
    tools that write the same grants or tags undo each other's work.
12. **2026-09-23 — A history schema is optional** (APL-5). Why: a host that deploys
    many products got three tables of stevin's bookkeeping per catalog and could not
    opt out, while stevin's own state is on the tables. It replaced an `apply` that
    refused without one.
13. **2026-09-26 — The Databricks assumptions are probes in `src/`, run by `stevin
    verify`** (DBX-1). Why: the live tests ran on one workspace and one runtime, and a
    user can now settle each on their own. It replaced a test file of assumptions.
14. **2026-09-27 — A step has no time limit** (APL-6). Why: a rewrite of a big table
    takes as long as it takes, and a limit that gave up on a statement left it running.
15. **2026-10-07 — deltaplan becomes stevin, and four names stay** (NAME-1). Why they
    stay: renaming what is written onto tables orphans every table that carries it.
    That is a migration, and none is decided.
16. **2026-10-09 — The scope: tables and access no transformation tool owns.** Hooks
    and SQL functions of their own leave (SPEC-2): they made stevin a second
    transformation tool. Views stay: a team without dbt models with them, and Delta
    Sharing needs a filtered view where a mask cannot go. Seeds stay: lookup tables are
    in the scope. `using:` stays: filling a new required column is part of the
    migration. It replaced the design's non-goals. The README has the scope.
17. **2026-10-09 — ABAC policies are read and never written** (ACC-3). Why: a policy on
    a schema decides who sees what in every table below it, so writing one from a
    table's spec would let a pull request about one table change the access to a
    hundred.
18. **2026-10-09 — dbt's tables are refused; other tools' tables may be governed**
    (OWN-7). Why refused: dbt's config carries grants and tags, and a `table`
    materialisation makes the table again and drops its masks, so two writers would
    undo each other on every run.
19. **2026-10-09 — A table's shape may come from an ODCS contract** (SPEC-3). Why: a
    shape written a second time in a spec is a second source of truth, and the two
    drift.
20. **2026-10-10 — A plan does not depend on what the workspace accepts** (PLAN-2). Why:
    the same specs and tables give the same plan everywhere. A plan does not read what
    `verify` found: an assumption that fails is a refused statement at `apply`, and
    the remedy is the spec.
21. **2026-10-11 — The live suite runs by hand, with a budget of tables** (TEST-3,
    TEST-4). Why: about fifteen runs in a day took the metastore's estimate to 510
    tables of 500 while it held 46, and the owner could not create a table. It replaced
    a suite that ran on every pull request and made over a hundred tables a run.
22. **2026-10-11 — One place per fact, and no design document.** Why: an audit found 61%
    of the design page's checked statements true as written, under 29 corrections and
    notes, and `CLAUDE.md` called it the source of truth. It replaced that page, a
    `CLAUDE.md` that told how stevin was built, and rules that no test was tied to.
    `CLAUDE.md` says where each fact lives now.
23. **2026-10-11 — A key of `owned_elsewhere` is split first, and each part is filled
    in on its own** (OWN-8). Why: the dot and the `*` are the key's own syntax, and a
    reference such as `${resources.schemas.raw.name}` holds dots that are not. Split
    outside the braces, a reference is one part whatever it holds, the three parts are
    checked when the project file is read, before a target is chosen, and what a
    variable stands for is never read as syntax. Rejected: filling the key in first and
    splitting after, the way a spec's `table:` name is read. A value with a dot would
    turn into more parts and a value of `*` into a pattern, and the check for three
    parts would have to wait for a target. Also rejected: leaving out a key whose
    reference has no value for a target, which the code did before. A pattern that is
    left out is a table stevin may claim, so it is an error at the key.
24. **2026-10-11 — A table under a row filter or column mask policy is refused a
    rewrite** (RW-4), as a table with a mask or row filter of its own is. Why: a
    rewrite reads the table as the applying principal sees it and copies that into a
    staging table the policy may not cover. stevin cannot tell, offline or cheaply,
    whether that principal is let off the policy: it hangs on the policy's conditions,
    the table's tags and group membership, which Databricks works out at query time. A
    wrong guess either leaves the data outside the policy or writes the filtered or
    masked copy over the table. Neither consequence has been tried on a workspace: the
    refusal is the safe side of an untested question. Put aside: a warning, which a
    reviewer can miss on the one plan where it matters, and "refuse unless the
    principal is exempt", which is the guess. `--clone` is refused for such a table for
    the first reason. Where the policies were not read, a rewrite is planned with a
    warning (RW-5): refusing there would refuse every rewrite of a project that hands
    policies over.
25. **2026-10-11 — A key of `schemas:` is read as a key of `owned_elsewhere` is**
    (OWN-9): split first, each part filled in on its own, and an error at the key when
    a reference has no one name for the target. Why an error: a key that is left out
    gives its schema the target's mode. Under a `strict` target, a schema the file
    marks `additive` then has its orphaned tables dropped, and under an `additive`
    target a schema marked `strict` keeps them without a word. Rejected: leaving the
    key out only where that is the safe side, when the target is `additive`. The file
    would then be read by two rules, and a `strict` that does nothing is still not
    what it says.
26. **2026-10-11 — A nested field's name is quoted in a statement and bare where it is
    shown** (SQL-1). Why: `STRUCT<select:INT>` leaves it to Databricks whether `select`
    is a name there, and a rule with an exception for types is a rule a reader has to
    check each time. A type is compared as a value, so the two spellings cannot turn
    into drift. Rejected: saying in the rule that a plain nested name is left bare,
    with a probe for a reserved word. That keeps a second way to put a name into SQL.
    A quoted nested name is read from the manual and has not been sent to a workspace.
27. **2026-10-11 — The refusal covers every step that reads a table's data to write it
    somewhere: a rewrite, a clone, a backfill** (RW-4, RW-6, RW-7). Entry 24 refused
    the rewrite and the clone under a policy. A clone of a table with a mask or row
    filter of its own was still planned, and so was a `using:` backfill on any masked
    or filtered table. Why they are refused too: each runs as the applying principal.
    A clone is a second table over the same rows, which stevin keeps. A backfill is an
    `UPDATE` that reaches only the rows that principal can see, so the rows a filter
    hides stay NULL and a `NOT NULL` after it fails or passes for the wrong reason,
    and it writes a masked column as the principal sees it into a column without the
    mask. The first of those holds for a `using:` that reads a constant or another
    table, so the expression is not looked at. Put aside: a warning on the step, for
    the reason in entry 24, and refusing only a `using:` that names a masked column,
    which leaves the hidden rows. The manual says a table with a row filter or column
    mask is not cloned at all. It does not say what an `UPDATE` sees. None of this has
    been tried on a workspace: the refusals are the safe side of untested questions.
28. **2026-10-11 — A refusal is an exit code, and the listing is a command of its own**
    (APL-8, OWN-10). A program that runs `apply` could tell a stale plan from a failed
    step only by matching stevin's sentences. Why exit codes: `drift` already answers
    with one, a code cannot be reworded, and it is there when the output is wrapped or
    lost. Why 3 and 4, not 2: the command line itself exits 2 for an option it does
    not know, and `drift` uses 2 for drifted. Why two codes: "plan again" and "say
    `--allow-destructive`" are different things to do next. Put aside: a `--format
    json` result for `apply`, a second output format to keep true for one field.
    Why `list` is a command and not an option: `drift` exists to diff and its exit code
    means drifted, `import` writes files for one schema, and `access` is about one
    table and who may read it. An option that turns one of them into "list and do not
    diff" would undo what that command is for. It uses `--json`, as `doctor`, `verify`
    and `access` do; `--format` is for the renderings of a plan.
29. **2026-10-11 — "The bundle has not deployed this yet" is exit code 5** (PLAN-5). A
    tool that deploys the bundle and then runs stevin plans both before either has
    run. On a target that was never deployed stevin refused, with exit 1, and the tool
    could not tell that from a spec that does not read. Why a code and not the words:
    the reasons of entry 28. Why 5 and not 3: 3 means "this plan will never run, plan
    again", and here there is no plan and nothing to fix; a program does something
    else next, which is to deploy. Why the same code on `drift` and on `apply` without
    a plan file: they run the same check, and one meaning per number across the
    commands is easier to hold than a table per command. Why `list` stays 0: it makes
    no plan, and "not there" is its answer. Put aside: stevin creating the schema,
    which is how a later `databricks bundle deploy` meets an object it did not make;
    and planning the tables as if the schema were there, a plan of a workspace nobody
    has read. Only this refusal has the code. A governed table that its owner has not
    made yet is still exit 1.
