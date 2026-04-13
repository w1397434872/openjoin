# Reword Workflow

AI-rewrite a commit message for any commit by SHA. Delegates to the `ai-reword` script, which uses Claude to analyze the commit's diff and generate an improved conventional commit message.

## Workflow Steps

These workflow steps MUST be followed exactly as written.

### 1. Validate Arguments

The SHA argument is required.

| Situation | Action |
|-----------|--------|
| No SHA provided | Error: "Usage: /git reword <SHA>" — stop |
| Invalid SHA | Error: "Invalid commit: <SHA>" — stop |
| Valid SHA | Proceed to step 2 |

Validate the SHA:

```bash
git rev-parse --verify <SHA>^{commit}
```

If the command exits non-zero, the SHA is invalid.

### 2. Check Push Status

Run:

```bash
git branch -r --contains <SHA>
```

If results are returned, warn the user before proceeding:

```
Warning: Commit <SHA> has been pushed. Rewording will rewrite history and require force-push.
```

Continue regardless — this is an informational warning, not a blocker.

### 3. Reword

Run `ai-reword -y <SHA>` via Bash to generate and apply without opening an editor:

```bash
ai-reword -y <SHA>
```

The command will:
1. Generate an improved commit message using Claude
2. Print the generated message to stdout (editor is skipped with `-y`)
3. Apply the reworded message (amend for HEAD, rebase for non-HEAD)

### 4. Report Result

After `ai-reword` completes, show the new commit message:

```bash
git log -1 --format="%h %s" <SHA>
```

For non-HEAD commits, `<SHA>` may have been rebased to a new hash — use `HEAD` if the short SHA is no longer valid.

Output one line:

```
Reworded <short-SHA>: <new-type>(<scope>): <new-description>
```

## Guidelines

- Always validate the SHA before calling `ai-reword` — the script validates too, but catching it early gives a cleaner error message
- The push warning is informational only — do not block or ask for confirmation; the user knows what they are doing
- Always pass `-y` to skip the editor — Claude Code cannot interact with terminal editors
- Do not reimplement message generation — `ai-reword` handles all Claude interaction
- Silent during execution — output only the compact summary line when complete
- Do not reword multiple commits at once
