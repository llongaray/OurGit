"""OurGit - testes de integração sem VPS real e sem acesso externo."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

APP = [sys.executable, str(Path(__file__).resolve().parents[1] / "ourgit.py")]


def run(*args, cwd=None, check=True):
    proc = subprocess.run([str(x) for x in args], cwd=cwd, text=True, capture_output=True)
    if check and proc.returncode:
        raise AssertionError(f"FALHA: {args}\nOUT: {proc.stdout}\nERR: {proc.stderr}")
    return proc


class OurGitTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.client = self.root / "client"
        self.bare = self.root / "main.git"
        run("git", "init", "-b", "hml", self.client)
        run("git", "init", "--bare", "-b", "hml", self.bare)
        run("git", "config", "user.name", "OurGit Test", cwd=self.client)
        run("git", "config", "user.email", "test@example.invalid", cwd=self.client)
        (self.client / "file.txt").write_text("inicio\n", encoding="utf-8")
        run("git", "add", "file.txt", cwd=self.client)
        run("git", "commit", "-m", "start", cwd=self.client)

    def app(self, *args, check=True):
        return run(*APP, *args, cwd=self.client, check=check)

    def setup_remote(self):
        self.app("init")
        self.app("remote", "add", "--name", "vps", "--url", self.bare, "--branch", "hml")

    def test_register_push_status_pull_fast_forward(self):
        self.setup_remote()
        self.assertIn("primeiro push", self.app("status").stdout)
        self.app("push")
        self.assertIn("refs/heads/hml", run("git", "show-ref", cwd=self.bare).stdout)
        self.assertIn("PUSH pendente: 0", self.app("status", "--fetch").stdout)
        coworker = self.root / "coworker"
        run("git", "clone", "-b", "hml", self.bare, coworker)
        run("git", "config", "user.name", "Tester", cwd=coworker)
        run("git", "config", "user.email", "test@example.invalid", cwd=coworker)
        (coworker / "file.txt").write_text("novo\n", encoding="utf-8")
        run("git", "commit", "-am", "remote changed", cwd=coworker)
        run("git", "push", "origin", "hml", cwd=coworker)
        self.assertIn("PULL pendente: 1", self.app("status", "--fetch").stdout)
        self.app("pull")
        self.assertEqual((self.client / "file.txt").read_text(), "novo\n")
        self.assertIn("PULL pendente: 0", self.app("status", "--fetch").stdout)

    def test_divergence_blocks_automatic_operations(self):
        self.setup_remote()
        self.app("push")
        coworker = self.root / "coworker"
        run("git", "clone", "-b", "hml", self.bare, coworker)
        run("git", "config", "user.name", "Tester", cwd=coworker)
        run("git", "config", "user.email", "test@example.invalid", cwd=coworker)
        (coworker / "remote.txt").write_text("remoto\n")
        run("git", "add", "-A", cwd=coworker)
        run("git", "commit", "-m", "remote", cwd=coworker)
        run("git", "push", "origin", "hml", cwd=coworker)
        (self.client / "local.txt").write_text("local\n")
        self.app("commit", "--all", "-m", "local")
        self.assertNotEqual(self.app("sync", "--apply", check=False).returncode, 0)
        self.assertNotEqual(self.app("push", "--fetch", check=False).returncode, 0)
        self.assertNotEqual(self.app("pull", check=False).returncode, 0)

    def test_untracked_file_not_sent_by_push(self):
        self.setup_remote()
        (self.client / "secret.env").write_text("test secret\n")
        self.app("push")
        tree = run("git", "ls-tree", "-r", "hml", cwd=self.bare).stdout
        self.assertNotIn("secret.env", tree)

    @unittest.skipIf(os.name == "nt", "Servidor requer Linux")
    def test_server_action_requires_opt_in_and_tracks_deploy(self):
        bare = self.root / "srv.git"
        work = self.root / "deploy"
        self.app("server", "init", "--repo", bare, "--worktree", work, "--branch", "hml")
        self.assertFalse(work.exists())
        config = self.app("server", "action", "status", "--repo", bare).stdout
        self.assertIn('"enabled": false', config)
        script = self.root / "deploy.sh"
        script.write_text('#!/bin/sh\nprintf "%s" "$OURGIT_SHA" > "$OURGIT_WORKTREE/../deployed.txt"\n')
        self.app("server", "action", "set", "--repo", bare, "--script", script)
        run("git", "remote", "add", "deploy", bare, cwd=self.client)
        pushed = run("git", "push", "deploy", "HEAD:refs/heads/hml", cwd=self.client)
        self.assertIn("new branch", pushed.stderr)
        self.assertTrue((work / "file.txt").exists())
        self.assertEqual((self.root / "deployed.txt").read_text(),
                         run("git", "rev-parse", "HEAD", cwd=self.client).stdout.strip())
        self.assertIn("SUCESSO", self.app("server", "log", "--repo", bare).stdout)
        report = self.app("server", "report", "--repo", bare).stdout
        self.assertIn('"ahead": 0', report)
        self.assertIn('"behind": 0', report)
        self.assertIn('"action_enabled": true', report)

    @unittest.skipIf(os.name == "nt", "Servidor requer Linux")
    def test_action_script_inside_worktree_is_rejected(self):
        bare = self.root / "srv.git"
        work = self.root / "deploy"
        work.mkdir()
        script = work / "action.sh"
        script.write_text("exit 0\n")
        self.app("server", "init", "--repo", bare, "--worktree", work, "--branch", "hml")
        result = self.app("server", "action", "set", "--repo", bare, "--script", script, check=False)
        self.assertNotEqual(result.returncode, 0)

    def test_git_init_is_explicit(self):
        blank = self.root / "blank"
        blank.mkdir()
        self.assertNotEqual(run(*APP, "init", "--path", blank, check=False).returncode, 0)
        run(*APP, "init", "--path", blank, "--git-init")
        self.assertTrue((blank / ".git" / "ourgit.json").exists())


if __name__ == "__main__":
    unittest.main()
