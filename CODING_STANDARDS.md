# Coding Standards

Each rule overrides a default. Project linters and configs win over this file; delete rules that don't fit.

## Boundaries
- Validate at the **boundary** (HTTP, CLI, files, env, third-party responses) with a schema, then pass typed values inward and trust them: one owner per check beats defensive re-checks nobody can reason about.
- Fail **loud**: let errors propagate with added context; catch only where you can recover or translate for a user. A swallowed error turns a crash into corrupted state.
- Keep data immutable once it crosses a module **boundary**; mutate locals freely. Aliasing bugs live at boundaries, not in loop counters.
- Load config and secrets at startup and fail fast when a value the current mode requires is missing, so the gap surfaces at deploy, not mid-request; keep deliberate optional values (demo fallbacks, local health checks) optional.

## Structure
- Group by feature, not by layer (`billing/` over `controllers/`), so one change touches one folder.
- Add an abstraction (repository, response envelope, interface) at the second real caller, not the first: speculative layers are the costliest code to delete.
- Comment the **why** (constraint, gotcha, rejected alternative); names carry the what.

## Tests
- A bug fix starts **red**: a test that fails on the bug before the fix touches code. No red, no proof.
- When a test goes red, fix the code. Change the test only when you can name what it got wrong, and say so in your summary.
- Test through public interfaces, so tests protect refactors instead of blocking them.

## Changes
- Keep each diff to one purpose; report unrelated problems instead of fixing them, so review sees one story.
- Put durable knowledge in the project's existing docs; ask before creating a new top-level file.
