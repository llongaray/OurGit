"""OurGit App Control: read-only diagnostics, no security policy changes."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class AppControlDiagnosticsTests(unittest.TestCase):
    def test_source_only_no_execution_or_policy_changes(self):
        s = (ROOT / "scripts/diagnose_windows_appcontrol.ps1").read_text(encoding="utf-8")
        for token in ("v0.2.0", "v0.3.1", "3077, 3089, 3092",
                      "Get-FileHash", "Get-AuthenticodeSignature", "SHA256",
                      "CodeIntegrity/Operational", "Expand-Archive"):
            self.assertIn(token, s)
        for forbidden in ("Set-ExecutionPolicy", "Unblock-File", "Set-MpPreference",
                          "Set-CIPolicy", "Start-Process", "& $binary", "& $exe"):
            self.assertNotIn(forbidden, s)

if __name__ == "__main__":
    unittest.main()
