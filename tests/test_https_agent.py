"""HTTPS Pull Agent (VPS sem SSH): testes offline com repositorio Git local.

OURGIT_ALLOW_LOCAL_SOURCE=1 habilita apenas a URL local do fixture.
O software em producao aceita somente fontes HTTPS na porta 443.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

APP = [sys.executable, str(Path(__file__).resolve().parents[1] / "ourgit.py")]


def run(*args, cwd=None, env=None, check=True):
    result = subprocess.run([str(x) for x in args], cwd=cwd, env=env,
                            capture_output=True, text=True, timeout=90)
    if check and result.returncode:
        raise AssertionError(f"{args}\nout={result.stdout}\nerr={result.stderr}")
    return result


@unittest.skipUnless(sys.platform == "linux", "O HTTPS Pull Agent executa em VPS Linux")
class HTTPSAgentTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.source = self.root / "source"
        self.remote = self.root / "origin.git"
        self.work = self.root / "checkout"
        run("git", "init", "-b", "hml", self.source)
        run("git", "init", "--bare", "-b", "hml", self.remote)
        run("git", "config", "user.email", "test@example.invalid", cwd=self.source)
        run("git", "config", "user.name", "OurGit Unit Test", cwd=self.source)
        (self.source / "app.txt").write_text("v1\n")
        run("git", "add", "app.txt", cwd=self.source)
        run("git", "commit", "-m", "app v1", cwd=self.source)
        run("git", "remote", "add", "origin", self.remote, cwd=self.source)
        run("git", "push", "-u", "origin", "hml", cwd=self.source)
        self.env = dict(os.environ,
                        OURGIT_ALLOW_LOCAL_SOURCE="1",
                        XDG_CONFIG_HOME=str(self.root / "config"))
        self.agent("init", "--name", "app-hml", "--url", self.remote,
                   "--branch", "hml", "--worktree", self.work)

    def agent(self, *args, check=True):
        return run(*APP, "agent", *args, cwd=self.root, env=self.env, check=check)

    def update_remote(self, data):
        (self.source / "app.txt").write_text(data)
        run("git", "commit", "-am", "new data", cwd=self.source)
        run("git", "push", "origin", "hml", cwd=self.source)

    def test_dry_run_never_clones(self):
        result = self.agent("check", "--name", "app-hml")
        self.assertIn("Somente consulta", result.stdout)
        self.assertFalse(self.work.exists())

    def test_checkout_and_action_only_after_explicit_enable(self):
        self.agent("check", "--name", "app-hml", "--apply")
        self.assertEqual((self.work / "app.txt").read_text(), "v1\n")
        self.assertIn("desabilitada", self.agent("status", "--name", "app-hml").stdout.lower())
        self.update_remote("v2\n")
        self.agent("check", "--name", "app-hml", "--apply")
        self.assertEqual((self.work / "app.txt").read_text(), "v2\n")
        script = self.root / "action.sh"
        script.write_text('#!/bin/sh\nprintf "%s" "$OURGIT_SHA" >> "$OURGIT_WORKTREE/../runs.txt"\nprintf "\\n" >> "$OURGIT_WORKTREE/../runs.txt"\n')
        self.agent("action", "set", "--name", "app-hml", "--script", script)
        self.agent("check", "--name", "app-hml", "--apply")
        self.assertEqual(len((self.root / "runs.txt").read_text().splitlines()), 1)
        self.agent("check", "--name", "app-hml", "--apply")
        self.assertEqual(len((self.root / "runs.txt").read_text().splitlines()), 1)
        self.update_remote("v3\n")
        self.agent("check", "--name", "app-hml", "--apply")
        self.assertEqual((self.work / "app.txt").read_text(), "v3\n")
        self.assertEqual(len((self.root / "runs.txt").read_text().splitlines()), 2)
        self.assertIn("Deploy CONCLUIDO", self.agent("log", "--name", "app-hml").stdout)

    def test_dirty_worktree_refused(self):
        self.agent("check", "--name", "app-hml", "--apply")
        (self.work / "untracked-secret.txt").write_text("nao apague")
        self.update_remote("novo\n")
        failed = self.agent("check", "--name", "app-hml", "--apply", check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("nao commitada", failed.stderr)
        self.assertEqual((self.work / "untracked-secret.txt").read_text(), "nao apague")
        self.assertEqual((self.work / "app.txt").read_text(), "v1\n")

    def test_action_script_inside_worktree_refused(self):
        self.agent("check", "--name", "app-hml", "--apply")
        script = self.work / "deploy.sh"
        script.write_text("exit 0\n")
        p = self.agent("action", "set", "--name", "app-hml", "--script", script, check=False)
        self.assertNotEqual(p.returncode, 0)

    def test_agent_rejects_unsafe_sources(self):
        for url in ("http://github.com/owner/repo.git",
                    "https://secret:token@github.com/owner/repo.git",
                    "ssh://git@github.com/owner/repo.git",
                    "https://github.com:8443/owner/repo.git"):
            p = self.agent("init", "--name", "unsafe", "--url", url,
                           "--branch", "hml",
                           "--worktree", self.root / "unsafe", check=False)
            self.assertNotEqual(p.returncode, 0, url)

    def test_timer_render_without_systemctl(self):
        output = self.agent("timer", "render", "--name", "app-hml", "--minutes", "5").stdout
        self.assertIn("OnUnitInactiveSec=5min", output)
        self.assertIn("--apply", output)
        self.assertIn("NoNewPrivileges=true", output)
        self.assertIn("ourgit-app-hml.timer", "ourgit-app-hml.timer")


if __name__ == "__main__":
    unittest.main()
