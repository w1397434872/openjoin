# Push Workflow

Push the current branch to the remote, setting up tracking if needed.

## Workflow Steps

### 1. Determine Current Branch

```bash
git branch --show-current
```

If the output is empty (detached HEAD), Error: "Cannot push: detached HEAD state" — stop.

### 2. Check for Unpushed Commits

```bash
git log --oneline @{upstream}..HEAD 2>/dev/null
```

If the command fails (no upstream), all local commits will be pushed when tracking is set up in step 3.

If the command succeeds but returns no output, report "Nothing to push — branch is up to date with remote" and stop.

### 3. Push

Determine whether the branch has an upstream set:

```bash
git rev-parse --abbrev-ref @{upstream} 2>/dev/null
```

| Situation | Command |
|-----------|---------|
| Upstream exists | `git push` |
| No upstream | `git push -u origin <branch>` |

If push is rejected (non-fast-forward), do NOT force-push. Instead, automatically rebase and retry:

1. Run `ai-rebase` to rebase onto the upstream branch:
   ```bash
   ai-rebase
   ```
2. If the rebase succeeds, retry the push (same command as above).
3. If the rebase fails, report the error and stop.
4. If the second push also fails, report the error and stop — do not retry again.

### 4. Report Result

After push succeeds, output a compact summary:

```bash
git log --oneline @{upstream}..HEAD 2>/dev/null || echo "(new branch)"
```

Output format:
```
Pushed <N> commits to origin/<branch>
```

Or for a new branch:
```
Pushed <branch> to origin (new branch, tracking set)
```

## Output

IMPORTANT: Be silent during execution. Do not narrate your actions or explain what you're doing.

Output ONLY the compact summary when complete. Nothing else.

## Guidelines

- NEVER force-push — if push is rejected, rebase and retry (once)
- NEVER push to main/master without explicit user confirmation
- Always use `-u` when pushing a branch for the first time to set up tracking
- If the branch is main or master, ask the user to confirm before pushing
