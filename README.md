# OurGit

**Git + SSH + automação de deploy em VPS Linux**, com executáveis independentes para Windows e Linux.

Versão inicial **0.1.0**, licença **GPL-3.0**, repositório [llongaray/OurGit](https://github.com/llongaray/OurGit). O OurGit usa Git para versionamento e SSH para transportar commits; não substitui o protocolo Git.

## Instalação sem clonar repositório

Windows PowerShell x64 (requer Git for Windows):

~~~powershell
irm https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.ps1 | iex
ourgit --version
~~~

Linux x86_64 (requer Git, curl, tar, sha256sum e SSH):

~~~bash
curl -fsSL https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
ourgit --version
~~~

Os instaladores descarregam a última [GitHub Release](https://github.com/llongaray/OurGit/releases) e conferem SHA-256 antes de copiar o executável. **As URLs de binários só funcionarão após a primeira release ser publicada.** Revise scripts remotos antes de executá-los em máquinas corporativas.

## 1. Registrar código local

~~~powershell
cd C:\Users\Usuario\github\Projeto
ourgit init
ourgit status
ourgit add --all
ourgit commit -m "feat: exemplo de atualizacao"
~~~

A configuração local fica em `.git/ourgit.json` e não é versionada. Em uma pasta ainda sem Git, `ourgit init --git-init` cria o repositório; sem essa flag não altera a estrutura Git.

## 2. Vincular a VPS (SSH pública, LAN ou VPN)

~~~powershell
ourgit connect --host 10.20.0.51 --port 22 --user deploy --repo /home/deploy/git/projeto-hml.git --worktree /home/deploy/apps/projeto-hml --branch hml --name vps-hml --install-server
~~~

Esse comando registra na VPS um repositório bare e um caminho separado de deploy, depois adiciona um remote SSH ao Git local. A flag `--install-server` instala o agente Linux via a última release; retire-a se o agente já estiver instalado. Para chave SSH específica use `--identity CAMINHO_DA_CHAVE`. O acesso requer chave válida e permissão de escrita nos diretórios; não é necessário abrir portas além da SSH. O SSH utiliza verificação de host `accept-new`; em ambiente empresarial verifique as host keys previamente.

**O deploy nasce desabilitado por padrão.** Primeiro push transmite código, mas não ativa produção.

## 3. Comparar commits e sincronizar

~~~bash
ourgit remote list
ourgit remote default vps-hml
ourgit status --fetch
ourgit push --dry-run
ourgit push
ourgit pull
ourgit sync
ourgit sync --apply
~~~

Comandos `status --fetch`, `push`, `pull` e `sync` aceitam `--remote NOME` para projetos com várias VPS ou repositórios. `push` envia commits via Git sem `--force`; `pull` aplica apenas `--ff-only`; `sync` mostra plano e só altera o Git quando recebe `--apply`. Históricos divergentes exigem intervenção humana. Arquivos não commitados não são enviados. Para outro remoto Git genérico há `ourgit remote add --name vps --url ssh://usuario@host:22/caminho/repo.git --branch hml`.

## 4. Actions automáticas na VPS

O agente cria um hook **post-receive** vinculado a uma única branch. A ação é configurada explicitamente com um script controlado pelo administrador **fora do repositório de deploy**:

~~~bash
# Na VPS, usuario deploy (sem root):
mkdir -p ~/actions
# Crie e revise ~/actions/projeto-hml.sh; exemplo em examples/deploy-docker.sh
~/.local/bin/ourgit server action set --repo /home/deploy/git/projeto-hml.git --script /home/deploy/actions/projeto-hml.sh --timeout 600
~/.local/bin/ourgit server action status --repo /home/deploy/git/projeto-hml.git
~/.local/bin/ourgit server log --repo /home/deploy/git/projeto-hml.git
~~~

Após receber push da branch configurada, o agente bloqueia concorrência, cria/atualiza um checkout separado por **fast-forward**, exige worktree limpa, executa o script aprovado e grava o resultado em `ourgit-actions.log`. Os comandos do script têm as permissões do usuário SSH. **Um push aceito não garante deploy bem-sucedido**: verifique os logs.

Consultar configuração de action pela máquina de desenvolvimento: `ourgit action-status --remote vps-hml`. Para comparar commits do bare e arquivos não commitados do checkout remoto, execute `ourgit vps-status --remote vps-hml`.

Se houver modificações na VPS, faça `git add`, `git commit` e `git push origin hml` no checkout do servidor; no PC use `ourgit pull`. A worktree suja bloqueia deploy para não descartar alterações. Não há rollback automático nesta versão; use backups e healthchecks do serviço.

## Segurança

- Chaves privadas e senhas **não são transferidas** para a VPS pelo OurGit; parâmetros ficam em `.git/ourgit.json`.
- Apenas SSH existente é utilizado. Não habilite SSH root/senha nem abra HTTP para instalar.
- Git bare recusa `non-fast-forward` e exclusões de branch; comandos OurGit não usam force push.
- Actions nunca são ativadas por padrão; o script aprovado deve estar fora da worktree.
- Binários Windows/Linux são builds PyInstaller x86_64 feitos pelo GitHub Actions. Git e SSH precisam estar disponíveis no PATH.
- Downloads possuem SHA-256 e TLS, mas ainda não possuem assinatura independente ou attestation de procedência.
- Esta versão suporta um script por repo/branch e exige permissões do administrador para configurar e acionar deploy.

## Testes e compilação

~~~bash
python ourgit.py --version
python -m unittest discover -s tests -v
~~~

Em commits/PRs, `.github/workflows/ci.yml` testa Windows e Linux. A primeira execução bem-sucedida da workflow `.github/workflows/release.yml` na branch `main` publica automaticamente a release `v0.1.0`; futuras versões são lançadas criando tags `vX.Y.Z`. Os pacotes incluem `ourgit.exe`, `ourgit`, ZIP/TAR.GZ e `checksums.txt`.

## Roadmap

Workflow declarativo YAML com múltiplos jobs, aprovação de deploy, logs em streaming, UI TUI mais rica, integridade por assinatura e rollback com healthchecks.