"""Exportador de historico CI: rede privada redigida por padrao."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

def make_report(entries, include_network=False):
    clean = []
    for original in entries:
        item = dict(original)
        if include_network:
            item["audit"] = dict(item.get("audit") or {})
        else:
            if item.get("audit"):
                item["audit_source"] = "redacted"
            item["audit"] = {}
        clean.append(item)
    return {"schema": "ourgit.history.v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "network_metadata_included": bool(include_network),
            "commit_count": len(clean), "commits": clean}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--include-network", action="store_true",
                   help="AVISO: hostname/IPs podem estar em commits publicos")
    args = p.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        p.error("Entrada invalida: esperado JSON array do 'ourgit history --json'")
    report = make_report(data, args.include_network)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OurGit: {report['commit_count']} commits; metadados rede={'SIM' if args.include_network else 'NAO'}")

if __name__ == "__main__":
    main()
