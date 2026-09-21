#!/usr/bin/env python3
"""git-attribution: find and remove AI co-author attribution from a repo's history.

Claude Code, Codex, Copilot, Cursor and the rest append a `Co-Authored-By:` trailer to
commit messages. GitHub reads the trailer and puts the agent in your contributor
graph. This tells you whether the trailer is still being added on this machine,
lists every commit that already carries one, and rewrites them on request.

    python attribution.py                    report: settings + tainted commits
    python attribution.py --repo PATH        another repo (default: cwd)
    python attribution.py --prs              also scan PR bodies through gh
    python attribution.py --fix              plan: switch the setting off, rewrite history
    python attribution.py --fix --apply      do it (backs up refs first; never pushes)
    python attribution.py --guard            show the pre-push hook
    python attribution.py --guard --apply    install it
    python attribution.py --agents claude    only look for one agent (default: all)
    python attribution.py --strict           exit 1 if any tainted commit is found
    python attribution.py --json             everything, machine-readable

Stdlib only. Read-only unless you pass --apply.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

# Names that identify an agent when they appear in a Co-Authored-By trailer, a
# "Generated with" footer, or the author / committer of a commit.
AGENTS = {
    "claude":  r"claude|anthropic",
    "copilot": r"copilot",
    "codex":   r"codex|chatgpt|openai",
    "cursor":  r"cursor",
    "gemini":  r"gemini|google-labs-jules|\bjules\b",
    "devin":   r"\bdevin\b|cognition",
    "aider":   r"\baider\b",
}
# Where each host's attribution switch lives, if anywhere. Claude Code: a settings key
# this script reads and can flip. Codex: a ChatGPT workspace policy fetched at runtime
# (codex-rs/ext/git-attribution), nothing on disk. Others: no documented switch. The
# pre-push guard is the local control that covers every one of them.
HOSTS = {
    "claude":  {"env": ["CLAUDECODE"], "switch": "settings.json attribution.commit / attribution.pr (read below)"},
    "codex":   {"env": ["CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED"],
                "switch": "a ChatGPT workspace policy fetched at runtime - nothing local to flip; the guard is the control"},
    "cursor":  {"env": ["CURSOR_AGENT"], "switch": "no documented local switch; the guard is the control"},
    "gemini":  {"env": ["GEMINI_CLI"], "switch": "no documented local switch; the guard is the control"},
}
TRAILER = re.compile(r"^\s*co-authored-by:\s*(?P<who>.+?)\s*$", re.I)
FOOTER = re.compile(r"^\s*(?:\U0001F916\s*)?(?:generated|made|created|written)\s+with\b.*$", re.I)
HOOK_MARK = "# git-attribution guard"


def agent_re(agents: list[str]) -> re.Pattern:
    return re.compile("|".join(f"(?:{AGENTS[a]})" for a in agents), re.I)


def detect_host() -> tuple[str | None, str | None]:
    """(host key, the env var that gave it away) or (None, None); best effort."""
    for key, spec in HOSTS.items():
        for var in spec["env"]:
            if os.environ.get(var):
                return key, var
    return None, None


# --------------------------------------------------------------------------- model

@dataclass
class Commit:
    sha: str
    short: str
    date: str
    subject: str
    hits: list[str] = field(default_factory=list)   # e.g. "trailer: Claude Opus 4.6"
    pushed: bool = False


@dataclass
class Report:
    repo: str
    branch: str = ""
    identity: str = ""
    host: str = ""                                   # agent this ran under, when detectable
    host_note: str = ""                              # where that host's switch lives
    settings: dict = field(default_factory=dict)     # commit/pr -> {on, source}
    template: str | None = None                      # commit.template that adds a trailer
    scanned: int = 0
    refs: int = 0
    commits: list[Commit] = field(default_factory=list)
    prs: list[dict] = field(default_factory=list)
    prs_note: str = ""
    guard: str = ""                                  # installed | other hook | none
    plan: list[str] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- git

def git(repo: Path, *args: str, check: bool = True, env: dict | None = None) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       encoding="utf-8", errors="surrogateescape", env=env)
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip() or p.returncode}")
    return p.stdout


def repo_root(start: Path) -> Path | None:
    try:
        return Path(git(start, "rev-parse", "--show-toplevel").strip())
    except (RuntimeError, FileNotFoundError):
        return None


# --------------------------------------------------------------------------- matching

def attribution_hit(line: str, rx: re.Pattern) -> str | None:
    """Why this message line is attribution, or None."""
    m = TRAILER.match(line)
    if m and rx.search(m.group("who")):
        return f"trailer: {m.group('who')}"
    if FOOTER.match(line) and rx.search(line):
        return f"footer: {line.strip()}"
    return None


def clean_message(msg: str, rx: re.Pattern) -> str:
    """Drop attribution lines; squash the blank lines they leave behind."""
    out: list[str] = []
    for line in msg.splitlines():
        if attribution_hit(line, rx):
            continue
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out) + "\n"


def scan_commits(repo: Path, rx: re.Pattern) -> tuple[list[Commit], int]:
    fmt = "%H%x1f%h%x1f%as%x1f%an <%ae>%x1f%cn <%ce>%x1f%s%x1f%B%x1e"
    raw = git(repo, "log", "--branches", "--tags", f"--format={fmt}", check=False)
    pushed = set(git(repo, "rev-list", "--remotes", check=False).split())
    found: list[Commit] = []
    n = 0
    for rec in raw.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        n += 1
        sha, short, date, author, committer, subject, body = rec.split("\x1f", 6)
        hits = [h for h in (attribution_hit(l, rx) for l in body.splitlines()) if h]
        if rx.search(author):
            hits.append(f"author: {author}")
        if committer != author and rx.search(committer):
            hits.append(f"committer: {committer}")
        if hits:
            found.append(Commit(sha, short, date, subject, hits, sha in pushed))
    return found, n


# --------------------------------------------------------------------------- settings

def load_json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def settings_files(repo: Path, claude_home: Path) -> list[Path]:
    """Highest precedence first, the order Claude Code merges them."""
    return [repo / ".claude" / "settings.local.json",
            repo / ".claude" / "settings.json",
            claude_home / "settings.json"]


def attribution_state(files: list[Path]) -> dict:
    state: dict[str, dict | None] = {"commit": None, "pr": None}
    for f in files:
        data = load_json(f)
        if not data:
            continue
        attr = data.get("attribution")
        if isinstance(attr, dict):
            for k in state:
                if state[k] is None and k in attr:
                    on = bool(str(attr[k]).strip())
                    state[k] = {"on": on, "source": f"{f}: attribution.{k} = {json.dumps(attr[k])}"}
        if "includeCoAuthoredBy" in data:              # the older single switch
            on = bool(data["includeCoAuthoredBy"])
            for k in state:
                if state[k] is None:
                    state[k] = {"on": on, "source": f"{f}: includeCoAuthoredBy = {json.dumps(on)}"}
    for k in state:
        if state[k] is None:
            state[k] = {"on": True, "source": "default - nothing sets it"}
    return state


def commit_template(repo: Path, rx: re.Pattern) -> str | None:
    path = git(repo, "config", "--get", "commit.template", check=False).strip()
    if not path:
        return None
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = repo / p
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return str(p) if any(attribution_hit(l, rx) for l in text.splitlines()) else None


# --------------------------------------------------------------------------- prs

def scan_prs(repo: Path, rx: re.Pattern) -> tuple[list[dict], str]:
    if not shutil.which("gh"):
        return [], "gh not on PATH - PR bodies not scanned"
    p = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "500",
                        "--json", "number,title,body,url"],
                       cwd=repo, capture_output=True, encoding="utf-8", errors="replace")
    if p.returncode:
        return [], f"gh pr list failed - {p.stderr.strip().splitlines()[-1] if p.stderr.strip() else 'no GitHub remote?'}"
    try:
        prs = json.loads(p.stdout or "[]")
    except ValueError:
        return [], "gh returned something that is not JSON"
    hits = []
    for pr in prs:
        lines = (pr.get("body") or "").splitlines()
        why = [h for h in (attribution_hit(l, rx) for l in lines) if h]
        if why:
            hits.append({"number": pr["number"], "title": pr["title"], "url": pr["url"], "hits": why})
    return hits, f"{len(prs)} PRs scanned"


# --------------------------------------------------------------------------- guard

def hook_path(repo: Path) -> Path:
    p = Path(git(repo, "rev-parse", "--git-path", "hooks").strip())
    return p if p.is_absolute() else repo / p


def hook_text(agents: list[str]) -> str:
    names = "|".join(AGENTS[a] for a in agents)
    return f"""#!/bin/sh
{HOOK_MARK} - refuses to push commits that still carry AI co-author attribution.
# Installed by attribution.py --guard --apply. Delete this file to remove it.
z40=0000000000000000000000000000000000000000
pattern='co-authored-by:.*({names})|(generated|made|created|written) with.*({names})'
status=0
while read -r local_ref local_sha remote_ref remote_sha; do
  [ "$local_sha" = "$z40" ] && continue
  if [ "$remote_sha" = "$z40" ]; then set -- "$local_sha" --not --remotes; else set -- "$remote_sha..$local_sha"; fi
  hits=$(git log -i -E --grep="$pattern" --format='  %h %s' "$@" 2>/dev/null)
  if [ -n "$hits" ]; then
    echo "git-attribution: refusing to push $local_ref - these commits carry AI attribution:" >&2
    echo "$hits" >&2
    status=1
  fi
done
if [ $status -ne 0 ]; then
  echo "  clean them: python attribution.py --fix --apply   (or override once with: git push --no-verify)" >&2
fi
exit $status
"""


def guard_state(repo: Path) -> str:
    hp = hook_path(repo) / "pre-push"
    if not hp.exists():
        return "none"
    try:
        return "installed" if HOOK_MARK in hp.read_text(encoding="utf-8", errors="replace") else "other hook"
    except OSError:
        return "other hook"


def install_guard(repo: Path, agents: list[str]) -> str:
    hp = hook_path(repo) / "pre-push"
    state = guard_state(repo)
    if state == "other hook":
        raise RuntimeError(f"{hp} exists and is not ours - add the check to it by hand (--guard prints it)")
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(hook_text(agents), encoding="utf-8", newline="\n")
    if os.name != "nt":
        hp.chmod(0o755)
    return f"{'updated' if state == 'installed' else 'installed'} {hp}"


# --------------------------------------------------------------------------- fix

def plan_fix(rep: Report, repo: Path, claude_home: Path, agents: list[str],
             settings_only: bool, history_only: bool) -> list[str]:
    plan: list[str] = []
    if not history_only and (rep.settings["commit"]["on"] or rep.settings["pr"]["on"]):
        plan.append(f"settings  write attribution.commit = \"\" and attribution.pr = \"\" to "
                    f"{claude_home / 'settings.json'} (user scope; new sessions stop adding the trailer)")
        for k in ("commit", "pr"):
            src = rep.settings[k]["source"]
            if rep.settings[k]["on"] and ".claude" in src and str(claude_home) not in src:
                plan.append(f"          NOTE {k}: a project file overrides the user file - {src}")
    if not settings_only and rep.commits:
        pushed = sum(c.pushed for c in rep.commits)
        plan.append(f"history   git filter-branch --msg-filter (this script's --msg-filter) -- --branches --tags")
        plan.append(f"          rewrites {len(rep.commits)} commit{'s' if len(rep.commits) != 1 else ''} "
                    f"({pushed} already pushed); every descendant gets a new sha")
        plan.append("          originals kept at refs/original/* (a previous refs/original is replaced)")
        if pushed:
            plan.append("after     git push --force-with-lease --all && git push --force-with-lease --tags")
            plan.append("          anyone else with a clone must re-clone or rebase; GitHub's contributor graph"
                        " refreshes within hours, not instantly")
        plan.append("verify    rerun this report, then: git for-each-ref --format='%(refname)' refs/original | "
                    "xargs -n1 git update-ref -d   (drops the backup)")
    if rep.template and not settings_only:
        plan.append(f"template  {rep.template} adds a trailer to every commit - edit it by hand")
    return plan


def apply_settings(claude_home: Path) -> str:
    p = claude_home / "settings.json"
    data = load_json(p)
    data["attribution"] = {"commit": "", "pr": ""}
    data.pop("includeCoAuthoredBy", None)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return f"settings  attribution switched off in {p}"


def apply_history(repo: Path, agents: list[str]) -> str:
    if git(repo, "status", "--porcelain", "--untracked-files=no").strip():
        raise RuntimeError("working tree is not clean - commit or stash first (filter-branch insists)")
    py = Path(sys.executable).as_posix()
    me = Path(__file__).resolve().as_posix()
    flt = f'"{py}" "{me}" --msg-filter --agents {",".join(agents)}'
    env = dict(os.environ, FILTER_BRANCH_SQUELCH_WARNING="1")
    p = subprocess.run(["git", "-C", str(repo), "filter-branch", "-f", "--msg-filter", flt,
                        "--", "--branches", "--tags"],
                       capture_output=True, encoding="utf-8", errors="replace", env=env)
    if p.returncode:
        raise RuntimeError(f"filter-branch failed: {(p.stderr or p.stdout).strip()[-800:]}")
    return "history   rewritten; originals at refs/original/*"


def msg_filter(agents: list[str]) -> int:
    """filter-branch calls us once per commit with the message on stdin."""
    raw = sys.stdin.buffer.read().decode("utf-8", errors="surrogateescape")
    sys.stdout.buffer.write(clean_message(raw, agent_re(agents)).encode("utf-8", errors="surrogateescape"))
    return 0


# --------------------------------------------------------------------------- report

def render(rep: Report, a) -> None:
    print(f"git-attribution  {rep.repo}")
    if rep.branch or rep.identity:
        print(f"                 {rep.branch}  {rep.identity}".rstrip())
    print()
    if rep.host:
        print(f"host      {rep.host}  {rep.host_note}")
    for k, label in (("commit", "commit trailer"), ("pr", "PR footer")):
        s = rep.settings.get(k)
        if s:
            print(f"claude    {label:15} {'ON ' if s['on'] else 'OFF'}  {s['source']}")
    if rep.template:
        print(f"template  commit.template  ON   {rep.template} contains a trailer")
    if rep.settings or rep.template or rep.host:
        print()
    n = len(rep.commits)
    pushed = sum(c.pushed for c in rep.commits)
    print(f"commits   {rep.scanned} scanned on {rep.refs} refs  ->  "
          f"{n} with AI attribution" + (f", {pushed} already pushed" if n else ""))
    for c in rep.commits[: None if a.full else 25]:
        why = "; ".join(c.hits)
        if not a.full and len(why) > 60:
            why = why[:57] + "..."
        print(f"  {c.short}  {c.date}  {'pushed' if c.pushed else 'local '}  {c.subject[:48]:48}  {why}")
    if n > 25 and not a.full:
        print(f"  ... {n - 25} more (--full)")
    if a.prs:
        print()
        print(f"prs       {rep.prs_note}  ->  {len(rep.prs)} with AI attribution")
        for pr in rep.prs:
            print(f"  #{pr['number']:<5} {pr['title'][:60]:60}  {pr['url']}")
    print()
    g = {"installed": "pre-push hook installed", "other hook": "a pre-push hook exists that is not ours",
         "none": "no pre-push hook"}[rep.guard]
    print(f"guard     {g}")
    if rep.plan:
        print()
        print("plan" if not rep.applied else "plan (applied)")
        for line in rep.plan:
            print("  " + line)
    if rep.applied:
        print()
        for line in rep.applied:
            print("  done  " + line)
    for e in rep.errors:
        print(f"\nerror     {e}")
    if not rep.plan and not rep.applied:
        hints = []
        if n:
            hints.append("--fix to plan a rewrite")
        if rep.settings.get("commit", {}).get("on"):
            hints.append("--fix to switch Claude Code's trailer off")
        if rep.guard == "none":
            hints.append("--guard --apply to block future pushes")
        if hints:
            print("\nnext      " + "; ".join(hints))


# --------------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.getcwd(), help="repository to inspect (default: cwd)")
    ap.add_argument("--agents", default=",".join(AGENTS), help=f"comma-separated subset of: {', '.join(AGENTS)}")
    ap.add_argument("--prs", action="store_true", help="also scan pull request bodies through gh")
    ap.add_argument("--fix", action="store_true", help="plan: settings off + history rewrite")
    ap.add_argument("--guard", action="store_true", help="show the pre-push hook")
    ap.add_argument("--apply", action="store_true", help="with --fix / --guard: do it")
    ap.add_argument("--settings-only", action="store_true", help="with --fix: only the settings change")
    ap.add_argument("--history-only", action="store_true", help="with --fix: only the history rewrite")
    ap.add_argument("--no-settings", action="store_true", help="skip the settings check (CI)")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any tainted commit or PR is found")
    ap.add_argument("--full", action="store_true", help="do not truncate the commit list")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--claude-home", default=str(Path.home() / ".claude"), help=argparse.SUPPRESS)
    ap.add_argument("--msg-filter", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if not a.msg_filter and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # cp1252 consoles vs the robot emoji

    agents = [s.strip().lower() for s in a.agents.split(",") if s.strip()]
    bad = [s for s in agents if s not in AGENTS]
    if bad:
        print(f"unknown agent(s): {', '.join(bad)}; known: {', '.join(AGENTS)}", file=sys.stderr)
        return 2
    if a.msg_filter:
        return msg_filter(agents)
    rx = agent_re(agents)
    claude_home = Path(a.claude_home)

    if a.guard and not a.apply:
        print(hook_text(agents), end="")
        return 0

    root = repo_root(Path(a.repo))
    if root is None:
        print(f"not a git repository: {a.repo}", file=sys.stderr)
        return 2
    rep = Report(repo=str(root))
    rep.branch = git(root, "branch", "--show-current", check=False).strip() or "(detached)"
    name = git(root, "config", "--get", "user.name", check=False).strip()
    mail = git(root, "config", "--get", "user.email", check=False).strip()
    rep.identity = f"{name} <{mail}>" if name or mail else "(no user.name / user.email)"
    host, var = detect_host()
    if host:
        rep.host = host
        rep.host_note = f"({var} set) attribution switch: {HOSTS[host]['switch']}"
    if not a.no_settings:
        rep.settings = attribution_state(settings_files(root, claude_home))
        rep.template = commit_template(root, rx)
    rep.commits, rep.scanned = scan_commits(root, rx)
    rep.refs = len(git(root, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/tags", check=False).split())
    if a.prs:
        rep.prs, rep.prs_note = scan_prs(root, rx)
    rep.guard = guard_state(root)

    if a.guard and a.apply:
        try:
            rep.applied.append("guard     " + install_guard(root, agents))
            rep.guard = guard_state(root)
        except RuntimeError as e:
            rep.errors.append(str(e))

    if a.fix:
        rep.plan = plan_fix(rep, root, claude_home, agents, a.settings_only, a.history_only)
        if not rep.plan:
            rep.plan = ["nothing to do"]
        elif a.apply:
            try:
                if not a.history_only and (rep.settings.get("commit", {}).get("on") or rep.settings.get("pr", {}).get("on")):
                    rep.applied.append(apply_settings(claude_home))
                    rep.settings = attribution_state(settings_files(root, claude_home))
                if not a.settings_only and rep.commits:
                    rep.applied.append(apply_history(root, agents))
                    rep.commits, rep.scanned = scan_commits(root, rx)
                    rep.applied.append(f"verify    {len(rep.commits)} tainted commit(s) remain")
            except RuntimeError as e:
                rep.errors.append(str(e))

    if a.json:
        print(json.dumps(asdict(rep), indent=2))
    else:
        render(rep, a)
    if rep.errors:
        return 1
    if a.strict and (rep.commits or rep.prs):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
