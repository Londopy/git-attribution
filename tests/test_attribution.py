"""Tests for attribution.py. Stdlib only: python -m unittest discover -s tests -v

Every test builds throwaway git repos and a throwaway --claude-home inside a temp
dir, so nothing here can touch a real repository or a real settings.json.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "git-attribution" / "scripts"))
import attribution  # noqa: E402

CLAUDE = "Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
COPILOT = "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
FOOTER = "\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)"
HUMAN = "Co-Authored-By: Alice Example <alice@example.com>"
ALL = attribution.agent_re(list(attribution.AGENTS))


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          encoding="utf-8", errors="replace", check=check)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "claude-home"
        self.home.mkdir()
        self.remote = self.tmp / "remote.git"
        git(self.tmp, "init", "-q", "--bare", str(self.remote))
        self.repo = self.tmp / "work"
        git(self.tmp, "init", "-q", "-b", "main", str(self.repo))
        git(self.repo, "config", "user.name", "Londopy")
        git(self.repo, "config", "user.email", "Londopy@users.noreply.github.com")
        git(self.repo, "config", "core.autocrlf", "false")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        self.n = 0

    def tearDown(self):
        self._tmp.cleanup()

    def commit(self, message: str, **env) -> str:
        self.n += 1
        (self.repo / f"f{self.n}").write_text(str(self.n))
        git(self.repo, "add", ".")
        e = dict(os.environ, **env)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-F", "-"], input=message,
                       encoding="utf-8", env=e, check=True)
        return git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def run_main(self, *args: str, cwd: Path | None = None) -> tuple[int, str]:
        argv = ["--repo", str(cwd or self.repo), "--claude-home", str(self.home), *args]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = attribution.main(argv)
        return code, out.getvalue() + err.getvalue()

    def run_json(self, *args: str) -> tuple[int, dict]:
        code, out = self.run_main("--json", *args)
        return code, json.loads(out)


# --------------------------------------------------------------------------- matching

class MessageCleaning(unittest.TestCase):
    def test_trailer_and_footer_removed_body_kept(self):
        msg = f"add b\n\nSome body text.\n\n{FOOTER}\n\n{CLAUDE}\n"
        self.assertEqual(attribution.clean_message(msg, ALL), "add b\n\nSome body text.\n")

    def test_human_coauthor_kept(self):
        msg = f"pair\n\n{HUMAN}\n{CLAUDE}\n"
        self.assertEqual(attribution.clean_message(msg, ALL), f"pair\n\n{HUMAN}\n")

    def test_clean_message_untouched(self):
        msg = "subject\n\nbody line one\nbody line two\n"
        self.assertEqual(attribution.clean_message(msg, ALL), msg)

    def test_blank_runs_squashed(self):
        msg = f"s\n\n{CLAUDE}\n\n\nmore\n\n\n"
        self.assertEqual(attribution.clean_message(msg, ALL), "s\n\nmore\n")

    def test_hit_variants(self):
        self.assertTrue(attribution.attribution_hit("co-authored-by: claude <x@anthropic.com>", ALL))
        self.assertTrue(attribution.attribution_hit("  Co-Authored-By: Cursor <cursoragent@cursor.com>", ALL))
        self.assertTrue(attribution.attribution_hit("Made with Cursor", ALL))
        self.assertTrue(attribution.attribution_hit(FOOTER, ALL))
        self.assertIsNone(attribution.attribution_hit(HUMAN, ALL))
        self.assertIsNone(attribution.attribution_hit("Generated with love by the team", ALL))
        self.assertIsNone(attribution.attribution_hit("we talked to claude about the design", ALL))

    def test_agent_subset(self):
        only_claude = attribution.agent_re(["claude"])
        self.assertIsNone(attribution.attribution_hit(COPILOT, only_claude))
        self.assertTrue(attribution.attribution_hit(CLAUDE, only_claude))


# --------------------------------------------------------------------------- settings

class Settings(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = Path(self._tmp.name)
        self.local, self.project, self.user = t / "local.json", t / "project.json", t / "user.json"
        self.files = [self.local, self.project, self.user]

    def tearDown(self):
        self._tmp.cleanup()

    def state(self):
        return attribution.attribution_state(self.files)

    def test_default_is_on(self):
        s = self.state()
        self.assertTrue(s["commit"]["on"] and s["pr"]["on"])
        self.assertIn("default", s["commit"]["source"])

    def test_user_off(self):
        self.user.write_text(json.dumps({"attribution": {"commit": "", "pr": ""}}))
        s = self.state()
        self.assertFalse(s["commit"]["on"])
        self.assertIn("user.json", s["commit"]["source"])

    def test_project_overrides_user(self):
        self.user.write_text(json.dumps({"attribution": {"commit": "", "pr": ""}}))
        self.project.write_text(json.dumps({"attribution": {"commit": "Co-Authored-By: Claude"}}))
        s = self.state()
        self.assertTrue(s["commit"]["on"])
        self.assertIn("project.json", s["commit"]["source"])
        self.assertFalse(s["pr"]["on"])                # pr not set in project -> user wins

    def test_local_overrides_project(self):
        self.project.write_text(json.dumps({"attribution": {"commit": "x"}}))
        self.local.write_text(json.dumps({"attribution": {"commit": ""}}))
        self.assertFalse(self.state()["commit"]["on"])

    def test_legacy_switch(self):
        self.user.write_text(json.dumps({"includeCoAuthoredBy": False}))
        s = self.state()
        self.assertFalse(s["commit"]["on"] or s["pr"]["on"])
        self.assertIn("includeCoAuthoredBy", s["commit"]["source"])

    def test_new_key_beats_legacy_in_same_file(self):
        self.user.write_text(json.dumps({"includeCoAuthoredBy": False, "attribution": {"commit": "yes"}}))
        s = self.state()
        self.assertTrue(s["commit"]["on"])
        self.assertFalse(s["pr"]["on"])

    def test_garbage_file_ignored(self):
        self.user.write_text("{not json")
        self.assertTrue(self.state()["commit"]["on"])


# --------------------------------------------------------------------------- scan

class Scan(Base):
    def test_finds_tainted_and_pushed(self):
        first = self.commit("first, clean\n")
        self.commit(f"add b\n\n{CLAUDE}\n")
        git(self.repo, "push", "-q", "origin", "main")
        self.commit(f"add c\n\n{FOOTER}\n\n{COPILOT}\n")
        self.commit("add d, clean\n")
        code, rep = self.run_json()
        self.assertEqual(code, 0)
        self.assertEqual(rep["scanned"], 4)
        self.assertEqual([c["subject"] for c in rep["commits"]], ["add c", "add b"])
        by = {c["subject"]: c for c in rep["commits"]}
        self.assertTrue(by["add b"]["pushed"])
        self.assertFalse(by["add c"]["pushed"])
        self.assertEqual(len(by["add c"]["hits"]), 2)
        self.assertTrue(rep["commits"][0]["hits"][0].startswith("footer:"))

    def test_agent_author(self):
        self.commit("bot commit\n", GIT_AUTHOR_NAME="Claude", GIT_AUTHOR_EMAIL="noreply@anthropic.com")
        _, rep = self.run_json()
        self.assertEqual(len(rep["commits"]), 1)
        self.assertTrue(rep["commits"][0]["hits"][0].startswith("author:"))

    def test_agents_subset_flag(self):
        self.commit(f"copilot only\n\n{COPILOT}\n")
        _, rep = self.run_json("--agents", "claude")
        self.assertEqual(rep["commits"], [])
        _, rep = self.run_json("--agents", "copilot")
        self.assertEqual(len(rep["commits"]), 1)

    def test_unknown_agent(self):
        code, out = self.run_main("--agents", "hal9000")
        self.assertEqual(code, 2)
        self.assertIn("unknown agent", out)

    def test_other_branches_and_tags_scanned(self):
        self.commit("main clean\n")
        git(self.repo, "checkout", "-q", "-b", "feature")
        self.commit(f"feature tainted\n\n{CLAUDE}\n")
        git(self.repo, "tag", "v1")
        git(self.repo, "checkout", "-q", "main")
        _, rep = self.run_json()
        self.assertEqual([c["subject"] for c in rep["commits"]], ["feature tainted"])
        self.assertEqual(rep["refs"], 3)

    def test_strict(self):
        self.commit("clean\n")
        self.assertEqual(self.run_main("--strict")[0], 0)
        self.commit(f"bad\n\n{CLAUDE}\n")
        self.assertEqual(self.run_main("--strict")[0], 1)

    def test_not_a_repo(self):
        code, out = self.run_main(cwd=self.tmp / "nowhere")
        self.assertEqual(code, 2)
        self.assertIn("not a git repository", out)

    def test_report_text(self):
        self.commit(f"add b\n\n{CLAUDE}\n")
        code, out = self.run_main()
        self.assertIn("1 with AI attribution", out)
        self.assertIn("trailer: Claude Opus 4.6", out)
        self.assertIn("commit trailer  ON", out)
        self.assertIn("no pre-push hook", out)
        self.assertIn("--fix", out)

    def test_commit_template_detected(self):
        tpl = self.tmp / "template.txt"
        tpl.write_text(f"\n\n{CLAUDE}\n")
        git(self.repo, "config", "commit.template", str(tpl))
        self.commit("x\n")
        _, rep = self.run_json()
        self.assertEqual(Path(rep["template"]), tpl)

    def test_no_settings_flag(self):
        self.commit("x\n")
        _, rep = self.run_json("--no-settings")
        self.assertEqual(rep["settings"], {})


# --------------------------------------------------------------------------- fix

class Fix(Base):
    def test_plan_only_changes_nothing(self):
        self.commit(f"b\n\n{CLAUDE}\n")
        code, rep = self.run_json("--fix")
        self.assertEqual(code, 0)
        self.assertTrue(any("filter-branch" in l for l in rep["plan"]))
        self.assertTrue(any("settings.json" in l for l in rep["plan"]))
        self.assertEqual(rep["applied"], [])
        self.assertFalse((self.home / "settings.json").exists())
        self.assertEqual(len(self.run_json()[1]["commits"]), 1)

    def test_apply_rewrites_history(self):
        first = self.commit("first, clean\n")
        self.commit(f"add b\n\nSome body text.\n\n{CLAUDE}\n")
        git(self.repo, "push", "-q", "origin", "main")
        self.commit(f"add c\n\n{FOOTER}\n\n{COPILOT}\n")
        last = self.commit("add d, clean\n")
        code, rep = self.run_json("--fix", "--history-only", "--apply")
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["commits"], [])
        self.assertTrue(any("0 tainted" in l for l in rep["applied"]))
        log = git(self.repo, "log", "--format=%B").stdout
        self.assertNotIn("Co-Authored", log)
        self.assertNotIn("Generated with", log)
        self.assertIn("Some body text.", log)
        # untouched ancestor keeps its sha; descendants of a rewrite do not
        self.assertEqual(git(self.repo, "rev-parse", "HEAD~3").stdout.strip(), first)
        self.assertNotEqual(git(self.repo, "rev-parse", "HEAD").stdout.strip(), last)
        self.assertIn("refs/original/refs/heads/main", git(self.repo, "for-each-ref").stdout)
        self.assertIn("origin", git(self.repo, "remote").stdout)
        self.assertTrue(any("force-with-lease" in l for l in rep["plan"]))

    def test_apply_refuses_dirty_tree(self):
        self.commit(f"b\n\n{CLAUDE}\n")
        (self.repo / "f1").write_text("changed")
        code, rep = self.run_json("--fix", "--history-only", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("not clean", rep["errors"][0])
        self.assertEqual(len(rep["commits"]), 1)

    def test_apply_settings(self):
        (self.home / "settings.json").write_text(json.dumps({"keep": 1, "includeCoAuthoredBy": True}))
        self.commit("x\n")
        code, rep = self.run_json("--fix", "--settings-only", "--apply")
        self.assertEqual(code, 0)
        data = json.loads((self.home / "settings.json").read_text())
        self.assertEqual(data["attribution"], {"commit": "", "pr": ""})
        self.assertEqual(data["keep"], 1)
        self.assertNotIn("includeCoAuthoredBy", data)
        self.assertFalse(rep["settings"]["commit"]["on"])

    def test_project_override_is_called_out(self):
        (self.home / "settings.json").write_text(json.dumps({"attribution": {"commit": "", "pr": ""}}))
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text(json.dumps({"attribution": {"commit": "Co-Authored-By: Claude"}}))
        self.commit("x\n")
        _, rep = self.run_json("--fix", "--settings-only")
        self.assertTrue(any("project file overrides" in l for l in rep["plan"]))

    def test_nothing_to_do(self):
        (self.home / "settings.json").write_text(json.dumps({"attribution": {"commit": "", "pr": ""}}))
        self.commit("clean\n")
        _, rep = self.run_json("--fix")
        self.assertEqual(rep["plan"], ["nothing to do"])

    def test_msg_filter_mode(self):
        p = subprocess.run([sys.executable, str(attribution.__file__), "--msg-filter", "--agents", "claude"],
                           input=f"s\n\n{CLAUDE}\n{COPILOT}\n", capture_output=True, encoding="utf-8")
        self.assertEqual(p.stdout, f"s\n\n{COPILOT}\n")


# --------------------------------------------------------------------------- guard

class Guard(Base):
    def hook(self) -> Path:
        return attribution.hook_path(self.repo) / "pre-push"

    def test_show_does_not_install(self):
        self.commit("x\n")
        code, out = self.run_main("--guard")
        self.assertEqual(code, 0)
        self.assertIn("#!/bin/sh", out)
        self.assertIn("claude|anthropic", out)
        self.assertFalse(self.hook().exists())

    def test_install_and_refuse_push(self):
        self.commit("clean\n")
        code, rep = self.run_json("--guard", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(rep["guard"], "installed")
        self.assertTrue(self.hook().exists())
        push = git(self.repo, "push", "origin", "main", check=False)
        self.assertEqual(push.returncode, 0, push.stderr)
        self.commit(f"sneaky\n\n{CLAUDE}\n")
        push = git(self.repo, "push", "origin", "main", check=False)
        self.assertNotEqual(push.returncode, 0)
        self.assertIn("refusing to push", push.stderr)
        self.assertIn("sneaky", push.stderr)
        # cleaned -> allowed
        self.run_json("--fix", "--history-only", "--apply")
        push = git(self.repo, "push", "--force", "origin", "main", check=False)
        self.assertEqual(push.returncode, 0, push.stderr)

    def test_new_branch_push_checked(self):
        self.commit("clean\n")
        self.run_json("--guard", "--apply")
        git(self.repo, "checkout", "-q", "-b", "feature")
        self.commit(f"bad\n\n{CLAUDE}\n")
        push = git(self.repo, "push", "origin", "feature", check=False)
        self.assertNotEqual(push.returncode, 0)
        self.assertIn("refusing to push", push.stderr)

    def test_reinstall_updates_ours(self):
        self.commit("x\n")
        self.run_json("--guard", "--apply")
        _, rep = self.run_json("--guard", "--apply", "--agents", "copilot")
        self.assertTrue(any("updated" in l for l in rep["applied"]))
        self.assertNotIn("anthropic", self.hook().read_text())

    def test_refuses_foreign_hook(self):
        self.commit("x\n")
        self.hook().parent.mkdir(parents=True, exist_ok=True)
        self.hook().write_text("#!/bin/sh\necho mine\n")
        code, rep = self.run_json("--guard", "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(rep["guard"], "other hook")
        self.assertIn("not ours", rep["errors"][0])
        self.assertEqual(self.hook().read_text(), "#!/bin/sh\necho mine\n")

    def test_respects_hooks_path(self):
        self.commit("x\n")
        custom = self.tmp / "hooks"
        git(self.repo, "config", "core.hooksPath", str(custom))
        self.run_json("--guard", "--apply")
        self.assertTrue((custom / "pre-push").exists())


if __name__ == "__main__":
    unittest.main()
