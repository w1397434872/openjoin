---
name: Git
description: "Git operations including commit, push, rebase, amend, reword, and squash. USE WHEN the user wants to perform git operations like committing, pushing, rebasing, amending commits, rewriting commit messages, or squashing commits."
argument-hint: "<command> [args]"
model: sonnet
allowed-tools: Bash(git:*), Bash(ssh-add:*), Bash(ai-commit:*), Bash(ai-amend:*), Bash(ai-rebase:*), Bash(ai-reword:*), Bash(ai-squash-commits:*), Read, Edit
---

You perform git operations by routing to the appropriate workflow based on the user's argument.

## When Invoked

1. Verify the current directory is inside a git repository by running `git rev-parse --git-dir`. If it exits non-zero, report "Not a git repository" and stop.
2. Verify SSH keys are loaded by running `ssh-add -l`. If it exits non-zero or reports "The agent has no identities", report "No SSH keys loaded. Run `ssh-add` to add your keys." and stop.
3. Parse the first argument to determine the workflow
4. If no argument or unrecognized argument, ask the user what they want to do
5. Read the selected workflow file completely
6. Execute the workflow steps exactly as written
7. Report results in compact summary format

## Workflow Routing

| Argument | Workflow | Description |
|----------|---------|-------------|
| `commit [motivation]` | [Commit](./workflows/Commit.md) | Stage and commit with AI-generated message |
| `rebase [target]` | [Rebase](./workflows/Rebase.md) | Rebase onto target with conflict resolution |
| `amend [SHA]` | [Amend](./workflows/Amend.md) | Amend any commit with content and/or message changes |
| `reword <SHA>` | [Reword](./workflows/Reword.md) | AI-rewrite a commit message |
| `squash <range>` | [SquashCommits](./workflows/SquashCommits.md) | Squash commits into one |
| `push` | [Push](./workflows/Push.md) | Push current branch to remote |

## Reference

- [Conflict Resolution](./reference/conflict-resolution.md) — Resolving git conflicts (zdiff3 markers, mergiraf, resolution process)
