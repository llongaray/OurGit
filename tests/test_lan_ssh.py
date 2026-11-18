"""Regression tests: HTTPS installer is distinct from Git-over-SSH on private LAN.

No real SSH connection or production VPS is contacted.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ourgit


class LANSSHConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name) / "my-project"
        subprocess.run(["git", "init", str(self.work)], check=True,
                       capture_output=True, text=True)
        self.assertEqual(ourgit.VERSION, "0.2.0")
        ourgit.cmd_init(argparse.Namespace(path=str(self.work), git_init=False))

    def test_private_ip_and_custom_ssh_port_without_public_ssh(self):
        args = argparse.Namespace(
            path=str(self.work),
            host="192.168.10.20",
            user="deploy",
            port=2222,
            repo="/home/deploy/repos/demo-hml.git",
            worktree="/home/deploy/apps/demo-hml",
            branch="hml",
            name="vps-hml",
            identity=None,
            install_server=False,
        )
        calls = []
        def fake_ssh(meta, command, timeout=60):
            calls.append((meta, command, timeout))
            return SimpleNamespace(stdout="Servidor inicializado\n")
        with patch.object(ourgit, "ssh_cmd", side_effect=fake_ssh):
            ourgit.cmd_connect(args)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0]["host"], "192.168.10.20")
        self.assertEqual(calls[0][0]["port"], 2222)
        self.assertIn("server init", calls[0][1])
        self.assertNotIn("curl", calls[0][1])
        remote = ourgit.git("remote", "get-url", "vps-hml", path=self.work).stdout.strip()
        self.assertEqual(remote,
                         "ssh://deploy@192.168.10.20:2222/home/deploy/repos/demo-hml.git")
        config = ourgit.config(self.work)
        self.assertEqual(config["remotes"]["vps-hml"]["branch"], "hml")
        self.assertEqual(config["remotes"]["vps-hml"]["worktree"], "/home/deploy/apps/demo-hml")

    def test_readme_portuguese_first_english_second(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        pt = readme.index("# OurGit — Git remoto")
        en = readme.index("# English documentation")
        self.assertEqual(pt, 0)
        self.assertGreater(en, 15000)
        self.assertIn("instalação** usa HTTPS", readme[:en])
        self.assertIn("SSH pelo IP LAN", readme[:en])
        self.assertIn("installation happens over outbound HTTPS", readme[en:])
        self.assertIn("source-code synchronization happens over Git-over-SSH", readme[en:])

    def test_windows_documentation_supports_restricted_execution_policy(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        pt, en = readme.split("# English documentation", 1)
        expected = 'Get-Content -LiteralPath "$env:TEMP\\install-ourgit.ps1" -Raw | Invoke-Expression'
        self.assertIn(expected, pt)
        self.assertIn(expected, en)
        self.assertNotIn('& "$env:TEMP\\install-ourgit.ps1"', readme)
        self.assertIn("Get-ExecutionPolicy -List", readme)

    def test_both_https_installers_present(self):
        linux = (ROOT / "install" / "install.sh").read_text(encoding="utf-8")
        win = (ROOT / "install" / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("https://github.com/llongaray/OurGit/releases/latest/download", linux)
        self.assertIn("https://github.com/llongaray/OurGit/releases/latest/download", win)
        self.assertIn("sha256sum", linux)
        self.assertIn("SHA256", win)
        self.assertNotIn("ssh -p", linux)
        self.assertNotIn("ssh -p", win)


if __name__ == "__main__":
    unittest.main()
