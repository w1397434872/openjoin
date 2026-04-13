# Rebase Workflow

Rebase the current branch onto a target using the `ai-rebase` script, which handles fetching, branch updates, and AI-assisted conflict resolution.

Arguments: $ARGUMENTS

## Workflow Steps

### 1. Determine Target

| Argument | Target |
|----------|--------|
| (none) | Default branch |
| `origin` | Default branch |
| `origin/<branch>` | `<branch>` |
| `<branch>` | `<branch>` |

### 2. Rebase

Run `ai-rebase` via Bash with the target argument (or no argument for default branch):

```bash
ai-rebase <target>
```

The command will:
1. Fetch origin
2. Update the local target branch (worktree-aware)
3. Rebase onto the target
4. If conflicts occur, invoke Claude to resolve them automatically

### 3. Report Result

After `ai-rebase` completes, run `git log --oneline <target>..HEAD` to count rebased commits and output a compact summary.

## Output

IMPORTANT: Be silent during execution. Do not narrate your actions or explain what you're doing.

When complete, output ONLY a compact summary in this exact format:
```
Rebased N commits onto <target>
[If conflicts were resolved:]
  - <file>: <one line describing resolution>
```

Nothing else. No explanations, no status updates, no tool output.

## Guidelines

- NEVER reimplement rebase logic — always delegate to `ai-rebase`
- The `ai-rebase` script handles fetching, branch updates, conflict resolution, and worktree detection
- If `ai-rebase` exits non-zero, report the error and stop
- Pass the target argument verbatim; do not modify it
