"""OurGit v0.3 audit: local Git hooks + optionally portable commit metadata.

Audit is strictly opt-in. Default avoids Internet IP lookup and never shares
machine/IP in Git commits. --embed --confirm-share is explicit opt-in.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import socket
import sys
from urllib.request import Request, urlopen

MARK = "# OurGit managed commit audit v0.3"
KEYS = ("OurGit-Machine", "OurGit-LAN-IP", "OurGit-Public-IP", "OurGit-UTC")
HEX = re.compile(r"^[a-fA-F0-9]{7,64}$")


def core():
    import ourgit
    return ourgit


def fail(message):
    raise core().OurGitError(message)


def paths(repo):
    base = core().git_dir(repo)
    return base / "ourgit-audit-policy.json", base / "ourgit-audit.jsonl"


def policy(repo):
    return core().read_json(paths(repo)[0],
                            {"version": 1, "enabled": False, "public_ip": False, "embed": False})


def hooks(repo):
    custom = core().git("config", "--path", "--get", "core.hooksPath",
                        path=repo, check=False)
    if custom.returncode == 0 and custom.stdout.strip():
        fail("core.hooksPath personalizado: recuso sobrescrever hooks de outra ferramenta.")
    folder = core().git_dir(repo) / "hooks"
    return folder / "post-commit", folder / "prepare-commit-msg"


def ours(path):
    try:
        return MARK in path.read_text(encoding="utf-8")[:1000]
    except (UnicodeError, OSError):
        return False


def program():
    if getattr(sys, "frozen", False):
        args = [str(Path(sys.executable).resolve())]
    else:
        args = [sys.executable, str(Path(__file__).resolve().parent / "ourgit.py")]
    return " ".join(shlex.quote(a.replace("\\", "/")) for a in args)


def hook_content(kind):
    cmd = program()
    if kind == "prepare":
        # Assemble shell positional expansion without embedding Python format fields.
        cmd += ' audit stamp --file "$1" --source "$' + '{2:-}"'
    else:
        cmd += " audit record"
    return "#!/bin/sh\n" + MARK + "\n" + cmd + "\n"


def write_hook(path, content):
    if path.exists() and not ours(path):
        fail(f"Hook de outro software detectado, nao modificar: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    if os.name != "nt":
        path.chmod(0o750)


def cmd_enable(args):
    repo = core().repo_root(args.path)
    post, prepare = hooks(repo)
    if post.exists() and not ours(post):
        fail("post-commit de terceiro detectado. Nao sobrescrever.")
    if args.embed and prepare.exists() and not ours(prepare):
        fail("prepare-commit-msg de terceiro detectado. Nao sobrescrever.")
    if args.embed and not args.confirm_share:
        fail("--embed inclui dados da maquina nos commits compartilhados. Confirme conscientemente com --confirm-share.")
    config = {"version": 1, "enabled": True,
              "public_ip": bool(args.public_ip), "embed": bool(args.embed)}
    core().save_json(paths(repo)[0], config)
    write_hook(post, hook_content("record"))
    if args.embed:
        write_hook(prepare, hook_content("prepare"))
    elif prepare.exists() and ours(prepare):
        prepare.unlink()
    print("Auditoria ATIVADA apenas neste repositorio.")
    print("Hostname/IP LAN: log PRIVADO em .git/ourgit-audit.jsonl")
    print("Consulta IP publico:", "SIM via HTTPS externo" if args.public_ip else "NAO")
    print("Metadados transportados com commits:", "SIM (opt-in)" if args.embed else "NAO")
    if args.public_ip:
        print("Aviso: IP publico e o endereco de SAIDA do NAT/VPN; pode nao ser o IP da maquina.")


def cmd_disable(args):
    repo = core().repo_root(args.path)
    for hook in hooks(repo):
        if hook.exists() and ours(hook):
            hook.unlink()
    cfg = policy(repo)
    cfg["enabled"] = False
    core().save_json(paths(repo)[0], cfg)
    print("Auditoria DESABILITADA. Registros antigos em .git foram preservados.")


def cmd_status(args):
    repo = core().repo_root(args.path)
    cfg = policy(repo)
    post, prepare = hooks(repo)
    enabled = bool(cfg.get("enabled") and post.exists() and ours(post))
    print("Auditoria de commits:", "ATIVA" if enabled else "desativada")
    print("Hostname e IP LAN:", "log local" if enabled else "nao coletados")
    print("IP publico:", "consulta HTTPS opcional" if cfg.get("public_ip") else "desativado")
    print("Trailers em commit:", "SIM" if cfg.get("embed") else "NAO")
    print("Registros: " + str(paths(repo)[1]))


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def hostname():
    return re.sub(r"[^A-Za-z0-9_.-]", "_", socket.gethostname())[:128] or "unknown"


def lan_ip(repo):
    # UDP connect apenas escolhe a rota; nenhum datagrama e enviado.
    target = "192.0.2.1"
    try:
        cfg = core().config(repo)
        for remote in cfg.get("remotes", {}).values():
            host = str(remote.get("host", ""))
            try:
                target = str(ipaddress.IPv4Address(host))
                break
            except ipaddress.AddressValueError:
                continue
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1)
            sock.connect((target, 9))
            return str(ipaddress.ip_address(sock.getsockname()[0]))
    except (OSError, ValueError):
        return "unavailable"


def public_ip():
    try:
        request = Request("https://api.ipify.org", headers={"User-Agent": "OurGit/0.3"})
        with urlopen(request, timeout=3) as result:
            candidate = result.read(96).decode("ascii").strip()
        return str(ipaddress.ip_address(candidate))
    except (OSError, ValueError, UnicodeError):
        return "unavailable"


def attributes(repo):
    config = policy(repo)
    return {"hostname": hostname(), "local_ip": lan_ip(repo),
            "public_ip": public_ip() if config.get("public_ip") else None,
            "timestamp_utc": utc()}


def cmd_stamp(args):
    repo = core().repo_root(args.path)
    cfg = policy(repo)
    if not cfg.get("enabled") or not cfg.get("embed"):
        return
    if args.source in ("merge", "squash", "commit"):
        return  # nao modificar mensagens de merges, cherry-picks ou --amend
    message_file = Path(args.file)
    if not message_file.is_file():
        fail("Arquivo da mensagem de commit indisponivel.")
    message = message_file.read_text(encoding="utf-8")
    if any(re.search(rf"(?m)^{re.escape(key)}:\s*", message) for key in KEYS):
        return
    lines = message.splitlines(keepends=True)
    cut = next((i for i, line in enumerate(lines) if line.startswith("#")), len(lines))
    head = "".join(lines[:cut]).rstrip()
    comments = "".join(lines[cut:])
    if not head:
        return
    d = attributes(repo)
    trailers = [f"OurGit-Machine: {d['hostname']}",
                f"OurGit-LAN-IP: {d['local_ip']}"]
    if d["public_ip"] is not None:
        trailers.append(f"OurGit-Public-IP: {d['public_ip']}")
    trailers.append(f"OurGit-UTC: {d['timestamp_utc']}")
    message_file.write_text(head + "\n\n" + "\n".join(trailers) + "\n" +
                            ("\n" + comments if comments else ""),
                            encoding="utf-8")


def current_branch(repo):
    res = core().git("symbolic-ref", "--quiet", "--short", "HEAD",
                     path=repo, check=False)
    return res.stdout.strip() if res.returncode == 0 else "(detached)"


def cmd_record(args):
    repo = core().repo_root(args.path)
    if not policy(repo).get("enabled"):
        return
    sha = core().git("rev-parse", "HEAD", path=repo).stdout.strip()
    info = core().git("log", "-1", "--format=%an%x1f%ae%x1f%aI%x1f%s",
                      path=repo).stdout.strip().split("\x1f")
    d = attributes(repo)
    event = {"sha": sha, "branch": current_branch(repo),
             "author": info[0], "author_email": info[1],
             "author_date": info[2], "subject": info[3], **d}
    ledger = paths(repo)[1]
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as log:
        log.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    if os.name != "nt":
        ledger.chmod(0o600)
    print(f"OurGit audit: commit {sha[:12]} maquina={d['hostname']}")


def local_entries(repo):
    ledger = paths(repo)[1]
    if not ledger.exists():
        return []
    records = []
    with ledger.open("r", encoding="utf-8") as log:
        for line in log:
            try:
                rec = json.loads(line)
                if isinstance(rec, dict) and HEX.fullmatch(str(rec.get("sha", ""))):
                    records.append(rec)
            except json.JSONDecodeError:
                continue
    return records


def cmd_log(args):
    repo = core().repo_root(args.path)
    limit = min(max(args.limit, 1), 1000)
    entries = local_entries(repo)[-limit:]
    if args.json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
    elif not entries:
        print("Sem auditoria local. Para habilitar: ourgit audit enable")
    else:
        for e in entries:
            ip = e.get("public_ip")
            print(f"{e.get('timestamp_utc', '')} {e['sha'][:12]} "
                  f"{e.get('hostname', '')} LAN={e.get('local_ip', '')}"
                  + (f" SAIDA={ip}" if ip else "")
                  + f" | {e.get('subject', '')}")


def register(sub):
    audit = sub.add_parser("audit", help="Auditoria de commits: hostname, IP LAN e IP de saida opcional")
    commands = audit.add_subparsers(dest="auditcommand", required=True)
    enable = commands.add_parser("enable", help="Habilitar hooks Git para rastrear quem fez cada commit (opt-in)")
    enable.add_argument("--path", default=".")
    enable.add_argument("--public-ip", action="store_true",
                        help="Consultar IP publico de saida via HTTPS, explicitamente")
    enable.add_argument("--embed", action="store_true",
                        help="Incluir metadados como trailers nos commits compartilhados")
    enable.add_argument("--confirm-share", action="store_true",
                        help="Confirmar divulgacao da maquina e IPs no historico Git")
    enable.set_defaults(func=cmd_enable)
    for name, handler in (("disable", cmd_disable), ("status", cmd_status),
                          ("log", cmd_log), ("record", cmd_record)):
        cmd = commands.add_parser(name)
        cmd.add_argument("--path", default=".")
        if name == "log":
            cmd.add_argument("--limit", type=int, default=20)
            cmd.add_argument("--json", action="store_true")
        cmd.set_defaults(func=handler)
    stamp = commands.add_parser("stamp", help=argparse.SUPPRESS)
    stamp.add_argument("--file", required=True)
    stamp.add_argument("--source", default="")
    stamp.add_argument("--path", default=".")
    stamp.set_defaults(func=cmd_stamp)
