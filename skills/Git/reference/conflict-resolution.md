# Conflict Resolution

Reference guide for resolving git conflicts during rebase, cherry-pick, or merge operations.

## Environment

The git configuration includes tools that assist with conflict resolution:

- **mergiraf**: A syntax-aware merge driver (`* merge=mergiraf`) that automatically resolves many conflicts by understanding language structure. When mergiraf succeeds, no manual intervention is needed.
- **zdiff3 conflict style**: Conflict markers include a third section showing the original (base) version of the code, not just ours/theirs. This makes it easier to understand what each side changed.
- **rerere**: Enabled globally — git records how you resolve conflicts and automatically applies the same resolution if the same conflict recurs.

## zdiff3 Conflict Markers

```
<<<<<<< HEAD (ours — the branch being rebased)
  our version of the code
||||||| (original — the common ancestor)
  original version before either side changed it
=======
  their version of the code
>>>>>>> commit-message (theirs — the target branch)
```

Compare each side against the **original** section to understand what changed, rather than comparing ours vs theirs directly.

## Resolution Process

For each conflicting file:

### 1. Understand the Target Branch Changes

Before editing anything, examine what the target branch did to the file:

```bash
git log -p -n 3 <target> -- <file>
```

This shows the intent behind the target's changes — not just the diff, but the commit messages explaining why.

### 2. Understand the Current Branch Changes

Read the conflict markers in the file. Compare the **ours** section against the **original** section to isolate what the current branch changed and why.

### 3. Resolve

The goal is to preserve the intent of **both** sides:

| Situation | Resolution |
|-----------|-----------|
| Both sides changed different parts of the same region | Combine both changes |
| Both sides made the same change | Keep one copy |
| One side refactored, the other added new code | Apply the new code within the refactored structure |
| Changes are logically incompatible | Ask the user for guidance |

When editing, remove all conflict markers (`<<<<<<<`, `|||||||`, `=======`, `>>>>>>>`) and produce a clean merged result.

### 4. Stage and Continue

```bash
git add <file>
git rebase --continue
```

Repeat for each conflicting file until the operation completes.

### 5. When to Ask for Help

Stop and ask the user if:

- The conflict involves a semantic decision (e.g., two different approaches to the same problem)
- The changes are logically incompatible and you cannot determine which intent should win
- The conflict spans a large region and the combined result is unclear
- A test or build would be needed to verify correctness
