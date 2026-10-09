# 005 — for agents

**Status:** draft. **Not built.** Phase three. The owner said "maybe have skills and other
things to help agentic development"; everything below is a proposal, and whether it is wanted
is the owner's to say.

## Why

Ask a coding agent to "add a pipeline for this API and run it every night" in a dlt project
on Databricks. It gets the dlt half right: dltHub ships rules, skills and an MCP server for
that (`dlthub ai`, in `dlt[hub]`) *(dlt)*. It gets the Databricks half wrong in the ways
[000](000-what-leeghwater-is.md#why-it-exists) lists, because nothing it has read says
otherwise. And it writes `dlt.pipeline(...)` with a destination and a schema in it, as every
example on the web does.

## Requirements

- **R1 — Skills for what leeghwater adds, and only that:**
  - add a pipeline to the app, and run it here;
  - give it a secret from a scope — by name, with the value never put in a file, and with
    where a secret is made (the Databricks CLI);
  - put it in the job;
  - read the first lines of a run, and use `doctor` when a run fails on Databricks.
- **R2 — Each rule comes with its reason.** A short page of hard rules: what to call, what
  never to call directly, and why, rule by rule. An agent keeps a rule it was given a reason
  for, and can tell when the reason doesn't apply. For one: make the pipeline with
  `leeghwater.create_pipeline` and never `dlt.pipeline`, because where a run loads is the
  run's to say ([001/R2](001-the-runner.md#requirements)); ask for a secret with
  `dlt.secrets.value` and never read one by hand, because of
  [003/R9](003-secrets.md#requirements).
- **R3 — They don't repeat dlt's.** How a source is written is dltHub's to teach. Where its
  skills are installed, leeghwater's point to them.
- **R4 — They come with the package and are written into a project by a command.** With
  `leeghwater init --agents` for a new project, and `leeghwater agents install` for one that
  exists — under the same rule as the scaffold: nothing is overwritten
  ([004/R8](004-the-scaffold.md#requirements)).
- **R5 — One format, more than one agent.** Each skill is a `SKILL.md` in the Agent Skills
  format, for the agents that read it, and the same text in short in an `AGENTS.md` section
  for the ones that don't.
- **R6 — The commands answer an agent as well as a person.** `list` and `doctor` as JSON, a
  scaffold that needs no terminal, and errors that name the next command. These are built
  ([001/R10](001-the-runner.md#requirements), [004/R7](004-the-scaffold.md#requirements)).
- **R7 — A skill is tested like a doc.** Every command a skill names exists and takes the
  options the skill gives it; a test runs them.

## Not in this spec

- **Tools in dlt's MCP server,** through dlt's hook for them. Later, if the skills show a
  need.
- **How to write a dlt source.** R3.
- **Anything that runs a model.**

## To decide

- **Whether to build it at all.**
- **Which agents first.** Proposed: Claude Code (skills) and an `AGENTS.md` section, which
  Codex and others read; Cursor after.

## Done when

An agent that has only the project and the installed skills adds a second pipeline that
takes a secret from a scope, runs it locally, and adds it to the job — with
`create_pipeline` and `run`, without a secret's value in a file, and without a destination
or a schema named in code.
