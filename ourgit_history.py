"""OurGit v0.3: history and safe recovery using native Git (no dedicated server).

History is readable locally without an OurGit remote and without network.
File restoration and creating recovery branches are preview-only by default.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import shutil

HEX = re.compile(r"^[a-fA-F0-9]{7,64}$")


def core():
    import ourgit
    return ourgit


def fail(message):
    raise core().OurGitError(message)


def root(args):
    return core().repo_root(args.path)


def verify_commit(repo, revision):
    if not HEX.fullmatch(revision):
        fail("Informe SHA hexadecimal de commit com 7 a 64 caracteres. Consulte: ourgit history")
    result = core().git("rev-parse", "--verify", f"{revision}^{{commit}}",
                        path=repo, check=False)
    if result.returncode:
        fail(f"Commit ausente deste clone: {revision}. Execute git fetch quando existir em outro remote.")
    return result.stdout.strip()


def safe_relative(repo, value):
    if not value or value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
        fail("Caminho absoluto nao e permitido. Informe caminho relativo ao repositorio.")
    p = PurePosixPath(value.replace("\\", "/"))
    if ".." in p.parts or p.as_posix() == "." or p.is_absolute():
        fail("Caminho inseguro (.. ou pasta externa).")
    target = repo.joinpath(*p.parts)
    if not target.resolve(strict=False).is_relative_to(repo.resolve()):
        fail("O caminho aponta para fora do repositorio.")
    return p.as_posix()


def portable_details(body):
    result = {}
    mapping = {"OurGit-Machine": "hostname",
               "OurGit-LAN-IP": "local_ip",
               "OurGit-Public-IP": "public_ip",
               "OurGit-UTC": "timestamp_utc"}
    for line in body.splitlines():
        for trailer, key in mapping.items():
            prefix = trailer + ": "
            if line.startswith(prefix):
                result[key] = line[len(prefix):].strip()
    return result


def history_entries(repo, limit=20, all_refs=False):
    if not 1 <= limit <= 1000:
        fail("--limit aceita valores entre 1 e 1000")
    format_spec = "%H%x1f%aI%x1f%an%x1f%ae%x1f%s%x1f%b%x1e"
    args = ["log", "--no-patch", f"--format={format_spec}", f"-n{limit}"]
    if all_refs:
        args.append("--all")
    result = core().git(*args, path=repo, check=False)
    if result.returncode:
        # Novo repositorio sem commits ainda e valido para historico.
        if "does not have any commits yet" in result.stderr or "your current branch" in result.stderr:
            return []
        fail(result.stderr.strip())
    audit = __import__("ourgit_audit")
    local_events = {item["sha"]: item for item in audit.local_entries(repo)}
    history = []
    for row in result.stdout.split("\x1e"):
        parts = row.strip("\r\n").split("\x1f", 5)
        if len(parts) != 6:
            continue
        sha, when, author, email, subject, body = parts
        portable = portable_details(body)
        details = portable or {key: local_events[sha].get(key) for key in
                               ("hostname", "local_ip", "public_ip", "timestamp_utc")
                               if key in local_events[sha]} if sha in local_events else portable
        history.append({"sha": sha, "date": when, "author": author,
                        "author_email": email, "subject": subject,
                        "audit": details,
                        "audit_source": "commit" if portable else
                                        "local-only" if details else "unavailable"})
    return history


def cmd_history(args):
    repo = root(args)
    events = history_entries(repo, args.limit, args.all)
    if args.json:
        print(json.dumps(events, ensure_ascii=False, indent=2))
        return
    if not events:
        print("Nenhum commit encontrado neste repositorio.")
        return
    for e in events:
        d = e["audit"]
        label = (f"host={d.get('hostname', '?')}, "
                 f"LAN={d.get('local_ip', '?')}, "
                 f"public={d.get('public_ip') or '(nao coletado)'}"
                 f" [{e['audit_source']}]") if d else "sem metadados de maquina/IP"
        print(f"{e['sha'][:12]} | {e['date']} | {e['author']} | {e['subject']}\n  {label}")


def cmd_show(args):
    repo = root(args)
    sha = verify_commit(repo, args.commit)
    if args.file:
        rel = safe_relative(repo, args.file)
        obj = core().git("cat-file", "-t", f"{sha}:{rel}", path=repo, check=False)
        if obj.returncode or obj.stdout.strip() != "blob":
            fail("Arquivo nao encontrado neste commit.")
        # Exibicao textual; arquivos binarios devem ser restaurados, nao impressos.
        data = core().execute(["git", "show", f"{sha}:{rel}"],
                              cwd=repo, check=False, capture=True)
        if data.returncode:
            fail(data.stderr.strip())
        print(data.stdout, end="")
    else:
        print(core().git("show", "--format=fuller", "--stat", sha, path=repo).stdout)


def cmd_diff(args):
    repo = root(args)
    start = verify_commit(repo, args.from_sha)
    end = verify_commit(repo, args.to_sha)
    options = ["diff", "--no-ext-diff", "--name-status" if args.names else "--stat",
               start, end]
    if args.file:
        options.extend(["--", safe_relative(repo, args.file)])
    print(core().git(*options, path=repo).stdout)


def cmd_recover(args):
    repo = root(args)
    sha = verify_commit(repo, args.commit)
    if bool(args.file) == bool(args.branch):
        fail("Indique exatamente um: --file CAMINHO ou --branch NOME.")
    if args.branch:
        name = core().branch_ok(args.branch)
        exists = core().git("show-ref", "--quiet", "--verify", f"refs/heads/{name}",
                            path=repo, check=False)
        if exists.returncode == 0:
            fail("Branch de recuperacao ja existe. Nenhuma referencia foi alterada.")
        print(f"Recuperar codigo completo criando branch '{name}' em {sha}.")
        print("Branch ativa, arquivos atuais e repositorio remoto nao serao modificados.")
        if args.apply:
            core().git("branch", name, sha, path=repo)
            print(f"Criada {name}. Para revisar, execute: git switch {name}")
        else:
            print("PREVIA: use --apply para criar a branch.")
        return
    rel = safe_relative(repo, args.file)
    obj = core().git("cat-file", "-t", f"{sha}:{rel}", path=repo, check=False)
    if obj.returncode or obj.stdout.strip() != "blob":
        fail("Arquivo nao existe no commit de origem ou nao e um blob Git.")
    dest = repo.joinpath(*PurePosixPath(rel).parts)
    if dest.is_symlink():
        fail("Destino atual e symlink. Recupere manualmente.")
    dirty = core().git("status", "--porcelain=v1", "-uall", "--", rel,
                       path=repo).stdout.strip()
    if dirty and not args.backup:
        fail("Arquivo possui alteracoes locais/untracked. Use --backup para guardar antes de restaurar.")
    print(f"Arquivo: {rel}\nCommit origem: {sha}\nDestino: {dest}")
    if not args.apply:
        print("PREVIA: use --apply para restaurar. Nenhuma alteracao feita.")
        return
    if dirty and args.backup and dest.exists():
        if not dest.is_file():
            fail("Destino nao e arquivo comum. Nenhuma alteracao.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = core().git_dir(repo) / "ourgit-backups" / f"{stamp}-{sha[:12]}" / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, backup)
        print(f"Backup antes da recuperacao: {backup}")
    core().git("restore", f"--source={sha}", "--worktree", "--", rel, path=repo)
    print("Arquivo restaurado para a WORKTREE (sem commit/push automatico).")


def cmd_revert(args):
    repo = root(args)
    sha = verify_commit(repo, args.commit)
    summary = core().git("show", "--format=%h %s", "--stat", sha, path=repo).stdout
    print("Gerar novo commit que reverte alteracoes (sem apagar historico):\n" + summary)
    if not args.apply:
        print("PREVIA: use --apply para executar git revert --no-edit.")
        return
    if core().local_changes(repo):
        fail("Worktree suja. Faça commit ou stash antes de reverter.")
    parents = core().git("rev-list", "--parents", "-n", "1", sha, path=repo).stdout.split()
    if len(parents) != 2:
        fail("Revert automatico de merge/root nao suportado. Trate manualmente.")
    core().git("revert", "--no-edit", sha, path=repo)
    print("Revert criou novo commit. Historico anterior preservado.")


def register(sub):
    hist = sub.add_parser("history", help="Historico Git e auditoria da maquina/IP")
    hist.add_argument("--path", default=".")
    hist.add_argument("--limit", type=int, default=20)
    hist.add_argument("--all", action="store_true", help="Todas as refs disponiveis")
    hist.add_argument("--json", action="store_true", help="Exportacao estruturada para CI/pipeline")
    hist.set_defaults(func=cmd_history)
    show = sub.add_parser("show", help="Inspecionar commit/arquivo antigo")
    show.add_argument("commit")
    show.add_argument("--file")
    show.add_argument("--path", default=".")
    show.set_defaults(func=cmd_show)
    diff = sub.add_parser("diff", help="Comparar commits antigos por arquivos")
    diff.add_argument("--from", dest="from_sha", required=True)
    diff.add_argument("--to", dest="to_sha", required=True)
    diff.add_argument("--file")
    diff.add_argument("--names", action="store_true")
    diff.add_argument("--path", default=".")
    diff.set_defaults(func=cmd_diff)
    rec = sub.add_parser("recover", help="Restaurar arquivo ou criar branch de recuperacao")
    rec.add_argument("--commit", required=True)
    rec.add_argument("--file")
    rec.add_argument("--branch")
    rec.add_argument("--backup", action="store_true")
    rec.add_argument("--apply", action="store_true")
    rec.add_argument("--path", default=".")
    rec.set_defaults(func=cmd_recover)
    rev = sub.add_parser("revert", help="Reverter commit por novo commit sem apagar historico")
    rev.add_argument("commit")
    rev.add_argument("--apply", action="store_true")
    rev.add_argument("--path", default=".")
    rev.set_defaults(func=cmd_revert)
