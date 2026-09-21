"""Tests for host awareness in attribution.py: which agent the report ran under and
where that agent's attribution switch lives (or that there is none).

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from test_attribution import Base  # noqa: E402
import attribution  # noqa: E402

KEEP = ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "PATH", "SYSTEMROOT", "TEMP", "TMP", "COMSPEC",
        "GIT_EXEC_PATH", "GIT_CONFIG_NOSYSTEM")


def env_only(extra: dict) -> dict:
    return {**{k: v for k, v in os.environ.items() if k in KEEP}, **extra}


class Hosts(Base):
    def test_codex_trailer_and_footer_are_detected(self):
        self.commit("Wire CI\n\nCo-authored-by: Codex <noreply@openai.com>\n")
        self.commit("Docs\n\nGenerated with [Codex](https://openai.com/codex/).\n")
        code, rep = self.run_json("--agents", "codex")
        self.assertEqual(len(rep["commits"]), 2)
        kinds = {c["hits"][0].split(":")[0] for c in rep["commits"]}
        self.assertEqual(kinds, {"trailer", "footer"})

    def test_host_line_names_where_the_switch_lives(self):
        self.commit("x\n")
        with mock.patch.dict(os.environ, env_only({"CODEX_SANDBOX": "seatbelt"}), clear=True):
            code, out = self.run_main()
            self.assertEqual(attribution.detect_host(), ("codex", "CODEX_SANDBOX"))
        self.assertIn("host      codex  (CODEX_SANDBOX set)", out)
        self.assertIn("workspace policy", out)
        self.assertIn("claude    commit trailer", out)          # Claude's setting is still reported
        with mock.patch.dict(os.environ, env_only({"CLAUDECODE": "1"}), clear=True):
            code, out = self.run_main()
        self.assertIn("host      claude  (CLAUDECODE set)", out)
        self.assertIn("attribution.commit", out)

    def test_no_host_marker_omits_the_line(self):
        self.commit("x\n")
        with mock.patch.dict(os.environ, env_only({}), clear=True):
            self.assertEqual(attribution.detect_host(), (None, None))
            code, rep = self.run_json()
        self.assertEqual(rep["host"], "")
        self.assertEqual(rep["host_note"], "")

    def test_guard_blocks_codex_trailer_too(self):
        self.commit("ok\n")
        code, out = self.run_main("--guard", "--apply")
        self.assertEqual(code, 0)
        self.commit("bad\n\nCo-authored-by: Codex <noreply@openai.com>\n")
        import subprocess
        p = subprocess.run(["git", "-C", str(self.repo), "push", "-q", "origin", "main"],
                           capture_output=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("refusing to push", p.stderr)


if __name__ == "__main__":
    unittest.main()
