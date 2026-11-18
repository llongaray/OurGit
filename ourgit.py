#!/usr/bin/env python3
"""OurGit: Git + SSH para repositorios locais, VPS e deploy por branch.

Python 3.10+ (desenvolvimento); PyInstaller gera executaveis independentes.
O daemon nao e necessario: o Git post-receive ativa o deploy no servidor.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

VERSION = "0.1.0"
INSTALL_URL = "https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.sh"
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:-]*$")
USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


class OurGitError(Exception):
    pass


def execute(args, *, cwd=None, check=True, capture=True, env=None, input_text=None, timeout=180):
    # O Git exporta GIT_DIR/GIT_WORK_TREE durante hooks. Se herdados, fazem
    # clone/fetch/checkout atuar no bare errado em vez da worktree selecionada.
    if args and Path(str(args[0])).name.lower() in ("git", "git.exe"):
        env = dict(os.environ if env is None else env)
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX",
                    "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
                    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_QUARANTINE_PATH"):
            env.pop(key, None)
    proc = subprocess.run([str(a) for a in args], cwd=cwd, env=env,
                          input=input_text, text=True, capture_output=capture,
                          timeout=timeout)
    if check and proc.returncode:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise OurGitError(f"Comando falhou ({proc.returncode}): {shlex.join([str(x) for x in args[:4]])}\n{msg}")
    return proc


def git(*args, path=None, check=True, env=None):
    return execute(["git", *args], cwd=path, check=check, env=env)


def branch_ok(name):
    if not BRANCH_RE.fullmatch(name) or name.endswith("/") or ".." in name or "@{" in name or "//" in name:
        raise OurGitError("Nome de branch invalido")
    if git("check-ref-format", "--branch", name, check=False).returncode:
        raise OurGitError("Nome de branch recusado pelo Git")
    return name


def repo_root(path=None):
    here = str(Path(path or os.getcwd()).expanduser().resolve())
    result = git("rev-parse", "--show-toplevel", path=here, check=False)
    if result.returncode:
        raise OurGitError("Diretorio nao e um repositorio Git. Execute ourgit init --git-init")
    return Path(result.stdout.strip())


def git_dir(root):
    result = git("rev-parse", "--absolute-git-dir", path=root)
    return Path(result.stdout.strip())


def config_path(root):
    return git_dir(root) / "ourgit.json"


def read_json(path, default):
    if not Path(path).exists():
        return default
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OurGitError(f"Configuracao invalida: {path}: {exc}") from exc


def save_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent,
                                     delete=False) as temp:
        json.dump(value, temp, ensure_ascii=False, indent=2)
        temp.write("\n")
        draft = temp.name
    try:
        os.replace(draft, target)
        if os.name != "nt":
            target.chmod(0o600)
    finally:
        if os.path.exists(draft):
            os.unlink(draft)


def config(root):
    return read_json(config_path(root), {"version": 1, "default": None, "remotes": {}})


def selected(root, name=None):
    cfg = config(root)
    key = name or cfg.get("default")
    remote = cfg.get("remotes", {}).get(key)
    if not remote:
        raise OurGitError("Remoto nao registrado. Use: ourgit remote add ou ourgit connect")
    return key, remote


def git_environment(remote):
    env = os.environ.copy()
    if remote.get("identity"):
        identity = Path(remote["identity"]).expanduser()
        if not identity.is_file():
            raise OurGitError(f"Chave SSH nao encontrada: {identity}")
        env["GIT_SSH_COMMAND"] = "ssh -i " + shlex.quote(str(identity)) + " -o IdentitiesOnly=yes -o BatchMode=yes"
    return env


def ensure_tools():
    if not shutil.which("git"):
        raise OurGitError("Git nao encontrado no PATH")


def local_changes(root):
    return git("status", "--porcelain=v1", "-uall", path=root).stdout.splitlines()


def counts(root, ref):
    result = git("rev-list", "--left-right", "--count", f"HEAD...{ref}", path=root, check=False)
    if result.returncode:
        return None
    a, b = result.stdout.strip().split()
    return int(a), int(b)


def remote_ref(name, remote):
    return f"refs/remotes/{name}/{remote['branch']}"


def do_fetch(root, name, remote):
    result = git("fetch", name, f"+refs/heads/{remote['branch']}:{remote_ref(name, remote)}",
                 path=root, check=False, env=git_environment(remote))
    if result.returncode:
        raise OurGitError("Falha no fetch: " + (result.stderr or result.stdout).strip())


def status_data(root, name, remote, fetch=False):
    if fetch:
        do_fetch(root, name, remote)
    ref = remote_ref(name, remote)
    ahead = counts(root, ref)
    changes = local_changes(root)
    head = git("rev-parse", "--short=10", "HEAD", path=root, check=False)
    return {"root": str(root), "remote": name, "branch": remote["branch"],
            "head": head.stdout.strip() if head.returncode == 0 else "(sem commits)",
            "local_changes": changes,
            "ahead": ahead[0] if ahead else None,
            "behind": ahead[1] if ahead else None,
            "remote_ref": ref}


def print_status(info):
    print(f"OurGit {VERSION} | {info['root']}")
    print(f"Destino: {info['remote']} / {info['branch']} | HEAD {info['head']}")
    if info["ahead"] is None:
        print("Branch remota ainda nao encontrada (primeiro push necessario).")
    else:
        print(f"PUSH pendente: {info['ahead']} commit(s) | PULL pendente: {info['behind']} commit(s)")
        if info["ahead"] and info["behind"]:
            print("DIVERGENCIA: nao realizar push forçado; reconciliar historicos.")
    changes = info["local_changes"]
    if changes:
        print(f"Arquivos nao commitados: {len(changes)}")
        for line in changes[:60]:
            print("  " + line)
        if len(changes) > 60:
            print(f"  ... outros {len(changes) - 60} arquivos")
    else:
        print("Arvore de trabalho limpa.")


def cmd_init(args):
    path = Path(args.path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    if git("rev-parse", "--show-toplevel", path=path, check=False).returncode:
        if not args.git_init:
            raise OurGitError("Nao e Git. Use --git-init para criar o repositorio explicitamente.")
        execute(["git", "init", str(path)])
    root = repo_root(path)
    if not config_path(root).exists():
        save_json(config_path(root), {"version": 1, "default": None, "remotes": {}})
    print(f"Registrado: {root} | configuracao privada em {config_path(root)}")


def add_remote(root, name, url, branch, meta=None):
    branch_ok(branch)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", name):
        raise OurGitError("Nome remoto invalido")
    existing = git("remote", "get-url", name, path=root, check=False)
    if existing.returncode == 0:
        if existing.stdout.strip() != url:
            raise OurGitError(f"Remote Git '{name}' ja existe com URL diferente.")
    else:
        git("remote", "add", name, url, path=root)
    cfg = config(root)
    cfg.setdefault("remotes", {})[name] = {"branch": branch, "url": url, **(meta or {})}
    if not cfg.get("default"):
        cfg["default"] = name
    save_json(config_path(root), cfg)
    print(f"Vinculado: {name} -> {url} (branch {branch})")


def cmd_remote_add(args):
    root = repo_root(args.path)
    add_remote(root, args.name, args.url, args.branch)


def cmd_remotes(args):
    root = repo_root(args.path)
    cfg = config(root)
    for name, remote in cfg.get("remotes", {}).items():
        default = "*" if name == cfg.get("default") else " "
        print(f"{default} {name:15s} {remote['branch']:25s} {remote['url']}")
    if not cfg.get("remotes"):
        print("Nenhum remoto cadastrado.")


def cmd_remote_default(args):
    root = repo_root(args.path)
    cfg = config(root)
    if args.name not in cfg.get("remotes", {}):
        raise OurGitError("Remote nao cadastrado.")
    cfg["default"] = args.name
    save_json(config_path(root), cfg)
    print(f"Remoto padrao: {args.name}")


def ssh_settings(args):
    if not HOST_RE.fullmatch(args.host):
        raise OurGitError("Host invalido")
    if not USER_RE.fullmatch(args.user):
        raise OurGitError("Usuario SSH invalido")
    if not 1 <= args.port <= 65535:
        raise OurGitError("Porta SSH invalida")
    if not args.repo.startswith("/") or not args.repo.endswith(".git"):
        raise OurGitError("Caminho do bare Git deve ser absoluto e terminar em .git")
    if not args.worktree.startswith("/"):
        raise OurGitError("Caminho do deploy deve ser absoluto")
    branch_ok(args.branch)
    return {"host": args.host, "user": args.user, "port": args.port,
            "repo": args.repo, "worktree": args.worktree,
            "identity": str(Path(args.identity).expanduser().resolve()) if args.identity else None}


def ssh_cmd(meta, script, *, timeout=60):
    cmd = ["ssh", "-T", "-p", str(meta["port"]), "-o", "BatchMode=yes",
           "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new"]
    if meta.get("identity"):
        cmd.extend(["-i", meta["identity"], "-o", "IdentitiesOnly=yes"])
    cmd.extend([f"{meta['user']}@{meta['host']}", script])
    return execute(cmd, timeout=timeout)


def cmd_connect(args):
    root = repo_root(args.path)
    meta = ssh_settings(args)
    if args.install_server:
        print("Instalando agente OurGit na VPS sob o usuario SSH...")
        ssh_cmd(meta, "curl -fsSL " + shlex.quote(INSTALL_URL) + " | sh", timeout=240)
    tool = '"$HOME/.local/bin/ourgit"'
    command = " ".join([tool, "server", "init", "--repo",
                        shlex.quote(meta["repo"]), "--worktree",
                        shlex.quote(meta["worktree"]), "--branch",
                        shlex.quote(args.branch)])
    result = ssh_cmd(meta, command, timeout=90)
    print(result.stdout.strip())
    url = f"ssh://{meta['user']}@{meta['host']}:{meta['port']}{quote(meta['repo'], safe='/._-')}"
    add_remote(root, args.name, url, args.branch, meta)
    print("Primeiro envio: ourgit push --remote " + args.name)


def cmd_status(args):
    root = repo_root(args.path)
    name, remote = selected(root, args.remote)
    print_status(status_data(root, name, remote, fetch=args.fetch))


def cmd_add(args):
    root = repo_root(args.path)
    if not args.files:
        raise OurGitError("Especifique arquivos, ou use ourgit add --all")
    git("add", "--", *args.files, path=root)
    print("Arquivos adicionados ao indice.")


def cmd_commit(args):
    root = repo_root(args.path)
    if args.all:
        git("add", "-A", path=root)
    res = git("diff", "--cached", "--quiet", path=root, check=False)
    if res.returncode == 0:
        raise OurGitError("Nenhuma alteracao staged. Execute ourgit add ou use commit --all")
    git("commit", "-m", args.message, path=root)
    print(git("log", "-1", "--oneline", path=root).stdout.strip())


def cmd_push(args):
    root = repo_root(args.path)
    name, remote = selected(root, args.remote)
    if args.fetch:
        do_fetch(root, name, remote)
    ref = remote_ref(name, remote)
    cc = counts(root, ref)
    if cc and cc[1]:
        raise OurGitError(f"Remote tem {cc[1]} commit(s) ausente(s) localmente. Primeiro sincronize.")
    if local_changes(root):
        print("AVISO: arquivos nao commitados nao serao enviados.")
    extra = ["--dry-run"] if args.dry_run else []
    res = git("push", *extra, name, f"HEAD:refs/heads/{remote['branch']}",
              path=root, env=git_environment(remote))
    print(res.stderr.strip() or res.stdout.strip())
    print("Push Git aceito. Para verificar deploy remoto use: ourgit server log (na VPS).")


def cmd_pull(args):
    root = repo_root(args.path)
    name, remote = selected(root, args.remote)
    if local_changes(root):
        raise OurGitError("Worktree suja. Faca commit ou stash antes do pull.")
    do_fetch(root, name, remote)
    ref = remote_ref(name, remote)
    cc = counts(root, ref)
    if cc is None:
        raise OurGitError("Branch remota inexistente.")
    if cc[0] and cc[1]:
        raise OurGitError("Historicos divergentes. Resolva via Git; merge automatico bloqueado.")
    if cc[0] and not cc[1]:
        print("Local ja esta a frente do remoto; nada a baixar.")
        return
    git("merge", "--ff-only", ref, path=root)
    print(f"Pull fast-forward concluido: {ref}")


def cmd_sync(args):
    root = repo_root(args.path)
    name, remote = selected(root, args.remote)
    do_fetch(root, name, remote)
    info = status_data(root, name, remote)
    print_status(info)
    if not args.apply:
        print("Simulacao: use --apply para realizar push ou pull seguro.")
        return
    ahead, behind = info["ahead"], info["behind"]
    if ahead is None:
        cmd_push(argparse.Namespace(path=args.path, remote=name, fetch=False, dry_run=False))
    elif ahead and behind:
        raise OurGitError("Divergencia detectada. Nenhum dado alterado.")
    elif ahead:
        cmd_push(argparse.Namespace(path=args.path, remote=name, fetch=False, dry_run=False))
    elif behind:
        cmd_pull(argparse.Namespace(path=args.path, remote=name))
    else:
        print("Sincronizado.")


def server_cfg(repo):
    repo = Path(repo).expanduser().resolve()
    if not repo.is_dir() or git("rev-parse", "--is-bare-repository", path=repo).stdout.strip() != "true":
        raise OurGitError("Caminho nao e um repositorio Git bare.")
    return repo, repo / "ourgit-server.json"


def save_server(repo, config_value):
    save_json(repo / "ourgit-server.json", config_value)


def hook_text(repo):
    if getattr(sys, "frozen", False):
        program = shlex.quote(sys.executable)
    else:
        program = shlex.quote(sys.executable) + " " + shlex.quote(str(Path(__file__).resolve()))
    command = program + " server receive --repo " + shlex.quote(str(repo))
    return ("#!/bin/sh\n"
            "while read old new ref; do\n"
            f'  {command} --old "$old" --new "$new" --ref "$ref" || echo "OurGit: deploy falhou; consulte server log" >&2\n'
            "done\n")


def cmd_server_init(args):
    if os.name == "nt":
        raise OurGitError("Agente post-receive requer Linux.")
    repo = Path(args.repo).expanduser().resolve()
    worktree = Path(args.worktree).expanduser().resolve()
    branch_ok(args.branch)
    if repo == worktree or repo in worktree.parents or worktree in repo.parents:
        raise OurGitError("Bare repo e worktree precisam ser diretorios independentes.")
    if not repo.exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        execute(["git", "init", "--bare", "--initial-branch", args.branch, str(repo)])
    if git("rev-parse", "--is-bare-repository", path=repo).stdout.strip() != "true":
        raise OurGitError("Repositorio remoto nao e bare.")
    cfg_path = repo / "ourgit-server.json"
    if cfg_path.exists():
        cfg = read_json(cfg_path, {})
        if cfg.get("branch") != args.branch or cfg.get("worktree") != str(worktree):
            raise OurGitError("Agente ja configurado para branch/worktree diferente.")
    else:
        cfg = {"version": 1, "branch": args.branch, "worktree": str(worktree),
               "action": {"enabled": False, "script": None, "timeout": 600}}
        save_server(repo, cfg)
    git("config", "receive.denyNonFastForwards", "true", path=repo)
    git("config", "receive.denyDeletes", "true", path=repo)
    hook = repo / "hooks" / "post-receive"
    if hook.exists() and hook.read_text(encoding="utf-8") != hook_text(repo):
        raise OurGitError("Hook post-receive existente diferente; nao sobrescrever sem revisao.")
    hook.write_text(hook_text(repo), encoding="utf-8")
    hook.chmod(0o750)
    print(f"Agente registrado: {repo} | branch: {args.branch} | deploy: DESABILITADO")
    print(f"Worktree apos habilitar action: {worktree}")


def log_line(repo, msg):
    line = f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {msg}"
    with (repo / "ourgit-actions.log").open("a", encoding="utf-8") as out:
        out.write(line + "\n")
    print("OurGit: " + msg, flush=True)


def cmd_server_action(args):
    repo, cfg_file = server_cfg(args.repo)
    cfg = read_json(cfg_file, None)
    if cfg is None:
        raise OurGitError("Execute ourgit server init primeiro.")
    if args.mode == "status":
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return
    if args.mode == "disable":
        cfg["action"]["enabled"] = False
        save_server(repo, cfg)
        print("Deploy automatico desabilitado.")
        return
    script = Path(args.script).expanduser().resolve()
    worktree = Path(cfg["worktree"])
    if not script.is_file() or not script.is_absolute():
        raise OurGitError("Script de deploy nao encontrado.")
    if script == worktree or worktree in script.parents:
        raise OurGitError("Script deve ser externo ao repositorio de deploy (diretorio controlado pelo administrador).")
    if not 1 <= args.timeout <= 3600:
        raise OurGitError("Timeout deve ficar entre 1 e 3600 segundos.")
    cfg["action"] = {"enabled": True, "script": str(script), "timeout": args.timeout}
    save_server(repo, cfg)
    print(f"Deploy habilitado SOMENTE na branch {cfg['branch']} com script {script}")


def cmd_server_log(args):
    repo, _ = server_cfg(args.repo)
    path = repo / "ourgit-actions.log"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    print("\n".join(lines[-args.lines:]) if lines else "Nenhum evento de deploy registrado.")


def _deploy(repo, cfg, sha):
    worktree = Path(cfg["worktree"])
    branch = cfg["branch"]
    if not worktree.exists():
        worktree.parent.mkdir(parents=True, exist_ok=True)
        execute(["git", "clone", "--no-checkout", str(repo), str(worktree)], timeout=300)
        git("fetch", "origin", f"refs/heads/{branch}", path=worktree)
        git("checkout", "-B", branch, f"origin/{branch}", path=worktree)
    else:
        if not (worktree / ".git").exists():
            raise OurGitError("Worktree existente nao e Git. Abortando para preservar arquivos.")
        origin = git("remote", "get-url", "origin", path=worktree).stdout.strip()
        if Path(origin).resolve() != repo:
            raise OurGitError("Origin do worktree nao aponta para o bare configurado.")
        if local_changes(worktree):
            raise OurGitError("Alteracoes locais na VPS: commit/push antes de executar action.")
        active = git("symbolic-ref", "--quiet", "--short", "HEAD", path=worktree, check=False)
        if active.returncode or active.stdout.strip() != branch:
            raise OurGitError("Worktree da VPS em branch diferente da configurada.")
        git("fetch", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}", path=worktree)
        target = f"refs/remotes/origin/{branch}"
        if git("merge-base", "--is-ancestor", "HEAD", target, path=worktree, check=False).returncode:
            raise OurGitError("VPS tem commits nao integrados; merge automatico bloqueado.")
        git("merge", "--ff-only", target, path=worktree)
    actual = git("rev-parse", "HEAD", path=worktree).stdout.strip()
    if actual != sha:
        raise OurGitError("SHA do worktree nao confere com a atualizacao recebida.")
    action = cfg["action"]
    env = os.environ.copy()
    env.update({"OURGIT_REPO": str(repo), "OURGIT_WORKTREE": str(worktree),
                "OURGIT_BRANCH": branch, "OURGIT_SHA": sha})
    run = execute(["/bin/sh", action["script"]], cwd=worktree, env=env,
                  timeout=action["timeout"], check=False)
    summary = (run.stdout + "\n" + run.stderr).strip()
    if summary:
        log_line(repo, "Saida: " + summary[-8000:].replace("\r", ""))
    if run.returncode:
        raise OurGitError(f"Script terminou com codigo {run.returncode}")


def cmd_server_receive(args):
    repo, cfgfile = server_cfg(args.repo)
    cfg = read_json(cfgfile, None)
    if not cfg:
        raise OurGitError("Servidor nao inicializado.")
    if args.ref != f"refs/heads/{cfg['branch']}":
        return
    if not re.fullmatch(r"[0-9a-f]{40,64}", args.new) or set(args.new) == {"0"}:
        log_line(repo, "Branch excluida; deploy ignorado.")
        return
    if not cfg["action"]["enabled"]:
        log_line(repo, f"Push recebido {args.new[:12]} em {cfg['branch']}; deploy desabilitado.")
        return
    # Um push posterior pode chegar antes do deploy anterior: sempre validar SHA atual.
    current = git("rev-parse", f"refs/heads/{cfg['branch']}", path=repo).stdout.strip()
    if current != args.new:
        log_line(repo, f"Atualizacao antiga {args.new[:12]} ignorada; HEAD mudou.")
        return
    import fcntl
    import contextlib
    with (repo / "ourgit-deploy.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            current = git("rev-parse", f"refs/heads/{cfg['branch']}", path=repo).stdout.strip()
            if current != args.new:
                log_line(repo, f"Deploy anterior {args.new[:12]} descartado apos lock.")
                return
            log_line(repo, f"Inicio deploy {cfg['branch']} SHA {current[:12]}")
            _deploy(repo, cfg, current)
            log_line(repo, f"SUCESSO deploy {current[:12]}")
        except (OSError, subprocess.TimeoutExpired, OurGitError) as exc:
            log_line(repo, f"FALHA deploy {args.new[:12]}: {type(exc).__name__}: {exc}")
            raise


def cmd_server_deploy(args):
    repo, cfgfile = server_cfg(args.repo)
    cfg = read_json(cfgfile, None)
    if not cfg:
        raise OurGitError("Servidor nao inicializado.")
    sha = git("rev-parse", f"refs/heads/{cfg['branch']}", path=repo).stdout.strip()
    cmd_server_receive(argparse.Namespace(repo=args.repo, new=sha,
                                          old="0" * 40, ref=f"refs/heads/{cfg['branch']}"))


def cmd_remote_status(args):
    root = repo_root(args.path)
    _, remote = selected(root, args.remote)
    if not remote.get("host"):
        raise OurGitError("Este remote nao possui agente SSH configurado.")
    command = '"$HOME/.local/bin/ourgit" server action status --repo ' + shlex.quote(remote["repo"])
    print(ssh_cmd(remote, command).stdout)


def cmd_server_report(args):
    repo, path = server_cfg(args.repo)
    cfg = read_json(path, None)
    if not cfg:
        raise OurGitError("Agente nao inicializado.")
    branch = cfg["branch"]
    ref = f"refs/heads/{branch}"
    commit = git("rev-parse", ref, path=repo, check=False)
    head = commit.stdout.strip() if commit.returncode == 0 else None
    result = {"repo": str(repo), "branch": branch, "remote_head": head,
              "worktree": cfg["worktree"], "worktree_head": None,
              "ahead": None, "behind": None, "dirty": [],
              "action_enabled": cfg["action"]["enabled"]}
    work = Path(cfg["worktree"])
    if (work / ".git").exists():
        tracked = git("rev-parse", "HEAD", path=work, check=False)
        if tracked.returncode == 0:
            result["worktree_head"] = tracked.stdout.strip()
            result["dirty"] = local_changes(work)
            if head:
                c = counts(work, head)
                if c:
                    result["ahead"], result["behind"] = c
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_vps_status(args):
    root = repo_root(args.path)
    _, remote = selected(root, args.remote)
    if not remote.get("host"):
        raise OurGitError("Este remote nao possui agente SSH configurado.")
    command = '"$HOME/.local/bin/ourgit" server report --repo ' + shlex.quote(remote["repo"])
    report = ssh_cmd(remote, command, timeout=40)
    data = json.loads(report.stdout)
    print(f"VPS {remote['host']} | branch {data['branch']}")
    print(f"Git bare HEAD: {data['remote_head'] or '(ainda sem push)'}")
    print(f"Checkout: {data['worktree']}")
    if data["worktree_head"]:
        print(f"Checkout HEAD: {data['worktree_head']}")
        print(f"Checkout -> bare: {data['ahead']} commit(s) a enviar")
        print(f"Bare -> checkout: {data['behind']} commit(s) a receber")
        changes = data["dirty"]
        print(f"Alteracoes nao commitadas na VPS: {len(changes)}")
        for item in changes[:60]:
            print("  " + item)
    else:
        print("Checkout da VPS ainda nao criado (action nao executada).")
    print("Action habilitada:", "SIM" if data["action_enabled"] else "NAO")


def parser():
    p = argparse.ArgumentParser(prog="ourgit", description="OurGit - Git e deploy por SSH para VPS")
    p.add_argument("--version", action="version", version=f"OurGit {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)
    i = sub.add_parser("init", help="Registrar repositorio local")
    i.add_argument("--path", default=".")
    i.add_argument("--git-init", action="store_true", help="Criar Git se ainda nao existir")
    i.set_defaults(func=cmd_init)
    rem = sub.add_parser("remote", help="Gerenciar remotos registrados")
    rsub = rem.add_subparsers(dest="rcommand", required=True)
    add = rsub.add_parser("add")
    add.add_argument("--name", default="vps")
    add.add_argument("--url", required=True)
    add.add_argument("--branch", required=True)
    add.add_argument("--path", default=".")
    add.set_defaults(func=cmd_remote_add)
    ls = rsub.add_parser("list")
    ls.add_argument("--path", default=".")
    ls.set_defaults(func=cmd_remotes)
    default = rsub.add_parser("default")
    default.add_argument("name")
    default.add_argument("--path", default=".")
    default.set_defaults(func=cmd_remote_default)
    conn = sub.add_parser("connect", help="Instalar/configurar OurGit na VPS e vincular por SSH")
    conn.add_argument("--host", required=True, help="IPv4, dominio ou host VPN")
    conn.add_argument("--user", required=True)
    conn.add_argument("--port", type=int, default=22)
    conn.add_argument("--repo", required=True, help="Caminho absoluto do Git bare na VPS, *.git")
    conn.add_argument("--worktree", required=True, help="Diretorio absoluto do deploy na VPS")
    conn.add_argument("--branch", required=True)
    conn.add_argument("--name", default="vps")
    conn.add_argument("--identity", help="Chave SSH privada local (nao enviada ao servidor)")
    conn.add_argument("--path", default=".")
    conn.add_argument("--install-server", action="store_true", help="Instalar binario Linux remoto via instalador oficial")
    conn.set_defaults(func=cmd_connect)
    for name, handler in [("status",cmd_status),("push",cmd_push),("pull",cmd_pull),("sync",cmd_sync)]:
        s = sub.add_parser(name)
        s.add_argument("--path", default=".")
        s.add_argument("--remote", default=None)
        if name == "status":
            s.add_argument("--fetch", action="store_true")
        elif name == "push":
            s.add_argument("--fetch", action="store_true")
            s.add_argument("--dry-run", action="store_true")
        elif name == "sync":
            s.add_argument("--apply", action="store_true", help="Aplicar push/pull se for fast-forward")
        s.set_defaults(func=handler)
    add_files = sub.add_parser("add", help="Preparar arquivos para commit")
    add_files.add_argument("files", nargs="*")
    add_files.add_argument("--all", action="store_true")
    add_files.add_argument("--path", default=".")
    def add_action(a):
        if a.all:
            git("add", "-A", path=repo_root(a.path))
            print("Alteracoes adicionadas ao indice.")
        else:
            cmd_add(a)
    add_files.set_defaults(func=add_action)
    co = sub.add_parser("commit")
    co.add_argument("-m", "--message", required=True)
    co.add_argument("--all", action="store_true")
    co.add_argument("--path", default=".")
    co.set_defaults(func=cmd_commit)
    sr = sub.add_parser("server", help="Agente Linux de hospedagem Git e actions")
    srv = sr.add_subparsers(dest="servercommand", required=True)
    si = srv.add_parser("init")
    si.add_argument("--repo", required=True)
    si.add_argument("--worktree", required=True)
    si.add_argument("--branch", required=True)
    si.set_defaults(func=cmd_server_init)
    sa = srv.add_parser("action")
    sa.add_argument("mode", choices=["set", "disable", "status"])
    sa.add_argument("--repo", required=True)
    sa.add_argument("--script", default="")
    sa.add_argument("--timeout", type=int, default=600)
    sa.set_defaults(func=cmd_server_action)
    slog = srv.add_parser("log")
    slog.add_argument("--repo", required=True)
    slog.add_argument("--lines", type=int, default=30)
    slog.set_defaults(func=cmd_server_log)
    report = srv.add_parser("report")
    report.add_argument("--repo", required=True)
    report.set_defaults(func=cmd_server_report)
    rec = srv.add_parser("receive")
    rec.add_argument("--repo", required=True)
    rec.add_argument("--ref", required=True)
    rec.add_argument("--old", required=True)
    rec.add_argument("--new", required=True)
    rec.set_defaults(func=cmd_server_receive)
    dep = srv.add_parser("deploy")
    dep.add_argument("--repo", required=True)
    dep.set_defaults(func=cmd_server_deploy)
    remote_status = sub.add_parser("action-status", help="Consultar action remota via SSH")
    remote_status.add_argument("--remote", default=None)
    remote_status.add_argument("--path", default=".")
    remote_status.set_defaults(func=cmd_remote_status)
    remote_worktree = sub.add_parser("vps-status", help="Comparar bare Git e checkout da VPS via SSH")
    remote_worktree.add_argument("--remote", default=None)
    remote_worktree.add_argument("--path", default=".")
    remote_worktree.set_defaults(func=cmd_vps_status)
    return p


def main(argv=None):
    try:
        ensure_tools()
        args = parser().parse_args(argv)
        args.func(args)
        return 0
    except OurGitError as exc:
        print(f"ERRO OurGit: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
        print(f"ERRO de ambiente: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
