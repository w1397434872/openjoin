# Amend Workflow

Amend staged changes into an existing commit using the `ai-amend` script, which folds in the changes and regenerates the commit message with Claude.

## Workflow Steps

These workflow steps MUST be followed exactly as written.

### 1. Determine Target Commit

| Argument | Target |
|----------|--------|
| (none) or `HEAD` | HEAD |
| `<SHA>` | That specific commit |

### 2. Check for Staged Changes

Run `git diff --cached --quiet` to check for staged changes.

| Situation | Action |
|-----------|--------|
| Staged changes exist | Proceed to Step 3 |
| No staged changes, target is HEAD | Ask user what to stage, then proceed to Step 3 |
| No staged changes, target is non-HEAD | Error: "No staged changes to amend into `<SHA>`. To rewrite only the message, use: `/git reword <SHA>`" — stop |

### 3. Check Push Status

Run:

```bash
git branch -r --contains <SHA>
```

If results are returned, warn the user:

```
Warning: Commit <SHA> has been pushed. Amending will rewrite history and require force-push.
```

**Ask the user to confirm before proceeding.** If they decline, stop.

### 4. Amend

Run `ai-amend -y <SHA>` via Bash (or `ai-amend -y` for HEAD):

```bash
ai-amend -y <SHA>
```

The command will:
1. Fold staged changes into the target commit
2. Regenerate the commit message using Claude to reflect the combined changes
3. Print the generated message to stdout (editor is skipped with `-y`)
4. Apply the amended commit (amend for HEAD, fixup + autosquash for non-HEAD)

### 5. Report Result

After `ai-amend` completes, get the amended commit details:

```bash
git show --stat --format="%h %s" HEAD
```

For non-HEAD amends, the SHA may have changed during rebase.

Output format:
```
Amended <short-SHA>: <type>(<scope>): <description>
  <N> files changed, <insertions> insertions(+), <deletions> deletions(-)
```

## Guidelines

- NEVER reimplement amend logic — always delegate to `ai-amend`
- Always pass `-y` to skip the editor — Claude Code cannot interact with terminal editors
- The `ai-amend` script handles fixup creation, autosquash, and message regeneration
- If `ai-amend` exits non-zero, report the error and stop
- NEVER skip the pushed-commit warning — force-pushing rewrites shared history
- For non-HEAD amends, staged changes are REQUIRED — redirect to `/git reword` if absent
- Silent during execution — output only the compact summary when complete
