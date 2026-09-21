# Changelog

## 1.1.0 - 2026-09-21

- Host awareness: the report's new `host` line names the agent it ran under (from
  `CLAUDECODE`, `CODEX_SANDBOX`, `CURSOR_AGENT`, `GEMINI_CLI`) and where that agent's
  attribution switch lives. Codex's is a ChatGPT workspace policy fetched at runtime,
  so there is nothing on disk to flip and the guard is the local control; Cursor,
  Gemini and Copilot have no documented switch. Claude Code's settings lines are now
  labelled `claude` and printed under every host.
- JSON gains `host` and `host_note`.
- SKILL.md rewritten for any host, with spec `license`, `compatibility` and `metadata`
  frontmatter; `agents/openai.yaml` added for Codex / ChatGPT UI metadata; README
  install matrix for Codex, Cursor, Gemini CLI, Copilot and OpenCode.
- Demo fixture gains a Codex-signed commit. 4 new tests (40 total).

## 1.0.0 - 2026-09-19

Initial release.

- `attribution.py`: reports whether Claude Code is still adding the `Co-Authored-By`
  trailer and PR footer (user / project / local settings precedence, plus the older
  `includeCoAuthoredBy` switch and `commit.template`), and lists every commit on any
  branch or tag that carries AI attribution - trailer, "Generated with" footer, or an
  agent as author - split into pushed and local-only. Knows Claude, Copilot, Codex /
  ChatGPT, Cursor, Gemini / Jules, Devin and Aider; `--agents` narrows it.
- `--prs`: the same scan over pull request bodies through `gh`.
- `--fix` / `--fix --apply`: switch the setting off in `~/.claude/settings.json` and
  rewrite the tainted commits with `git filter-branch --msg-filter`. Dry run by
  default, refuses a dirty tree, keeps `refs/original/*`, never pushes.
- `--guard` / `--guard --apply`: a `pre-push` hook that refuses to push commits
  that still carry attribution. Respects `core.hooksPath`; will not overwrite a hook
  it did not write.
- `--strict` and `--no-settings` for CI; `--json` for tooling.
- 36-test suite (throwaway repos and a throwaway `--claude-home`; the guard test
  pushes to a bare remote through git's real hook runner) and a CI matrix
  (Windows / macOS / Linux, Python 3.10 / 3.13) that also checks this repo's own
  history in strict mode.
- `SKILL.md`: when to run which mode, what to confirm before a rewrite, and what to
  tell the user about force-pushing and GitHub's contributor-graph lag.
