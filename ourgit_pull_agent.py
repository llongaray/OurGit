"""OurGit Pull Agent: deploy autonomo por HTTPS de saida, sem SSH de entrada.

O agente roda na VPS Linux, usando Git HTTPS + systemd timer de usuario.
A VPS nunca expoe um listener HTTP: instala-se via console administrativo.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
from urllib.parse import urlsplit


_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


def _core():
    import ourgit
    return ourgit


def _fail(msg):
    raise _core().OurGitError(msg)


def _name(name):
    if not _NAME.fullmatch(name):
        _fail("Nome do agente invalido: use letras minusculas, numeros, _ ou -; inicie com letra.")
    return name


def _dir():
    base = Path(os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config")).expanduser().resolve()
    return base / "ourgit" / "agents"


def _paths(name):
    name = _name(name)
    return _dir() / f"{name}.json", _dir() / f"{name}.state.json", _dir() / f"{name}.log"


def _load(name):
    file, state, log = _paths(name)
    cfg = _core().read_json(file, None)
    if cfg is None:
        _fail(f"Agente '{name}' nao configurado. Execute: ourgit agent init.")
    return cfg, file, state, log


def _log(path, message):
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {message}"
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as out:
        out.write(line + "\n")
    print("OurGit Agent: " + message, flush=True)


def _source(url):
    value = url.strip()
    if os.getenv("OURGIT_ALLOW_LOCAL_SOURCE") == "1" and Path(value).is_absolute():
        if not Path(value).is_dir():
            _fail("Git local de teste nao encontrado.")
        return str(Path(value).resolve())
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        _fail("Use URL Git HTTPS sem usuario/token embutido, ex.: https://github.com/owner/repo.git")
    if parsed.query or parsed.fragment:
        _fail("URL de origem Git nao pode incluir query ou fragment.")
    if parsed.port is not None and parsed.port != 443:
        _fail("Somente HTTPS na porta padrao 443 e permitido no Pull Agent.")
    return value


def _git(*args, cwd=None, check=True, timeout=300):
    core = _core()
    return core.execute(["git", *args], cwd=cwd, check=check, timeout=timeout)


def _is_git(path):
    if not (path / ".git").exists():
        return False
    p = _git("rev-parse", "--is-inside-work-tree", cwd=path, check=False)
    return p.returncode == 0 and p.stdout.strip() == "true"


def _head(path):
    p = _git("rev-parse", "HEAD", cwd=path, check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def _remote_head(cfg):
    # Entrada HTTPS de origem fica sob controle do administrador e
    # nao usa SSH nem servidor HTTP no destino.
    p = _git("ls-remote", "--heads", cfg["url"], f"refs/heads/{cfg['branch']}", timeout=60)
    rows = [line.split() for line in p.stdout.splitlines() if line.strip()]
    exact = f"refs/heads/{cfg['branch']}"
    for row in rows:
        if len(row) == 2 and row[1] == exact:
            return row[0]
    _fail(f"Branch '{cfg['branch']}' nao encontrada em {cfg['url']}")


def _changes(path):
    return _git("status", "--porcelain=v1", "-uall", cwd=path).stdout.splitlines()


def _check_existing(worktree, cfg):
    if not _is_git(worktree):
        _fail("O caminho do deploy ja existe, mas nao e checkout Git. Nada foi alterado.")
    origin = _git("remote", "get-url", "origin", cwd=worktree).stdout.strip()
    if origin != cfg["url"]:
        _fail("Origin da worktree difere da origem HTTPS autorizada. Nada foi alterado.")
    branch = _git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=worktree, check=False)
    if branch.returncode or branch.stdout.strip() != cfg["branch"]:
        _fail("Worktree com branch diferente ou HEAD detached. Nada foi alterado.")
    changes = _changes(worktree)
    if changes:
        _fail(f"Worktree VPS com {len(changes)} alteracao(oes) nao commitada(s); commit/stash manual necessario.")


def _source_credentials_warning():
    return ("Em repositorios privados, configure previamente credenciais Git HTTPS "
            "de leitura no usuario do agente; nunca coloque tokens na URL, action ou config.")


def cmd_init(args):
    if sys.platform != "linux":
        _fail("Pull Agent e systemd timer requerem Linux.")
    name = _name(args.name)
    url = _source(args.url)
    branch = _core().branch_ok(args.branch)
    worktree = Path(args.worktree).expanduser().resolve()
    home = Path.home().resolve()
    if not worktree.is_absolute() or worktree in (Path("/"), home, Path("/etc"), Path("/usr")):
        _fail("Worktree deve apontar para um diretorio especifico do aplicativo, nao raiz/home/sistema.")
    if worktree.exists() and (not worktree.is_dir() or any(worktree.iterdir())):
        _fail("Worktree existente nao esta vazia. Escolha outro caminho.")
    file, state, log = _paths(name)
    if file.exists():
        _fail(f"Agente '{name}' ja existe. Nao sera sobrescrito.")
    cfg = {"version": 2, "name": name, "mode": "outbound-https",
           "url": url, "branch": branch, "worktree": str(worktree),
           "action": {"enabled": False, "script": None, "timeout": 600}}
    _core().save_json(file, cfg)
    _log(log, f"Registrado {name}, branch {branch}. Actions desabilitadas.")
    print(f"Config: {file}\nOrigem: {url}\nWorktree: {worktree}")
    print("Para testar: ourgit agent check --name " + name)
    print("Para atualizar checkout: ourgit agent check --name " + name + " --apply")
    print(_source_credentials_warning())


def cmd_status(args):
    cfg, file, state, log = _load(args.name)
    report = _core().read_json(state, {})
    print(f"OurGit HTTPS Pull Agent '{cfg['name']}'")
    print(f"Origem: {cfg['url']} | branch: {cfg['branch']}")
    print(f"Deploy: {cfg['worktree']}")
    print("Action:", "HABILITADA" if cfg["action"]["enabled"] else "desabilitada")
    print("Ultimo SHA aplicado:", report.get("last_deployed_sha") or "(nenhum)")
    print("Ultimo checkout:", report.get("last_checkout_sha") or "(nenhum)")
    print("Ultima verificacao:", report.get("last_check_at") or "(nenhuma)")
    print("Ultimo erro:", report.get("last_error") or "(nenhum)")
    if Path(cfg["worktree"]).exists() and _is_git(Path(cfg["worktree"])):
        print("Worktree dirty:", len(_changes(Path(cfg["worktree"]))))
    print(f"Logs: {log}")


def cmd_log(args):
    _, _, _, path = _load(args.name)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    print("\n".join(lines[-args.lines:]) if lines else "Nenhum evento.")


def _sync(cfg, wanted, log):
    worktree = Path(cfg["worktree"])
    branch = cfg["branch"]
    if not worktree.exists():
        worktree.parent.mkdir(parents=True, exist_ok=True)
        # Clone cria apenas o checkout aprovado; sem executar codigo recebido.
        _git("clone", "--no-checkout", "--single-branch", "--branch", branch,
             "--origin", "origin", cfg["url"], str(worktree), timeout=360)
        _git("checkout", branch, cwd=worktree)
        actual = _head(worktree)
        _log(log, "Checkout inicial criado em " + str(worktree))
    else:
        _check_existing(worktree, cfg)
        _git("fetch", "--no-tags", "origin",
             f"+refs/heads/{branch}:refs/remotes/origin/{branch}", cwd=worktree)
        target = _git("rev-parse", f"refs/remotes/origin/{branch}", cwd=worktree).stdout.strip()
        local = _head(worktree)
        if not local:
            _fail("Checkout sem commit inicial, abortado.")
        if _git("merge-base", "--is-ancestor", local, target, cwd=worktree,
                check=False).returncode:
            _fail("Historicos divergentes: atualizacao automatica bloqueada.")
        if local != target:
            _git("merge", "--ff-only", f"refs/remotes/origin/{branch}", cwd=worktree)
        actual = _head(worktree)
    # A branch pode mudar durante o fetch; deploy do SHA verificado.
    if actual != wanted:
        _fail("Branch mudou durante o fetch; nenhuma action executada. Proxima consulta tentara novamente.")
    return actual


def _run_action(cfg, sha, log):
    action = cfg["action"]
    script = Path(action["script"]).expanduser().resolve()
    worktree = Path(cfg["worktree"]).resolve()
    if not script.is_file() or worktree == script or worktree in script.parents:
        _fail("Script de deploy ausente, invalido ou dentro do repositorio.")
    if script.stat().st_mode & stat.S_IWOTH:
        _fail("Script de deploy com permissao de escrita publica, rejeitado.")
    env = os.environ.copy()
    env.update({"OURGIT_WORKTREE": str(worktree), "OURGIT_BRANCH": cfg["branch"],
                "OURGIT_SHA": sha, "OURGIT_AGENT": cfg["name"]})
    proc = subprocess.run(["/bin/sh", str(script)], cwd=worktree, env=env, text=True,
                          capture_output=True, timeout=int(action["timeout"]))
    # Log local somente; cuidado para nao incluir secrets no stdout do script.
    if proc.stdout.strip():
        _log(log, "stdout: " + proc.stdout.strip()[-6000:])
    if proc.stderr.strip():
        _log(log, "stderr: " + proc.stderr.strip()[-6000:])
    if proc.returncode:
        _fail(f"Action falhou (exit={proc.returncode}); consulte log do agente.")


def cmd_check(args):
    if sys.platform != "linux":
        _fail("Pull Agent executa somente em Linux.")
    cfg, file, statefile, log = _load(args.name)
    import fcntl
    lockfile = file.with_suffix(".lock")
    with lockfile.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = _core().read_json(statefile, {})
        state["last_check_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            remote_sha = _remote_head(cfg)
            worktree = Path(cfg["worktree"])
            local = _head(worktree) if _is_git(worktree) else None
            state["last_remote_sha"] = remote_sha
            print(f"Origem HTTPS {cfg['branch']}: {remote_sha[:12]} | local: {(local or 'nao instalado')[:12]}")
            if not args.apply:
                print("Somente consulta. Use --apply para baixar; timer executa com --apply.")
                return
            actual = _sync(cfg, remote_sha, log)
            state["last_checkout_sha"] = actual
            if cfg["action"]["enabled"]:
                if state.get("last_deployed_sha") != actual:
                    _log(log, f"Iniciando action: {cfg['branch']} {actual[:12]}")
                    _run_action(cfg, actual, log)
                    state["last_deployed_sha"] = actual
                    _log(log, f"Deploy CONCLUIDO: {actual[:12]}")
                else:
                    print("Checkout e deploy ja atualizados.")
            else:
                print("Checkout atualizado; action continua desabilitada.")
            state["last_error"] = None
        except (OSError, subprocess.TimeoutExpired, _core().OurGitError) as exc:
            state["last_error"] = f"{type(exc).__name__}: {exc}"
            _log(log, "FALHA: " + state["last_error"])
            raise
        finally:
            _core().save_json(statefile, state)


def cmd_action(args):
    cfg, file, _, _ = _load(args.name)
    if args.mode == "status":
        print(json.dumps(cfg["action"], ensure_ascii=False, indent=2))
        return
    if args.mode == "disable":
        cfg["action"]["enabled"] = False
        _core().save_json(file, cfg)
        print("Action desabilitada; timer pode continuar atualizando checkout.")
        return
    script = Path(args.script).expanduser().resolve()
    worktree = Path(cfg["worktree"]).resolve()
    if not script.is_file() or worktree == script or worktree in script.parents:
        _fail("Script deve existir e ficar FORA do diretorio de deploy.")
    if script.stat().st_mode & stat.S_IWOTH:
        _fail("Script nao pode ser world-writable.")
    if not 1 <= args.timeout <= 3600:
        _fail("Timeout valido: 1 a 3600 segundos.")
    cfg["action"] = {"enabled": True, "script": str(script), "timeout": args.timeout}
    _core().save_json(file, cfg)
    print(f"Action habilitada em {args.name}: {script}")


def _unit(name, minutes):
    name = _name(name)
    if not 1 <= minutes <= 1440:
        _fail("Intervalo valido: 1 a 1440 minutos.")
    exe = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        argv = [str(exe), "agent", "check", "--name", name, "--apply"]
    else:
        argv = [str(exe), str(Path(__file__).resolve().parent / "ourgit.py"),
                "agent", "check", "--name", name, "--apply"]
    command = " ".join(shlex.quote(part) for part in argv)
    service = ("[Unit]\n"
               f"Description=OurGit HTTPS Pull Agent ({name})\n"
               "After=network-online.target\nWants=network-online.target\n\n"
               "[Service]\nType=oneshot\n"
               f"ExecStart={command}\n"
               "TimeoutStartSec=3700\n"
               "NoNewPrivileges=true\n"
               "PrivateTmp=true\n\n"
               "[Install]\nWantedBy=default.target\n")
    timer = ("[Unit]\n"
             f"Description=Verificar OurGit HTTPS - {name}\n\n"
             "[Timer]\nOnBootSec=2min\n"
             f"OnUnitInactiveSec={minutes}min\n"
             "AccuracySec=30s\n"
             f"Unit=ourgit-{name}.service\n\n"
             "[Install]\nWantedBy=timers.target\n")
    return service, timer


def cmd_timer(args):
    cfg, _, _, _ = _load(args.name)
    name = cfg["name"]
    directory = Path.home() / ".config" / "systemd" / "user"
    service, timer = _unit(name, args.minutes)
    if args.mode == "render":
        print("=== SERVICE ===\n" + service + "=== TIMER ===\n" + timer)
        return
    if not shutil_which("systemctl"):
        _fail("systemctl indisponivel. Requer systemd user timer.")
    servicepath = directory / f"ourgit-{name}.service"
    timerpath = directory / f"ourgit-{name}.timer"
    unit = timerpath.name
    if args.mode == "install":
        directory.mkdir(parents=True, exist_ok=True)
        if servicepath.exists() or timerpath.exists():
            _fail("Unit OurGit ja existe; remova pelo comando timer remove antes de alterar.")
        servicepath.write_text(service, encoding="utf-8")
        timerpath.write_text(timer, encoding="utf-8")
        _core().execute(["systemctl", "--user", "daemon-reload"])
        _core().execute(["systemctl", "--user", "enable", "--now", unit])
        print(f"Timer instalado: {unit} (a cada {args.minutes} min).")
        print("Para funcionar sem login interativo, administrador deve habilitar lingering:")
        print("sudo loginctl enable-linger \"$USER\"")
        return
    if args.mode == "remove":
        _core().execute(["systemctl", "--user", "disable", "--now", unit], check=False)
        if servicepath.exists(): servicepath.unlink()
        if timerpath.exists(): timerpath.unlink()
        _core().execute(["systemctl", "--user", "daemon-reload"])
        print("Timer removido; configuracao e worktree preservadas.")
        return
    result = _core().execute(["systemctl", "--user", "status", unit, "--no-pager", "-l"], check=False)
    print(result.stdout or result.stderr)


def shutil_which(name):
    import shutil
    return shutil.which(name)


def register(sub):
    agent = sub.add_parser("agent", help="Agente HTTPS Pull: VPS sem porta SSH de entrada")
    commands = agent.add_subparsers(dest="agentcommand", required=True)
    init = commands.add_parser("init", help="Registrar branch Git HTTPS e checkout na VPS")
    init.add_argument("--name", required=True)
    init.add_argument("--url", required=True)
    init.add_argument("--branch", required=True)
    init.add_argument("--worktree", required=True)
    init.set_defaults(func=cmd_init)
    for command, handler in [("check", cmd_check), ("status", cmd_status), ("log", cmd_log)]:
        item = commands.add_parser(command)
        item.add_argument("--name", required=True)
        if command == "check": item.add_argument("--apply", action="store_true")
        if command == "log": item.add_argument("--lines", type=int, default=40)
        item.set_defaults(func=handler)
    action = commands.add_parser("action")
    action.add_argument("mode", choices=["set", "disable", "status"])
    action.add_argument("--name", required=True)
    action.add_argument("--script", default="")
    action.add_argument("--timeout", type=int, default=600)
    action.set_defaults(func=cmd_action)
    timer = commands.add_parser("timer")
    timer.add_argument("mode", choices=["install", "remove", "status", "render"])
    timer.add_argument("--name", required=True)
    timer.add_argument("--minutes", type=int, default=5)
    timer.set_defaults(func=cmd_timer)
