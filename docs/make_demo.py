"""Render docs/demo.png: real attribution output on a fixture repo, styled as a terminal.

Run from the repo root:  python docs/make_demo.py
Needs Pillow (dev-only; the tool itself has no dependencies).
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "git-attribution" / "scripts"))
import attribution  # noqa: E402

FONT = next(p for p in [Path("C:/Windows/Fonts/CascadiaMono.ttf"),
                        Path("C:/Windows/Fonts/consola.ttf"),
                        Path("/System/Library/Fonts/Menlo.ttc"),
                        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")] if p.exists())

BG, FG, DIM = (24, 26, 32), (220, 223, 228), (120, 126, 138)
GREEN, YELLOW, RED, BLUE, PURPLE = (126, 204, 140), (230, 190, 90), (240, 110, 110), (110, 170, 240), (190, 140, 240)


def git(repo: Path, *args: str, stdin: str | None = None) -> None:
    subprocess.run(["git", "-C", str(repo), *args], input=stdin, encoding="utf-8",
                   capture_output=True, check=True,
                   env=dict(os.environ, GIT_AUTHOR_DATE="2026-08-14T10:00:00", GIT_COMMITTER_DATE="2026-08-14T10:00:00"))


def commit(repo: Path, n: int, message: str) -> None:
    (repo / f"src/{n}.py").parent.mkdir(exist_ok=True)
    (repo / f"src/{n}.py").write_text(f"# {n}\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-F", "-", stdin=message)


def fixture(tmp: Path) -> Path:
    remote = tmp / "remote.git"
    git(tmp, "init", "-q", "--bare", str(remote))
    repo = tmp / "tidewatch"
    git(tmp, "init", "-q", "-b", "main", str(repo))
    git(repo, "config", "user.name", "Mara Quill")
    git(repo, "config", "user.email", "mara@example.com")
    git(repo, "remote", "add", "origin", str(remote))
    commit(repo, 1, "Initial tide model and CLI\n")
    commit(repo, 2, "Add harmonic constituents table\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n")
    commit(repo, 3, "Fix DST offset in the tide clock\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n")
    git(repo, "push", "-q", "origin", "main")
    commit(repo, 4, "Docs: getting started\n\n\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>\n")
    commit(repo, 5, "Wire the CI matrix\n\nCo-authored-by: Codex <noreply@openai.com>\n")
    commit(repo, 6, "Release 0.4.0\n")
    home = tmp / "home"
    home.mkdir()
    (home / "settings.json").write_text(json.dumps({"attribution": {"commit": "", "pr": ""}}))
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text(json.dumps({"attribution": {"commit": "Co-Authored-By: Claude <noreply@anthropic.com>"}}))
    return repo, home


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo, home = fixture(Path(tmp))
        buf = io.StringIO()
        with redirect_stdout(buf):
            attribution.main(["--repo", str(repo), "--claude-home", str(home), "--fix"])
        out = (buf.getvalue()
               .replace(str(repo), "~/Code/tidewatch").replace(str(home), "~/.claude")
               .replace("\\", "/").replace("\U0001F916 ", ""))   # tofu in most mono fonts

    lines = ["$ python attribution.py --fix", ""] + out.rstrip().splitlines()
    lines = [l if len(l) <= 108 else l[:107] + "…" for l in lines]
    font = ImageFont.truetype(str(FONT), 15)
    lh = 22
    pad = 28
    width = 1040
    height = pad * 2 + lh * len(lines) + 30
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([pad + i * 22, 14, pad + i * 22 + 12, 26], fill=c)
    d.text((width // 2 - 60, 12), "git-attribution", fill=DIM, font=font)

    y = pad + 20
    for line in lines:
        color = FG
        if line.startswith("$ "):
            color = GREEN
        elif line.startswith(("host", "claude", "template", "setting", "commits", "guard", "plan", "prs")):
            color = BLUE
        elif re.match(r"\s{2}[0-9a-f]{7}\s.*\spushed\s", line):
            color = RED
        elif re.match(r"\s{2}[0-9a-f]{7}\s.*\slocal\s", line):
            color = YELLOW
        elif re.match(r"\s{2}(history|after|verify|settings|template)\s", line):
            color = PURPLE
        elif line.strip().startswith(("NOTE", "rewrites", "originals", "anyone")):
            color = DIM
        d.text((pad, y), line, fill=color, font=font)
        y += lh
    outp = ROOT / "docs" / "demo.png"
    img.save(outp, optimize=True)
    print(f"wrote {outp} ({width}x{height})")


if __name__ == "__main__":
    main()
