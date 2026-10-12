# Git and PRs

## Before committing

Run the checklist in `docs/agents/security.md` against the staged changes.

## Commits

Russian, narrative, no conventional-commit prefix: say why it was done this way,
not just what the diff shows. Follow the style of `git log`.

## Pull requests

Fill `.github/pull_request_template.md`; «Решения и обоснование» is mandatory for
non-trivial changes. Write it from the whole branch (`git log origin/main..HEAD`),
not just the last commit.
