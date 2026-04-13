# workflows/

Workflow files for the Git skill. Each file defines the steps for a specific git operation.

- `Commit.md` — Stage and commit changes using AI-generated conventional commit messages via the `ai-commit` script.
- `Rebase.md` — Rebase the current branch onto a target using the `ai-rebase` script with AI-assisted conflict resolution.
- `Amend.md` — Amend staged changes into any commit (HEAD or non-HEAD) via the `ai-amend` script with AI-regenerated messages.
- `Reword.md` — AI-rewrite a commit message for any commit by SHA using the `ai-reword` script.
- `SquashCommits.md` — Squash a range of commits into one via the `ai-squash-commits` script with an AI-generated message.
- `Push.md` — Push the current branch to the remote, setting up tracking if needed.
