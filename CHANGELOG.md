# Changelog

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
