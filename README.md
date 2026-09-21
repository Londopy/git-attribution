<div align="center">

# 🧹 git-attribution

**Claude, Codex or Copilot showed up in your contributors. Find every commit an agent signed, get it out, and keep it out — from whichever agent you're using.**

[![CI](https://github.com/Londopy/git-attribution/actions/workflows/ci.yml/badge.svg)](https://github.com/Londopy/git-attribution/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)](skills/git-attribution/scripts/attribution.py)
[![Agent Skills](https://img.shields.io/badge/Agent_Skills-spec-111)](https://agentskills.io)
[![Works with](https://img.shields.io/badge/works_with-Claude_Code_%7C_Codex_%7C_Cursor_%7C_Gemini_CLI_%7C_Copilot_%7C_OpenCode-D97757)](#install)
[![Platform](https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey)](#install)

<img src="docs/demo.png" alt="git-attribution output: the trailer setting, tainted commits split into pushed and local, the rewrite plan and the guard" width="900">

<sub>Part of the rollcall family — tools that make what your coding agent does silently legible: [skill-rollcall](https://github.com/Londopy/skill-rollcall) · [mcp-rollcall](https://github.com/Londopy/mcp-rollcall) · [settings-effective](https://github.com/Londopy/settings-effective) · **git-attribution** · all four: [agent-skills](https://github.com/Londopy/agent-skills)</sub>

</div>

---

Claude Code appends `Co-Authored-By: Claude <noreply@anthropic.com>` to every commit it writes. Codex appends `Co-authored-by: Codex <noreply@openai.com>` when its ChatGPT workspace policy says so. GitHub reads the trailer and adds the agent to your repo's contributor graph. Nothing tells you it happened — you notice when the avatar shows up. Copilot, Cursor, Gemini, Devin and Aider do the same thing with their own names.

`git-attribution` answers the three questions that follow: **is it still being added?** (which settings file decided that), **where is it already?** (every commit on every branch, split into pushed and local-only), and **how do I get it out?** (a rewrite with a backup, and a pre-push hook so it doesn't come back). It runs as a skill in any Agent Skills host (`/git-attribution` in Claude Code, `$git-attribution` in Codex, or just say "Claude is in my contributors") and as a plain CLI.

## What it does

| Mode | Question it answers |
|---|---|
| default | Which agent am I running under, and where does **its** attribution switch live? Is Claude Code's trailer **still being added** on this machine, and which of `settings.local.json` / `.claude/settings.json` / `~/.claude/settings.json` decided it? Which commits **already carry** attribution, from which agent, and which of those are **pushed**? |
| `--prs` | Same scan over pull request bodies, via `gh`. |
| `--fix` | Show the plan: switch the setting off, rewrite the tainted commits, what to push afterwards. `--fix --apply` does the first two. **It never pushes.** |
| `--guard` | Show a `pre-push` hook that refuses commits carrying attribution. `--guard --apply` installs it. |
| `--agents claude` | Only look for one agent. Default: all seven it knows. |
| `--strict --no-settings` | Is this repo's history clean? Non-zero exit for CI. |

Everything is read-only except `--apply`, which shows you the plan first.

## Install

One layout — `skills/git-attribution/SKILL.md` + `scripts/attribution.py` — is the [Agent Skills](https://agentskills.io) standard, so the same folder works everywhere.

**`skills` CLI** — any of 79 agents (global; `--copy` because symlinks need Developer Mode on Windows):

```bash
npx skills add Londopy/git-attribution -g --copy                  # picks the agents it finds
npx skills add Londopy/git-attribution -g --copy -a codex -a cursor
npx skills add Londopy/git-attribution -g --copy --all            # every agent, no prompts
```

**Claude Code plugin** (in an interactive `claude` session):

```
/plugin marketplace add Londopy/git-attribution
/plugin install git-attribution@git-attribution
```

**By hand** — copy the folder into the host's skills directory:

```bash
git clone https://github.com/Londopy/git-attribution
cp -r git-attribution/skills/git-attribution ~/.claude/skills/          # Claude Code
cp -r git-attribution/skills/git-attribution ~/.agents/skills/          # Codex, Cline, Zed, Warp (universal)
cp -r git-attribution/skills/git-attribution ~/.cursor/skills/          # Cursor
cp -r git-attribution/skills/git-attribution ~/.gemini/skills/          # Gemini CLI
cp -r git-attribution/skills/git-attribution ~/.copilot/skills/         # GitHub Copilot
cp -r git-attribution/skills/git-attribution ~/.config/opencode/skills/ # OpenCode
```

## Usage

### From your agent

Say what you'd naturally say — "is Claude still being added to my commits?", "Codex is in my contributors, get it out", "scrub the AI co-authors from this repo", "make sure that never gets pushed again" — or invoke the skill by name. The agent runs the report, answers your actual question first, and before any rewrite confirms with you that the tree is clean and that you're willing to force-push if any tainted commit is already on the remote.

### As a CLI

Stdlib-only Python, nothing in it depends on any particular agent:

```bash
python ~/.claude/skills/git-attribution/scripts/attribution.py
python ~/.agents/skills/git-attribution/scripts/attribution.py --agents codex   # from a Codex install
python ~/.claude/skills/git-attribution/scripts/attribution.py --fix          # plan
python ~/.claude/skills/git-attribution/scripts/attribution.py --fix --apply  # do it
python ~/.claude/skills/git-attribution/scripts/attribution.py --guard --apply
```

| Flag | Effect |
|---|---|
| `--repo DIR` | Repository to inspect (default: cwd) |
| `--agents a,b` | Subset of `claude, copilot, codex, cursor, gemini, devin, aider` |
| `--prs` | Also scan PR bodies through `gh` (skipped if `gh` is missing) |
| `--fix` / `--fix --apply` | Plan / perform the settings change and the history rewrite |
| `--settings-only` / `--history-only` | Restrict `--fix` to one half |
| `--guard` / `--guard --apply` | Print / install the pre-push hook |
| `--strict` | Exit 1 if any tainted commit or PR is found |
| `--no-settings` | Skip the settings check (CI, or someone else's machine) |
| `--full` / `--json` | Untruncated commit list / machine-readable |

### Where each agent's switch lives

| Host (detected from the environment) | Attribution switch |
|---|---|
| Claude Code (`CLAUDECODE`) | `attribution.commit` / `attribution.pr` in `settings.json`, older `includeCoAuthoredBy`. Read with the file that decided it; `--fix` writes it off. |
| Codex (`CODEX_SANDBOX`) | A ChatGPT workspace policy fetched at runtime ([`codex-rs/ext/git-attribution`](https://github.com/openai/codex/tree/main/codex-rs/ext/git-attribution)) — nothing on disk. The pre-push guard is the local control. |
| Cursor (`CURSOR_AGENT`), Gemini CLI (`GEMINI_CLI`), Copilot | No documented local switch. The guard is the local control. |

The Claude Code lines are printed under every host — a machine usually runs more than one agent — and the scan, rewrite and guard cover every agent in `--agents` regardless.

## What the rewrite does

`--fix --apply` runs `git filter-branch --msg-filter` over every branch and tag, with this script as the filter. Each message loses only its attribution lines (a `Co-Authored-By:` naming a known agent, a "Generated with …" footer, plus the blank line it leaves behind). Everything else in the message is untouched; a human co-author trailer stays.

- Commits older than the first tainted one keep their SHA. Everything after gets a new one — that's what a rewrite is.
- The originals are kept at `refs/original/*`. Your remotes are left alone (`git filter-repo` deletes them by design; that's why this uses `filter-branch`).
- It refuses to run on a dirty working tree.
- It does not push. If any rewritten commit was already on the remote, the plan prints `git push --force-with-lease --all && git push --force-with-lease --tags` for you to run, and reminds you that anyone else's clone needs a re-clone or rebase.
- GitHub rebuilds the contributor graph on its own schedule, usually within a few hours of the push. Claude will still show until then.

## The guard

`--guard --apply` writes `.git/hooks/pre-push` (or wherever `core.hooksPath` points). On every push it runs `git log --grep` over the commits about to go out and refuses the push if any of them still carry attribution, listing them. `git push --no-verify` overrides it once. It won't overwrite a pre-push hook it didn't write; `--guard` prints the text so you can merge it into yours.

This is a git hook, so it catches pushes from Claude Code, from your terminal, and from your IDE alike.

## What it catches

| Finding | Where | Why it matters |
|---|---|---|
| `attribution.commit` / `.pr` non-empty, or unset | settings precedence chain | New commits will keep getting the trailer. A project file silently overrides a user-level "off". |
| `includeCoAuthoredBy` | same | The older switch; still honoured, and removed when `--fix` writes the new key. |
| `commit.template` containing a trailer | git config | Every commit gets it, regardless of Claude. |
| `Co-Authored-By: <agent>` | commit message | The line GitHub turns into a contributor. |
| `Generated with …`, `Made with …` naming an agent | commit message / PR body | The PR footer; also ends up in squash-merge commit messages. |
| Agent as author or committer | commit metadata | Some setups commit *as* the agent. Not fixed by a message rewrite — shown so you know. |

## Related, not overlapping

`git log -i --grep=co-authored-by` finds the commits. This adds the pushed/local split, the settings precedence, the rewrite with a backup, and the hook. [`git filter-repo`](https://github.com/newren/git-filter-repo) is the better engine for a very large repo, but it needs a pip install and strips remotes on purpose; for a handful of commits, `filter-branch` shipping with git and keeping your remotes is the right trade.

## What it cannot do

- **It doesn't push, and it doesn't edit PR bodies.** Both are outward-facing; the plan prints the commands and URLs.
- **It can't override a managed policy file** or a project file you don't own. It tells you which file decided the setting.
- **Only Claude Code has a local switch it can write.** Codex's attribution is workspace policy; Cursor's, Gemini's and Copilot's have no documented toggle. For those the guard is the answer, and it says so.
- **It only knows the agents in `AGENTS`.** A trailer from a tool it hasn't heard of needs a name added to that dict — one line.
- **It can't make GitHub recompute contributors faster.** Only time does that.
