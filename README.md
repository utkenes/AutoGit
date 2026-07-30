# AutoGit

Plan clean commits, run quality checks, and push safely.

AutoGit is a local-first Git assistant for developers who want clean, reviewed
commits without giving a tool unchecked control of their repository.

## What it is (and is not)

AutoGit analyzes local changes, proposes Conventional Commit groups, runs
enabled quality checks, and waits for approval before committing or pushing.
Unlike GitHub Desktop, it focuses on explaining and planning a commit workflow;
it does not replace a graphical Git client or host repositories.

## Install

```bash
pipx install autogit
# or, from a checkout during the beta
pip install .
```

Python 3.12+ is required. Verify the installation with `autogit --version`.

## 60-second quick start

```bash
cd path/to/your/git-project
autogit start
```

Review the proposed groups, then choose approve, edit messages, or cancel.
AutoGit only creates local commits after explicit approval. Push always requires
a separate confirmation.

## Commands

- `autogit start` — guided planning, checks, approved commits, and optional push.
- `autogit start --dry-run` — show the plan, checks, and push target without
  changing Git state or config.
- `autogit start --auto` — accepts the plan and may apply a low-risk lint fix;
  it still cannot push, change remotes, install dependencies, or perform
  destructive operations without the user.
- `autogit plan --json` — emit a machine-readable plan with no Rich/log output.
- `autogit undo` — undo the last unpushed AutoGit workflow when HEAD and the
  working tree are unchanged.
- `autogit status`, `autogit doctor`, and `autogit config` — inspect the setup.

`autogit watch` and `autogit commit` remain legacy commands; `start` is the
recommended workflow.

## Quality recovery

When a supported linter fails, AutoGit can suggest a low-risk fix such as
`python -m ruff check . --fix`. It shows the command and requires approval
unless `--auto` was selected. Test logic failures are never automatically
rewritten. A workflow applies an automatic fix at most once by default.

## Safety and privacy

- Existing staged files stop the workflow and are never cleared.
- Merge/rebase/cherry-pick/revert, detached HEAD, Git `index.lock`, and another
  AutoGit workflow block commits.
- Secret scanning runs on staged content and masks findings.
- `.git` and `.autogit` are excluded from commit candidates.
- No source code, diffs, repository URLs, or secrets are sent to an external
  server in v0.1.0; analysis runs locally.

## Supported checks

AutoGit can detect Python tests, JavaScript test scripts, Ruff, ESLint, and
Biome. All test/lint/auto-fix/commit/push options are disabled by default until
the user approves them.

## Beta limitations and feedback

Commit grouping is deterministic rather than AI-generated. Remote divergence is
blocked conservatively, and AutoGit does not create GitHub repositories. Please
include the command, sanitized output, and platform details in beta feedback.

See [CHANGELOG.md](CHANGELOG.md) for release notes.
