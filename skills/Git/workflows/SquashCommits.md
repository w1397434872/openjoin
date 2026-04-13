# SquashCommits Workflow

Squash a range of commits into a single commit using the `ai-squash-commits` script, which performs a non-interactive rebase and generates an AI commit message for the result.

## Workflow Steps

These workflow steps MUST be followed exactly as written.

### 1. Parse Range Argument

The `<range>` argument is required. Supported formats:

| Input Format | Example | Description |
|--------------|---------|-------------|
| `last <N>` | `last 3` | Squash the last N commits (N >= 2) |
| `<SHA1>..<SHA2>` | `abc123..def456` | Squash SHA1 through SHA2 |
| `<SHA1> <SHA2>` | `abc123 def456` | Same as above, space-separated |
| `since <branch>` | `since main` | All commits since diverging from branch |

If no range is provided, Error: "Usage: /git squash <range>" — stop.

### 2. Warn If Commits Have Been Pushed

Find the oldest commit in the range and check:

```bash
git branch -r --contains <oldest-SHA>
```

If results are returned, warn the user:

```
WARNING: One or more commits in this range have been pushed to a remote branch.
Squashing will require a force-push after completion.
Proceed? (yes/no)
```

**Ask the user to confirm before proceeding.** If they decline, stop.

### 3. Squash

Run `ai-squash-commits -y <range>` via Bash:

```bash
ai-squash-commits -y <range>
```

Pass the range argument verbatim. The command will:
1. Parse the range and determine the base commit
2. Validate at least 2 commits exist in the range
3. Squash all commits into one using non-interactive rebase
4. Generate a new commit message using Claude for the combined diff
5. Print the generated message to stdout (editor is skipped with `-y`)
6. Apply the new message

### 4. Report Result

After `ai-squash-commits` completes, output a compact summary:

```bash
git show --stat --format="%h %s" HEAD
```

Output format:
```
Squashed N commits into <short-SHA>: <type>(<scope>): <description>
  <diff stat>
```

## Guidelines

- NEVER reimplement squash logic — always delegate to `ai-squash-commits`
- Always pass `-y` to skip the editor — Claude Code cannot interact with terminal editors
- The `ai-squash-commits` script handles range parsing, rebase, and message generation via `ai-reword`
- If `ai-squash-commits` exits non-zero, report the error and stop
- Always warn before squashing pushed commits — the user must understand a force-push will be required
- Silent during execution — output only the compact summary when complete
