"""Teste de redacao de IPs no historico automatico."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from export_history import make_report

class HistoryExportTests(unittest.TestCase):
    def setUp(self):
        self.events = [{"sha":"a"*40,"author":"Test","subject":"update",
                        "audit_source":"commit",
                        "audit":{"hostname":"workstation","local_ip":"10.0.0.4",
                                 "public_ip":"203.0.113.6","timestamp_utc":"2026-11-18T00:00:00Z"}}]

    def test_automatic_report_redacts_ips_and_hostname(self):
        report = make_report(self.events)
        self.assertFalse(report["network_metadata_included"])
        self.assertEqual(report["commits"][0]["audit"], {})
        self.assertEqual(report["commits"][0]["audit_source"], "redacted")
        data = json.dumps(report)
        for secret in ("workstation","10.0.0.4","203.0.113.6"):
            self.assertNotIn(secret, data)

    def test_manual_opt_in_includes_network_metadata(self):
        report = make_report(self.events, include_network=True)
        self.assertTrue(report["network_metadata_included"])
        self.assertEqual(report["commits"][0]["audit"]["public_ip"], "203.0.113.6")

    def test_cli_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.json"
            output_path = Path(tmp) / "out.json"
            input_path.write_text(json.dumps(self.events))
            proc = subprocess.run([sys.executable,str(ROOT/"scripts/export_history.py"),
                                   "--input",input_path,"--output",output_path],
                                  capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(json.loads(output_path.read_text())["commit_count"],1)

if __name__ == "__main__":
    unittest.main()
