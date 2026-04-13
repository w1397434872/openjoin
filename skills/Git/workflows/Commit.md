# Commit Workflow

Stage changes and create a commit using the `ai-commit` script, which generates an AI-assisted conventional commit message and opens the editor for review.

## Workflow Steps

### 1. Check for Changes

Run `git status --porcelain` to understand the current state. In porcelain output, the first column indicates staged status and the second column indicates unstaged status (`??` = untracked).

| Situation | Action |
|-----------|--------|
| Any line has a non-space first column (staged changes exist) | Proceed to Step 3 |
| Lines exist but all have a space first column (unstaged/untracked only) | Ask user what to stage, then proceed to Step 2 |
| No output at all | Report "Nothing to commit" and stop |

### 2. Stage Changes (if needed)

Stage the files the user specified using `git add <files>`.

### 3. Commit

Run `ai-commit -y` via Bash to generate and commit without opening an editor. If a motivation argument was provided, pass it: `ai-commit -y "<motivation>"`.

The command will:
1. Generate a commit message using Claude
2. Print the generated message to stdout (editor is skipped with `-y`)
3. Run pre-commit hooks (fixing issues automatically if possible)
4. Create the commit

### 4. Report Result

After `ai-commit` completes, run `git log -1 --stat` to get the commit details and output a compact summary.

## Output

IMPORTANT: Be silent during execution. Do not narrate your actions or explain what you're doing.

When complete, output ONLY a compact summary in this exact format:
```
Committed: <type>(<scope>): <description>
  <N> files changed, <insertions> insertions(+), <deletions> deletions(-)
```

Nothing else. No explanations, no status updates, no tool output.

## Guidelines

- NEVER reimplement commit message generation — always delegate to `ai-commit`
- Always pass `-y` to skip the editor — Claude Code cannot interact with terminal editors
- The `ai-commit` script handles staged-change detection, message generation, and hook execution
- If `ai-commit` exits non-zero, report the error and stop
- Pass the motivation argument verbatim; do not modify or truncate it
