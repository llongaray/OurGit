"""Windows distribution safety: install fails closed and does not disable App Control."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WindowsDistributionTests(unittest.TestCase):
    def test_installer_diagnoses_and_rolls_back(self):
        source = (ROOT / "install/install.ps1").read_text(encoding="utf-8")
        for item in ("Get-AuthenticodeSignature", "Get-FileHash",
                     "Get-OurGitBlockMessage", "Id = 3077", "$backup",
                     "Copy-Item -LiteralPath $backup -Destination $target",
                     "Invoke-OurGitVersion -Executable $target"):
            self.assertIn(item, source)
        self.assertNotIn("Set-ExecutionPolicy", source)
        self.assertNotIn("Unblock-File", source)
        self.assertNotIn("Set-MpPreference", source)

    def test_ci_supports_signed_release_via_protected_environment(self):
        source = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("ourgit-code-signing", source)
        self.assertIn("sign_windows.ps1", source)
        self.assertIn("OURGIT_CODESIGN_PFX_BASE64", source)
        self.assertIn("OURGIT_CODESIGN_PFX_PASSWORD", source)
        self.assertIn("windows-signature.json", source)

    def test_signer_does_not_generate_self_signed_certificate(self):
        source = (ROOT / "scripts/sign_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("Import-PfxCertificate", source)
        self.assertIn("signtool.exe", source)
        self.assertIn("/fd SHA256", source)
        self.assertIn("/td SHA256", source)
        self.assertIn("Get-AuthenticodeSignature", source)
        self.assertNotIn("New-SelfSignedCertificate", source)


if __name__ == "__main__":
    unittest.main()
