---
name: git-attribution
description: Find and remove AI co-author attribution from a git repo - the Co-Authored-By trailer and "Generated with" footer that Claude Code, Copilot, Codex, Cursor and others add to commits and that put the agent in your GitHub contributor graph. Use this whenever the user says Claude (or an AI) showed up as a contributor, asks to remove Co-Authored-By or stop adding it, asks whether commits are still being attributed to Claude, wants AI attribution scrubbed from history, wants a repo checked for AI co-authors before pushing or publishing, or asks to block pushes that carry the trailer. Also use it before you push to a repo where the user has said they want no AI attribution.
---

# git-attribution

Claude Code appends `Co-Authored-By: Claude ... <noreply@anthropic.com>` to every commit
it writes and `Generated with Claude Code` to every PR body, unless a setting turns it
off. Nothing tells the user it happened; they find out when Claude appears in their
contributor graph. The same goes for Copilot, Codex, Cursor and the rest. This skill
answers three questions - is it still being added, where is it already, and how do I
get it out - and installs a guard so it does not come back.

The script is at `scripts/attribution.py` next to this file (installed as a skill that
is `~/.claude/skills/git-attribution/scripts/attribution.py`). Stdlib-only, read-only
unless `--apply` is passed, and it never pushes.

## Pick the mode from what the user asked

| The user says | Run |
|---|---|
| "is Claude still being added", "did the setting take", "check this repo" | default |
| "Claude is in my contributors", "remove the co-authored-by lines" | default, then `--fix` |
| "just turn it off" | `--fix --settings-only --apply` |
| "scrub the history" (they already confirmed the force-push) | `--fix --history-only --apply` |
| "make sure it never gets pushed again" | `--guard --apply` |
| "check my PRs too" | add `--prs` |
| "only Claude, I don't care about Copilot" | add `--agents claude` |
| "check before I publish" / CI | `--strict --no-settings` |

Pass `--repo PATH` when they mean a repo other than the cwd. `--json` when you need to
process the result.

## Steps

1. Run the default report first, even when they asked for the fix. It tells you what
   the fix would touch. Read the four lines that matter:
   - **setting** - `ON` means new commits will keep getting the trailer. The source
     column says which file decided it. A project `.claude/settings.json` can override
     a user-level `OFF`; say so when that is the case, because switching it off in the
     user file will not help.
   - **commits** - how many carry attribution and how many are **pushed**. Local-only
     ones can be rewritten freely. Pushed ones need a force-push afterwards, and that
     is the user's call, not yours.
   - **prs** (with `--prs`) - PR bodies with the footer. These are not fixed by a
     history rewrite; the plan lists the URLs to edit by hand.
   - **guard** - whether the pre-push hook is installed.

2. Answer the question first. If they asked "is it still being added", the setting
   line is the answer; do not lead with the commit list. If they asked "why is Claude
   in my contributors", the commit list is the answer; name the oldest one.

3. Before `--fix --apply`, show them the plan (`--fix` alone) and confirm two things
   out loud: that the working tree is clean (the rewrite refuses otherwise), and, if
   any tainted commit is pushed, that they are willing to force-push and that nobody
   else has a clone that will break. Do not run the rewrite on a shared branch
   without that confirmation. The rewrite keeps a backup at `refs/original/*` and
   leaves remotes alone; commits older than the first tainted one keep their sha.

4. After a rewrite the tool re-scans and reports how many remain (it should be 0).
   The push is yours to run only if the user asks:
   `git push --force-with-lease --all && git push --force-with-lease --tags`.
   Tell them GitHub's contributor graph lags the push by a few hours, so Claude will
   still show for a while after the history is clean. Once they are happy, the
   backup can go: `git for-each-ref --format='%(refname)' refs/original | xargs -n1 git update-ref -d`.

5. Offer `--guard --apply` when the guard line says none. It installs a `pre-push`
   hook that refuses any push whose commits still carry a trailer (from any of the
   known agents unless `--agents` narrows it). If a pre-push hook already exists that
   is not ours, the tool refuses; `--guard` prints the hook text so you can merge it
   in by hand. `git push --no-verify` bypasses it once, which is fine to mention.

6. The settings change writes `attribution: {commit: "", pr: ""}` to
   `~/.claude/settings.json` and removes the older `includeCoAuthoredBy` key. It
   takes effect for **new** sessions; in the current one, just leave the trailer off
   when you write commit messages, whatever the harness reminder says.

## Related, not overlapping

`git log --grep` finds the commits; this adds the pushed/local split, the settings
precedence, the rewrite with a backup and the hook. `git filter-repo` is the better
engine for a huge repo, but it needs a pip install and strips the remotes on purpose;
`filter-branch` ships with git and keeps them, which is the right trade for a
handful of commits.

## What this cannot do

It does not push, and it does not edit PR bodies - both are outward-facing and stay
with the user. It cannot turn the setting off for a managed (enterprise) policy file
or for a project file it does not own; it tells you which file to edit. It finds the
agents it knows (`--agents` lists them); a trailer from an unfamiliar tool needs the
name added to `AGENTS`. And it does not make GitHub recompute the contributor graph
faster; only time does that.
