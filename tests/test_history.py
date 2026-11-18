"""OurGit 0.3: history, recovery, audit hooks and machine/IP privacy.

Uses only temporary local Git repositories and deterministic offline tests.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

APP = [sys.executable, str(Path(__file__).resolve().parents[1] / "ourgit.py")]


def run(*args, cwd=None, check=True):
    p = subprocess.run([str(a) for a in args], cwd=cwd,
                       capture_output=True, text=True, timeout=90)
    if check and p.returncode:
        raise AssertionError(f"{args}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p


class HistoryTests(unittest.TestCase):
    def setUp(self):
        obj = tempfile.TemporaryDirectory()
        self.addCleanup(obj.cleanup)
        self.root = Path(obj.name) / "project"
        run("git", "init", "-b", "main", self.root)
        run("git", "config", "user.name", "OurGit History Tests", cwd=self.root)
        run("git", "config", "user.email", "test@example.invalid", cwd=self.root)
        self.file = self.root / "app.py"
        self.file.write_text("print('v1')\n", encoding="utf-8")
        run("git", "add", "app.py", cwd=self.root)
        run("git", "commit", "-m", "initial commit", cwd=self.root)
        self.first = run("git", "rev-parse", "HEAD", cwd=self.root).stdout.strip()

    def app(self, *args, check=True):
        return run(*APP, *args, cwd=self.root, check=check)

    def second_commit(self):
        self.file.write_text("print('v2')\n", encoding="utf-8")
        run("git", "commit", "-am", "version 2", cwd=self.root)
        return run("git", "rev-parse", "HEAD", cwd=self.root).stdout.strip()

    def test_history_json_with_no_remote_and_diff(self):
        second = self.second_commit()
        events = json.loads(self.app("history", "--json", "--limit", "10").stdout)
        self.assertEqual(events[0]["sha"], second)
        self.assertEqual(events[1]["sha"], self.first)
        self.assertEqual(events[0]["audit_source"], "unavailable")
        self.assertIn("app.py", self.app("diff", "--from", self.first, "--to", second, "--names").stdout)
        self.assertIn("initial commit", self.app("show", self.first).stdout)
        self.assertIn("print('v1')", self.app("show", self.first, "--file", "app.py").stdout)

    def test_recover_file_is_preview_first_and_never_auto_commits(self):
        second = self.second_commit()
        preview = self.app("recover", "--commit", self.first, "--file", "app.py").stdout
        self.assertIn("PREVIA", preview)
        self.assertEqual(self.file.read_text(), "print('v2')\n")
        self.app("recover", "--commit", self.first, "--file", "app.py", "--apply")
        self.assertEqual(self.file.read_text(), "print('v1')\n")
        self.assertEqual(run("git", "rev-parse", "HEAD", cwd=self.root).stdout.strip(), second)
        self.assertIn(" M app.py", run("git", "status", "--porcelain", cwd=self.root).stdout)

    def test_recover_branch_preserves_current_head_and_checkout(self):
        second = self.second_commit()
        self.app("recover", "--commit", self.first, "--branch", "recovery/v1")
        self.assertNotIn("recovery/v1", run("git", "branch", cwd=self.root).stdout)
        self.app("recover", "--commit", self.first, "--branch", "recovery/v1", "--apply")
        recovered = run("git", "rev-parse", "recovery/v1", cwd=self.root).stdout.strip()
        self.assertEqual(recovered, self.first)
        self.assertEqual(run("git", "rev-parse", "HEAD", cwd=self.root).stdout.strip(), second)
        self.assertEqual(self.file.read_text(), "print('v2')\n")
        self.assertNotEqual(self.app("recover", "--commit", self.first, "--branch",
                                     "recovery/v1", "--apply", check=False).returncode, 0)

    def test_recovery_refuses_dirty_file_by_default_but_creates_backup_with_opt_in(self):
        self.second_commit()
        self.file.write_text("unsaved current changes\n")
        p = self.app("recover", "--commit", self.first, "--file", "app.py",
                     "--apply", check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.file.read_text(), "unsaved current changes\n")
        self.app("recover", "--commit", self.first, "--file", "app.py",
                 "--apply", "--backup")
        self.assertEqual(self.file.read_text(), "print('v1')\n")
        backups = list((self.root / ".git" / "ourgit-backups").rglob("app.py"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "unsaved current changes\n")

    def test_recovery_blocks_path_traversal_and_invalid_sha(self):
        self.second_commit()
        p = self.app("recover", "--commit", self.first, "--file", "../passwd",
                     "--apply", check=False)
        self.assertNotEqual(p.returncode, 0)
        p = self.app("recover", "--commit", "-bad", "--file", "app.py",
                     "--apply", check=False)
        self.assertNotEqual(p.returncode, 0)

    def test_revert_does_not_rewrite_history_or_act_without_apply(self):
        second = self.second_commit()
        self.app("revert", second)
        self.assertEqual(run("git", "rev-parse", "HEAD", cwd=self.root).stdout.strip(), second)
        self.app("revert", second, "--apply")
        self.assertEqual(self.file.read_text(), "print('v1')\n")
        events = json.loads(self.app("history", "--json").stdout)
        self.assertEqual(len(events), 3)

    def test_audit_local_only_does_not_expose_machine_in_commit(self):
        self.app("audit", "enable")
        status = self.app("audit", "status").stdout
        self.assertIn("ATIVA", status)
        self.assertIn("IP publico: desativado", status)
        self.second_commit()
        events = json.loads(self.app("audit", "log", "--json").stdout)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["public_ip"], None)
        self.assertTrue(events[0]["hostname"])
        self.assertEqual(len(events[0]["sha"]), 40)
        body = run("git", "log", "-1", "--format=%B", cwd=self.root).stdout
        self.assertNotIn("OurGit-Machine", body)
        entries = json.loads(self.app("history", "--json").stdout)
        self.assertEqual(entries[0]["audit_source"], "local-only")
        self.app("audit", "disable")
        self.assertIn("desativada", self.app("audit", "status").stdout.lower())

    def test_embed_audit_trailers_require_explicit_consent(self):
        fail = self.app("audit", "enable", "--embed", check=False)
        self.assertNotEqual(fail.returncode, 0)
        self.app("audit", "enable", "--embed", "--confirm-share")
        self.second_commit()
        body = run("git", "log", "-1", "--format=%B", cwd=self.root).stdout
        self.assertIn("OurGit-Machine:", body)
        self.assertIn("OurGit-LAN-IP:", body)
        self.assertIn("OurGit-UTC:", body)
        self.assertNotIn("OurGit-Public-IP:", body)
        item = json.loads(self.app("history", "--json").stdout)[0]
        self.assertEqual(item["audit_source"], "commit")
        self.app("audit", "disable")

    def test_does_not_overwrite_third_party_git_hooks(self):
        hook = self.root / ".git" / "hooks" / "post-commit"
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        p = self.app("audit", "enable", check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(hook.read_text(), "#!/bin/sh\nexit 0\n")


if __name__ == "__main__":
    unittest.main()
