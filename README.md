# OurGit — Git remoto e deploy de VPS pela LAN

[![CI Windows/Linux](https://github.com/llongaray/OurGit/actions/workflows/ci.yml/badge.svg)](https://github.com/llongaray/OurGit/actions/workflows/ci.yml)
[![Releases](https://img.shields.io/github/v/release/llongaray/OurGit?label=vers%C3%A3o)](https://github.com/llongaray/OurGit/releases)
[![Windows](https://img.shields.io/badge/Windows-x64-0078D4)](https://github.com/llongaray/OurGit/releases)
[![Linux](https://img.shields.io/badge/Linux-x86__64-FCC624)](https://github.com/llongaray/OurGit/releases)
[![License: GPL-3.0](https://img.shields.io/badge/licen%C3%A7a-GPL--3.0-blue)](LICENSE)

**OurGit** é uma CLI para controlar commits, branches, sincronização Git e deploy de aplicações entre o computador do desenvolvedor e servidores Linux. O objetivo é proporcionar um fluxo previsível, auditável e simples, incluindo VPS cuja **porta SSH não é acessível pelo IP público**, mas funciona normalmente pelo **IP privado da LAN/VPN**.

> **Regra principal:** a **instalação** usa HTTPS (porta **443**, somente saída); a **comunicação do código** entre PC e VPS usa **Git sobre SSH pelo IP LAN e pela porta SSH privada configurada**. Essas são conexões distintas. **Não é necessário expor SSH à Internet, hospedar painel web ou abrir porta HTTP de entrada.**

**Idioma:** Português (Brasil) primeiro; [English below](#english-documentation).

## Índice — PT-BR

1. [Arquitetura e fluxo de rede](#arquitetura-e-fluxo-de-rede)
2. [Funcionalidades e limites](#funcionalidades-e-limites)
3. [Requisitos](#requisitos)
4. [Instalação pela Internet (HTTPS)](#instalação-pela-internet-https)
5. [Preparar SSH privado na LAN](#preparar-ssh-privado-na-lan)
6. [Registrar e vincular PC e VPS](#registrar-e-vincular-pc-e-vps)
7. [Comparar arquivos e commits](#comparar-arquivos-e-commits)
8. [Enviar, receber e sincronizar](#enviar-receber-e-sincronizar)
9. [Automatizar o deploy por branch](#automatizar-o-deploy-por-branch)
10. [Como o OurGit funciona internamente](#como-o-ourgit-funciona-internamente)
11. [Modo HTTPS Pull Agent (alternativo)](#modo-https-pull-agent-alternativo)
12. [Segurança, solução de problemas e referência](#segurança-solução-de-problemas-e-referência)
13. [Desenvolvimento, builds e licença](#desenvolvimento-builds-e-licença)

---

## Arquitetura e fluxo de rede

```text
                            INTERNET (HTTPS 443)
                        GitHub Releases / CDN
                           /              \
                 Download HTTPS      Download HTTPS
                        /                  \
            PC desenvolvedor          VPS Linux Server
            Windows / Linux           IP LAN 192.168.10.20
            +---------------+         +-----------------------------+
            | ourgit        |         | ourgit                      |
            | Projeto/.git  |         | git bare: projeto-hml.git   |
            | branch hml    |         | checkout: projeto-hml       |
            +-------+-------+         | post-receive + script deploy|
                    |                 +--------------+--------------+
                    |                                ^
                    +----- Git via SSH LAN:22 --------+
                          (ou VPN / porta definida)
                          SEM SSH público obrigatório
```

| Necessidade | Origem → destino | Protocolo | Porta | Recebe conexões externas? |
|---|---|---|---|---|
| Instalar no PC | PC → GitHub Releases | HTTPS | 443 saída | Não |
| Instalar na VPS | Terminal da VPS → GitHub Releases | HTTPS | 443 saída | Não |
| Enviar commits | PC → IP LAN/VPN da VPS | SSH + Git | 22 ou porta interna | **Somente LAN/VPN** |
| Receber commits | PC → IP LAN/VPN da VPS | SSH + Git | 22 ou porta interna | **Somente LAN/VPN** |
| Deploy após push | Hook local da VPS → checkout/script | Processo local | Nenhuma nova porta | Não |
| GitHub corporativo (opcional) | PC → GitHub | HTTPS ou SSH existentes | Conforme remote | Não há dependência do GitHub para o push direto à VPS |

**Exemplo concreto:** a VPS possui um IP público, mas a porta 22 é bloqueada no firewall externo. Se PC e VPS compartilham a LAN ou VPN e `192.168.10.20:22` é alcançável, o OurGit funciona normalmente. Use esse **IP interno** em `--host`, não o IP público. Se a porta SSH privada for 2222, configure `--port 2222`.

**Importante:** o download HTTPS não cria uma sessão administrativa remota. O primeiro comando de instalação na VPS é executado em seu terminal legítimo (console do provedor, SSH pela LAN/VPN, console corporativo ou outro acesso existente).

## Funcionalidades e limites

| Funcionalidade | Comando | Status |
|---|---|---|
| Registrar um repositório existente | `ourgit init` | Disponível |
| Inicializar Git explicitamente | `ourgit init --git-init` | Disponível |
| Configurar diversos destinos | `ourgit remote add` | Disponível |
| Vincular servidor Linux na LAN/VPN | `ourgit connect` | Disponível |
| Examinar arquivos modificados/não rastreados | `ourgit status` | Disponível |
| Comparar commits a enviar/receber | `ourgit status --fetch` | Disponível |
| Preparar arquivos e criar commits | `ourgit add` / `ourgit commit` | Disponível |
| Enviar commits de forma não destrutiva | `ourgit push` | Disponível |
| Receber apenas fast-forward | `ourgit pull` | Disponível |
| Prévia e aplicação da sincronização | `ourgit sync` / `ourgit sync --apply` | Disponível |
| Consultar branch e checkout da VPS por SSH | `ourgit vps-status` | Disponível |
| Executar deploy após push da branch autorizada | Git `post-receive` | Disponível |
| Logs de deploy / status de action | `ourgit server log` / `ourgit action-status` | Disponível |
| Workflows YAML com diversos jobs, aprovação e rollback automático | — | **Ainda não implementado** |
| Interface gráfica web / sincronização em tempo real | — | **Ainda não implementado** |

O OurGit **não substitui o Git ou o GitHub**: usa o protocolo e as regras reais do Git. O status mostra as mudanças da **worktree local** e a **quantidade de commits divergentes**. Na VPS, `vps-status` mostra a diferença entre o bare e o checkout, inclusive alterações não commitadas no servidor. A comparação exata por arquivo entre duas máquinas pode ser feita com comandos Git (`git diff`); não existe ainda um painel de diferenças remotas por linha.

## Requisitos

| Componente | PC Windows x64 | VPS Linux x86_64 |
|---|---|---|
| Sistema | Windows 10/11 ou Server compatível | Distribuição Linux x86_64, recomendável Ubuntu/Debian |
| OurGit | Executável `ourgit.exe` | Executável `ourgit` |
| Git | **Git for Windows** no PATH | `git` instalado |
| OpenSSH | Cliente SSH no PATH | Servidor SSH ativo **na LAN**, usuário com acesso por chave |
| Rede de instalação | Acesso HTTPS a GitHub | HTTPS de saída a GitHub |
| Rede de sincronização | Acesso ao **IP LAN/VPN da VPS** | SSH recebendo conexões **da LAN/VPN** |
| Permissões | Escrita no repositório local | Escrita no bare e no checkout do usuário de deploy |
| Para action Docker | — | Docker e Compose instalados e permissão previamente autorizada |
| Para desenvolvimento | Python 3.10+ | Python 3.10+ (opcional) |

Os executáveis de Release são autocontidos quanto ao Python, mas **Git e SSH continuam sendo dependências externas**. A publicação inicial suporta x64; outras arquiteturas não são garantidas.

### Instalar as dependências do Linux

```bash
# Ubuntu/Debian: executado na VPS, conforme política da organização
sudo apt-get update
sudo apt-get install -y git curl ca-certificates openssh-client

git --version
curl --version
```

Não é necessário instalar `openssh-server` se a VPS já dispõe de SSH pela LAN. Não modifique `sshd_config` nem abra a porta pública apenas para o OurGit.

## Instalação pela Internet (HTTPS)

Instale o OurGit **separadamente no PC e no servidor**. Não é preciso clonar o repositório OurGit.

### Windows — PowerShell (máquina do desenvolvedor)

```powershell
# Requer Git for Windows.
irm https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.ps1 | iex
ourgit --version
ourgit --help
```

O instalador baixa a última Release por **HTTPS**, confere o SHA-256, extrai o executável para `%LOCALAPPDATA%\Programs\OurGit\ourgit.exe` e registra o diretório no PATH do usuário. Se o PATH não aparecer imediatamente, abra outro PowerShell.

Para auditar antes de executar:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.ps1 -OutFile "$env:TEMP\install-ourgit.ps1"
notepad "$env:TEMP\install-ourgit.ps1"
Get-Content -LiteralPath "$env:TEMP\install-ourgit.ps1" -Raw | Invoke-Expression
```

> **PowerShell com Execution Policy restrita:** o comando direto `& ".\\install-ourgit.ps1"` pode gerar `PSSecurityException` mesmo após uma instalação válida. Depois de revisar e aprovar o conteúdo do arquivo, a execução acima usa `Invoke-Expression` na sessão atual sem alterar `Set-ExecutionPolicy` no computador. Se a política da empresa proibir essa execução, solicite liberação ao TI. Confira com `Get-ExecutionPolicy -List`. O OurGit já instalado não precisa ser reinstalado.

### Linux — Bash (terminal da VPS)

```bash
# Executar como o USUÁRIO DE DEPLOY (não como root).
curl -fsSL https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.sh | sh

export PATH="$HOME/.local/bin:$PATH"
ourgit --version
ourgit --help
```

O instalador utiliza **HTTPS de saída** e instala `$HOME/.local/bin/ourgit`, sem clonar o repositório ou exigir privilégios de root. Verifica o SHA-256 do arquivo de Release.

Para revisar o script antes:

```bash
curl -fsSL https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.sh -o /tmp/install-ourgit.sh
less /tmp/install-ourgit.sh
sh /tmp/install-ourgit.sh
```

**Releases e downloads:** [última versão](https://github.com/llongaray/OurGit/releases/latest) · [Windows ZIP](https://github.com/llongaray/OurGit/releases/latest/download/ourgit-windows-x86_64.zip) · [Linux TAR.GZ](https://github.com/llongaray/OurGit/releases/latest/download/ourgit-linux-x86_64.tar.gz) · [checksums.txt](https://github.com/llongaray/OurGit/releases/latest/download/checksums.txt).

O checksum ajuda a verificar integridade, mas **não equivale a assinatura criptográfica independente**. Para produção corporativa, fixe uma versão e valide sua proveniência antes de executar qualquer instalador externo.

## Compatibilidade Windows e assinatura empresarial (v0.3.1)

O Windows pode impedir a execução do `ourgit.exe` quando uma política **App Control for Business / Code Integrity (evento 3077)** exige código autorizado. Isso **não é um erro de Git nem da porta SSH**. Um executável PyInstaller sem assinatura Authenticode pode ser bloqueado mesmo após o download via HTTPS e a conferência do SHA-256. Uma assinatura válida também **não garante** autorização: a regra aplicada pela organização precisa aceitar o certificado/publicador ou hash específico.

**Instalação com proteção contra atualizações bloqueadas:** o `install/install.ps1` valida ZIP/SHA-256, consulta o estado da assinatura Authenticode, faz cópia de segurança do `ourgit.exe` atual e testa a nova versão no caminho final. Se o Windows bloquear a execução, registra a ocorrência de Code Integrity quando disponível e **restaura o executável anterior**. O script **não desativa** Defender, App Control, AppLocker ou Execution Policy. Se não existir instalação anterior, remove o novo arquivo que falhou.

No computador Windows corporativo, para solicitar à TI uma autorização segura:

~~~powershell
$exe = "$env:LOCALAPPDATA\Programs\OurGit\ourgit.exe"
Get-AuthenticodeSignature -LiteralPath $exe | Format-List Status, SignerCertificate
Get-FileHash -LiteralPath $exe -Algorithm SHA256
Get-WinEvent -FilterHashtable @{ LogName = "Microsoft-Windows-CodeIntegrity/Operational"; StartTime = (Get-Date).AddHours(-2); Id = 3077 } -ErrorAction SilentlyContinue | Where-Object { $_.Message -match "ourgit.exe" } | Select-Object -First 5 TimeCreated, Id, Message | Format-List
~~~

**Opções de instalação para ambientes com requisitos de assinatura:**

~~~powershell
# Exigir assinatura Authenticode confiável pela máquina atual
$env:OURGIT_REQUIRE_SIGNED = "1"
irm https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.ps1 | iex

# Opcional: exigir também o thumbprint do certificado aprovado pela TI
$env:OURGIT_TRUSTED_SIGNER_THUMBPRINT = "THUMBPRINT_APROVADO_PELA_TI"
~~~

Não configure um thumbprint fictício: obtenha-o do certificado real, devidamente homologado. Se a Release for não assinada, `OURGIT_REQUIRE_SIGNED=1` interrompe a instalação sem substituir a versão anterior.

**Assinatura no GitHub Actions:** `scripts/sign_windows.ps1` pode aplicar Authenticode utilizando um certificado Code Signing aprovado pela organização (PFX) e carimbo de tempo RFC 3161. Configure um **GitHub Environment protegido** chamado `ourgit-code-signing`, restrinja branches/tags autorizados e habilite aprovação dos responsáveis. Nesse Environment, disponibilize os secrets `OURGIT_CODESIGN_PFX_BASE64` (PFX codificado em base64) e `OURGIT_CODESIGN_PFX_PASSWORD`, exclusivamente se a política corporativa permitir hospedar a chave dessa forma. Considere HSM/serviço de assinatura remota quando o certificado não puder ser exportado. Para bloquear publicação não assinada, configure a variável `OURGIT_REQUIRE_SIGNED_RELEASE=1`.

A Release inclui o relatório `windows-signature.json`, com `signing_mode`, publicador, thumbprint e hash do executável. **Sem certificado aprovado configurado, o pipeline distribui um executável não assinado**, explicitamente identificado; a distribuição ainda poderá ser bloqueada no seu Windows. A autorização final depende da equipe que controla a política Code Integrity.

---

## Preparar SSH privado na LAN

A instalação via HTTPS e a sincronização por SSH são independentes.

### Passo 1 — conferir conectividade LAN no Windows

```powershell
# SUBSTITUA 192.168.10.20 pelo IP INTERNO da VPS
Test-NetConnection -ComputerName 192.168.10.20 -Port 22
```

Procure `TcpTestSucceeded : True`. Se false, verifique rota/VPN, firewall interno, porta configurada no `sshd` e se o servidor está ativo. **Não tente corrigir expondo a porta 22 pelo IP público.**

### Passo 2 — gerar chave SSH no PC, se necessário

```powershell
ssh-keygen -t ed25519 -C "ourgit-pc-desenvolvimento"

# Exiba APENAS a chave pública:
Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
```

No console administrativo da VPS, adicione **somente a chave pública autorizada** ao `~/.ssh/authorized_keys` do usuário `deploy`. Ajuste permissões:

```bash
# VPS Linux, logado como usuario deploy
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
# Acrescente a chave PUBLICA do desenvolvedor, apos conferir sua origem.
```

Nunca copie `id_ed25519` (chave **privada**) para a VPS, GitHub ou README.

### Passo 3 — testar autenticação

```powershell
ssh -p 22 deploy@192.168.10.20
```

O OurGit executa SSH em modo não interativo. Portanto, a autenticação por chave precisa funcionar antes de `connect`. Na primeira conexão, valide a impressão digital da host key usando uma fonte administrativa confiável. Uma conexão VPN entre redes distintas é igualmente suportada, desde que haja rota ao IP privado e liberação do firewall LAN.

## Registrar e vincular PC e VPS

### 1. Registrar o projeto local no PC

```powershell
cd C:\Users\Usuario\github\MeuProjeto

ourgit init
ourgit status
```

Se ainda não for um projeto Git, use `ourgit init --git-init` para **criar Git explicitamente**.

### 2. Instalar o agente na VPS por HTTPS

Execute `curl ... | sh` na VPS conforme a seção de instalação e teste:

```bash
$HOME/.local/bin/ourgit --version
git --version
```

O usuário remoto precisa conseguir criar diretórios em sua própria home. Para este exemplo, usaremos caminhos sob `/home/deploy`, **não** alteraremos o diretório do SIGA ou serviços existentes.

### 3. Vincular pelo IP LAN e a porta SSH privada

No **PC**:

```powershell
ourgit connect --host 192.168.10.20 --port 22 --user deploy --repo /home/deploy/repos/meuprojeto-hml.git --worktree /home/deploy/apps/meuprojeto-hml --branch hml --name vps-hml
```

Significado dos argumentos:

| Opção | Finalidade | Exemplo |
|---|---|---|
| `--host` | **IP LAN/VPN** alcançável pelo PC | `192.168.10.20` |
| `--port` | Porta SSH do servidor **na LAN** | `22` ou `2222` |
| `--user` | Usuário Linux autorizado | `deploy` |
| `--repo` | Caminho absoluto do **Git bare** na VPS | `/home/deploy/repos/meuprojeto-hml.git` |
| `--worktree` | Diretório diferente do bare para o checkout/deploy | `/home/deploy/apps/meuprojeto-hml` |
| `--branch` | Branch associada ao destino | `hml` |
| `--name` | Apelido do remote Git local | `vps-hml` |
| `--identity` | Caminho opcional da chave privada **no PC** | `C:\Users\Usuario\.ssh\id_ed25519` |
| `--install-server` | Opcional: instalar agente na VPS **através da conexão SSH LAN** | Não necessário se já instalou por HTTPS no terminal |

`connect` chama o agente já instalado na VPS via SSH, inicializa um repositório bare, cria o hook de recebimento e cadastra o remote local. **Não faz deploy imediatamente**. O checkout será criado ao habilitar e executar uma action.

**Não** utilize `--install-server` para o fluxo recomendado de instalação por terminal HTTPS; este parâmetro existe para conveniência quando o servidor já está acessível por SSH.

### 4. Conferir o vínculo

```powershell
ourgit remote list
git remote -v
ourgit remote default vps-hml

ourgit status --remote vps-hml
ourgit vps-status --remote vps-hml
```

Pode haver vários remotes no mesmo projeto, como `origin` (GitHub corporativo), `pessoal` e `vps-hml`. A configuração do OurGit **não substitui, renomeia nem força** outros remotes. Cada destino possui sua própria branch configurada.

## Comparar arquivos e commits

Após pelo menos um push para a VPS:

```powershell
# Lê o Git local e usa "git fetch" pela conexão SSH LAN
ourgit status --remote vps-hml --fetch

# Arquivos locais modificados, staged e não rastreados
git status --short

# Diferenças locais por arquivo e linha (sem push)
git diff
git diff --cached

# Commits a enviar para a VPS
git log --oneline vps-hml/hml..HEAD

# Commits existentes na VPS que faltam no PC
git log --oneline HEAD..vps-hml/hml

# Comparação resumida de arquivos entre os commits
git diff --stat vps-hml/hml HEAD

# Checkout efetivamente presente no servidor
ourgit vps-status --remote vps-hml
```

`status --fetch` informa `PUSH pendente`, `PULL pendente` e as modificações locais. Se houver commits em ambas as direções, o OurGit **bloqueia a sincronização automática**, preservando ambos os históricos.

## Enviar, receber e sincronizar

### Commit e primeiro push para VPS

```powershell
ourgit add --all
ourgit commit -m "feat: publicar primeira homologacao"

ourgit push --remote vps-hml --dry-run
ourgit push --remote vps-hml
```

O Git envia apenas os arquivos presentes nos commits. Arquivos não rastreados e modificações não commitadas **não são enviados**. Na VPS, o hook registra a atualização da branch, mas a action de deploy continua desabilitada até a configuração explícita.

### Pull VPS → PC

```powershell
ourgit pull --remote vps-hml
```

O OurGit realiza `fetch` e `merge --ff-only`. Se o diretório local estiver sujo ou se os históricos divergirem, o comando falha sem reset/force. Faça commit, stash ou uma resolução Git manual.

### Modo de sincronização assistida

```powershell
ourgit sync --remote vps-hml
ourgit sync --remote vps-hml --apply
```

Sem `--apply`, há somente análise. Com `--apply`, o programa decide entre push/pull **quando o histórico permite uma operação segura**; em divergência não executa merge automático.

### Alterações criadas diretamente na VPS

O diretório de deploy é um checkout normal. Se for preciso editar algo na VPS, registre essas alterações no Git **antes** de tentar sincronizar:

```bash
cd /home/deploy/apps/meuprojeto-hml
git status
git add -- arquivo
git commit -m "fix: ajuste realizado no servidor"
git push origin hml
```

No PC, execute `ourgit pull --remote vps-hml`. Alterações não commitadas na VPS bloqueiam a atualização do checkout e impedem seu descarte acidental.

## Automatizar o deploy por branch

O `ourgit connect` instala um hook Git `post-receive` no **bare** da VPS. Quando um push válido atualiza a branch configurada, o hook pode atualizar a worktree e executar **um script aprovado pelo administrador**. O sistema **não** usa webhook HTTP, scheduler externo ou porta pública.

### 1. Criar um script controlado fora do código da aplicação

Na VPS:

```bash
mkdir -p /home/deploy/actions

cat > /home/deploy/actions/meuprojeto-hml.sh <<'SH'
#!/bin/sh
set -eu
: "$OURGIT_WORKTREE"
: "$OURGIT_SHA"
cd "$OURGIT_WORKTREE"

# Exemplo: customize para o projeto e aprove o acesso ao Docker.
docker compose -p meuprojeto-hml -f compose.yaml up -d --build
docker compose -p meuprojeto-hml -f compose.yaml ps
SH

chmod 700 /home/deploy/actions/meuprojeto-hml.sh
```

**Antes de habilitar:** revise os comandos, verifique permissões do usuário de deploy, limites de memória/CPU e isolamento do Docker. O exemplo não deve ser aplicado ao SIGA ou produção sem análise de impacto.

### 2. Habilitar a action **explicitamente** na VPS

```bash
$HOME/.local/bin/ourgit server action set --repo /home/deploy/repos/meuprojeto-hml.git --script /home/deploy/actions/meuprojeto-hml.sh --timeout 600
$HOME/.local/bin/ourgit server action status --repo /home/deploy/repos/meuprojeto-hml.git
```

Após essa configuração, cada **novo push** na branch `hml` ativa o fluxo. Para executar a branch atual manualmente:

```bash
$HOME/.local/bin/ourgit server deploy --repo /home/deploy/repos/meuprojeto-hml.git
```

### 3. Consultar o resultado e desabilitar

```bash
$HOME/.local/bin/ourgit server log --repo /home/deploy/repos/meuprojeto-hml.git --lines 40
$HOME/.local/bin/ourgit server action disable --repo /home/deploy/repos/meuprojeto-hml.git
```

No PC:

```powershell
ourgit action-status --remote vps-hml
ourgit vps-status --remote vps-hml
```

**Push aceito pelo Git não significa deploy concluído.** O `post-receive` executa após o Git aceitar os commits, e a action pode falhar posteriormente. Consulte logs, status do Docker e healthcheck da aplicação. Falhas **não** realizam rollback automático.

### Fluxo técnico do hook

1. O Git recebe e valida os commits na referência `refs/heads/hml`.
2. O hook verifica se a action foi habilitada e se o SHA ainda é o atual.
3. Um arquivo de lock evita dois deploys simultâneos.
4. O checkout é criado ou atualizado por `fast-forward`, sem `reset --hard`.
5. O agente exige branch correta e worktree limpa.
6. Executa o script externo com `OURGIT_BRANCH`, `OURGIT_SHA` e `OURGIT_WORKTREE`.
7. Registra resultados no arquivo `ourgit-actions.log` dentro do bare.

Esta é uma implementação inicial de **action por branch**, não uma plataforma com runners, workflows YAML, múltiplas etapas, aprovação por ambiente ou rollback transacional.

## Como o OurGit funciona internamente

- **Transporte:** os comandos de envio e recebimento usam `git fetch`/`git push` via URL `ssh://usuario@IP_LAN:PORTA/repositorio.git`. A chave SSH privada permanece na máquina cliente.
- **Identificação de mudanças:** `git status --porcelain` identifica a worktree, e `git rev-list --left-right --count` calcula os commits à frente/atrás do destino.
- **Configuração local:** `.git/ourgit.json` associa apelidos de remotes, branches e parâmetros SSH sem versionar esses ajustes na aplicação.
- **Repositório remoto:** um Git **bare** guarda objetos, refs e o hook. Um **checkout separado** guarda os arquivos executados na VPS.
- **Segurança Git:** histórico remoto não é sobrescrito via `force push`; branches do bare são protegidas contra non-fast-forward e exclusões.
- **Action:** script externo, opt-in, rodando como o usuário Linux que recebeu os commits, nunca como root por padrão.
- **Instaladores:** distribuição por HTTPS de assets compilados em GitHub Actions, verificação SHA-256 e instalação no diretório do usuário.
- **Logs:** logs locais do hook e estado verificável por SSH. Não existe painel de gestão com exposição HTTP.

### Estrutura principal do repositório

```text
OurGit/
├── ourgit.py                   # CLI, Git/SSH e servidor post-receive
├── ourgit_pull_agent.py        # Modo HTTPS de saida, opcional
├── install/
│   ├── install.ps1             # Instalador Windows por HTTPS
│   └── install.sh              # Instalador Linux por HTTPS
├── .github/workflows/
│   ├── ci.yml                  # Testes Windows e Linux
│   └── release.yml             # Build e assets dos executaveis
├── scripts/package_release.py # ZIP Windows e TAR.GZ Linux
├── examples/deploy-docker.sh  # Modelo de action
├── tests/                      # Testes de Git local, SSH simulado e agent
├── README.md                   # PT-BR seguido por English
└── LICENSE                     # GPL-3.0
```

## Modo HTTPS Pull Agent (alternativo)

**Não é necessário para o seu cenário LAN.** Existe como alternativa para servidores que não aceitam SSH **nem pela LAN/VPN**: a própria VPS consulta uma origem Git HTTPS e atualiza seu checkout via `systemd --user`. Não recebe push do PC e não fornece comparação remota SSH.

Exemplo no **terminal da VPS**:

```bash
ourgit agent init --name meuapp-hml --url https://github.com/ORGANIZACAO/REPOSITORIO.git --branch hml --worktree /home/deploy/apps/meuapp-hml
ourgit agent check --name meuapp-hml
ourgit agent check --name meuapp-hml --apply
ourgit agent status --name meuapp-hml
ourgit agent timer render --name meuapp-hml --minutes 5
```

A action também nasce desabilitada e o timer só é instalado mediante comando explícito. Em repositórios privados, configure credenciais HTTPS de **somente leitura** no ambiente seguro do usuário, sem inserir tokens em URLs. Esse mecanismo **não é** o padrão quando o SSH LAN está disponível.

## Segurança, solução de problemas e referência

### Boas práticas obrigatórias

- Restrinja o SSH no firewall **à LAN/VPN**, usando usuário de deploy dedicado e autenticação por chave.
- Não habilite login root, senha SSH ou entrada pela porta pública apenas para usar OurGit.
- Verifique fingerprints de host keys antes do primeiro acesso; `accept-new` não substitui verificação fora da banda.
- Proteja os diretórios bare, checkout e scripts externos; não conceda escrita a usuários não autorizados.
- Não commit senhas, `.env`, tokens, chaves privadas ou arquivos operacionais da VPS.
- A execução de scripts de deploy é equivalente a executar comandos de shell como o usuário SSH. Audite cada script.
- Use branches específicas de homologação e produção, limites de recursos e rollback/backup próprios da aplicação.
- O OurGit não valida automaticamente CVEs ou assinaturas independentes dos artefatos; mantenha Git, OpenSSH e sistema atualizados.

### Problemas comuns

| Sintoma | Causa provável | Diagnóstico / ação |
|---|---|---|
| SSH público fechado, mas LAN funcional | Comportamento esperado | Use `--host IP_LAN`, não IP público |
| `Test-NetConnection` retorna falso | Firewall LAN, rota ou VPN | Verifique IP/porta/rota; não abra a porta pública |
| `Permission denied (publickey)` | Chave pública não autorizada | Revise `authorized_keys` e usuário SSH |
| `Host key verification failed` | Host key não verificada ou alterada | Confirme fingerprint com administrador antes de alterar `known_hosts` |
| `Git not found` | Git fora do PATH | Instale Git e abra novo terminal |
| `ourgit: command not found` | PATH ainda não atualizado | Linux: `export PATH="$HOME/.local/bin:$PATH"`; Windows: novo PowerShell |
| `Push pendente 0 / Pull pendente 0` | Branches sincronizadas | Nenhuma alteração de commits; verifique worktree local |
| Branch remota inexistente | Primeiro push ainda não feito | Revise `--branch` e execute o primeiro push |
| Históricos divergentes | Commits diferentes em ambas as pontas | Resolva manualmente no Git, não faça `--force` |
| Worktree VPS suja | Alterações feitas diretamente no servidor | Faça commit/stash ou reconcilie manualmente antes do deploy |
| Push funcionou, mas app não atualizou | Action desabilitada ou falha | Veja `server action status` e `server log` |
| Falha no download HTTPS da VPS | Sem saída para GitHub/Release | Revise DNS, proxy, firewall de saída e certificados |
| Erro de permissão no Docker | Usuário sem autorização | Solicite aprovação/ajuste de permissão; não execute como root indiscriminadamente |
| Porta LAN 22 não usada | SSH escuta em porta diferente | `ourgit connect --port PORTA_INTERNA` |

### Referência resumida de comandos

| Comando | Efeito |
|---|---|
| `ourgit --help` | Lista comandos |
| `ourgit --version` | Versão |
| `ourgit init [--git-init] [--path PASTA]` | Registra projeto |
| `ourgit remote add --name N --url URL --branch B` | Cadastra remote |
| `ourgit remote list` | Lista remotes |
| `ourgit remote default N` | Define destino padrão |
| `ourgit connect --host IP --port PORTA --user USER --repo BARE --worktree CHECKOUT --branch B --name N` | Vincula VPS via SSH LAN |
| `ourgit status [--fetch] [--remote N]` | Status local/remoto |
| `ourgit add --all` | Prepara mudanças |
| `ourgit commit -m "mensagem"` | Cria commit |
| `ourgit push [--dry-run] [--remote N]` | Envia commits |
| `ourgit pull [--remote N]` | Baixa fast-forward |
| `ourgit sync [--apply] [--remote N]` | Plano ou sincronização |
| `ourgit vps-status --remote N` | Compara bare e checkout por SSH |
| `ourgit action-status --remote N` | Action remota |
| `ourgit server init / action / log / deploy` | Operação na VPS Linux |
| `ourgit agent init / check / timer` | Pull HTTPS alternativo, sem SSH de entrada |

## Histórico de commits, auditoria de máquinas e recuperação (v0.3.0)

**Não é preciso um servidor dedicado para guardar versões anteriores:** o próprio **Git armazena commits, árvores e conteúdos** no repositório local (`.git`), no bare Git existente de uma VPS ou em qualquer remoto Git convencional. O OurGit v0.3.0 adiciona uma CLI de leitura e recuperação segura sobre esses recursos.

> A recuperação depende de os commits ainda existirem em **alguma cópia acessível do repositório**. Se todas as cópias forem perdidas ou commits inalcançáveis forem eliminados pelo Git, não há como reconstruí-los. Uma cópia externa ou backup regular continua sendo recomendada; **não é necessário hospedar um serviço adicional de histórico**.

### Ver commits antigos mesmo antes de vincular a VPS

```powershell
# No diretorio do VivoMonitor (ou de qualquer Git local)
ourgit history
ourgit history --limit 50
ourgit history --all

# JSON para pipelines, logs ou dashboards locais
ourgit history --json
ourgit history --json --limit 100

# Inspecionar autor, data e mudancas do commit
ourgit show a1b2c3d

# Exibir conteudo antigo de arquivo
ourgit show a1b2c3d --file vivomonitor/web/app.py

# Comparar duas versoes
ourgit diff --from a1b2c3d --to 9e8f7a6 --names
ourgit diff --from a1b2c3d --to 9e8f7a6
```

Substitua os SHAs ilustrativos por IDs de `ourgit history`. Histórico não depende de um remote OurGit cadastrado. O comando `history --json` expõe um objeto por commit com SHA, data, autor, assunto e metadados de auditoria caso existam.

### Auditoria automática: máquina, IP LAN e IP público de saída

A auditoria é **opcional e configurada por repositório**. Ao ativá-la, o OurGit instala um hook `post-commit` no Git, que funciona tanto para `ourgit commit` quanto para `git commit` e commits criados pela IDE (desde que disparem hooks Git).

**Modo recomendado (dados privados na máquina):**

```powershell
ourgit audit enable
ourgit audit status

# Criar commit normalmente:
ourgit add --all
ourgit commit -m "feat: atualizar aplicacao"

# Relatorio local de auditoria
ourgit audit log
ourgit audit log --json
```

Dados registrados: SHA, branch, autor e data Git, assunto, nome do computador, IP local estimado pela interface de rota e horário UTC. Eles são escritos em **`.git/ourgit-audit.jsonl`**, fora dos commits e sem transmissão automática para a VPS/GitHub. Esse arquivo **não é criptografado**: proteja acesso ao diretório `.git`.

**O IP público não é coletado por padrão.** Se autorizado para auditoria interna:

```powershell
ourgit audit enable --public-ip
```

Nessa modalidade o OurGit faz uma requisição HTTPS a `https://api.ipify.org` quando registra cada commit, para identificar o **IP público de saída**. Esse pode ser o IP de NAT, proxy ou VPN, não necessariamente o IP exclusivo do PC. O serviço externo recebe a conexão. Se estiver indisponível, fica marcado `unavailable` e o commit continua.

**Transportar os dados nos próprios commits (requer autorização explícita):**

```powershell
ourgit audit enable --embed --confirm-share

# Para incluir tambem IP publico:
ourgit audit enable --public-ip --embed --confirm-share
```

Nesse modo, o hook `prepare-commit-msg` adiciona *Git trailers* como `OurGit-Machine`, `OurGit-LAN-IP`, `OurGit-Public-IP` (quando solicitado) e `OurGit-UTC` ao texto dos **novos commits**. Portanto, esses dados acompanham `push` para GitHub e VPS e podem ficar permanentemente disponíveis a outras pessoas. **Evite em repositórios públicos ou com dados de rede sensíveis.** A ferramenta nunca falsifica ou reconstrói IPs de commits antigos.

Para parar a coleta:

```powershell
ourgit audit disable
```

A desativação remove apenas os hooks identificados como pertencentes ao OurGit, **sem apagar auditorias anteriores**. Se já houver um `post-commit` ou `prepare-commit-msg` de outra ferramenta, o OurGit recusa sobrescrevê-lo. Os campos de máquina/IP são **declarativos**, não uma prova criptográfica de identidade; uma política de commits assinados oferece garantia diferente.

### Recuperar arquivo específico de um commit antigo

```powershell
# 1. Visualizar o plano sem alterar codigo
ourgit recover --commit a1b2c3d --file vivomonitor/web/app.py

# 2. Se o destino estiver limpo, recuperar apenas esse arquivo
ourgit recover --commit a1b2c3d --file vivomonitor/web/app.py --apply

# 3. Se houver mudancas nao commitadas, so prosseguir com backup explicito
ourgit recover --commit a1b2c3d --file vivomonitor/web/app.py --backup --apply

git status --short
```

O comando **não executa push ou commit automaticamente**. Quando solicitado, cria backup das mudanças locais em `.git/ourgit-backups/` antes de substituir o arquivo. Caminhos fora do projeto são recusados.

### Recuperar o código completo de uma versão anterior

Em vez de sobrescrever o branch atual com `git reset --hard`, crie uma **nova branch** apontando para o commit anterior:

```powershell
ourgit recover --commit a1b2c3d --branch recovery/antes-da-alteracao
ourgit recover --commit a1b2c3d --branch recovery/antes-da-alteracao --apply

# So depois de revisar, pode trocar para essa branch:
git switch recovery/antes-da-alteracao
```

A criação da branch de recuperação mantém a branch atual, arquivos e remotos intactos. O `git switch` é uma etapa manual e independente.

### Reverter um commit sem apagar o histórico

```powershell
ourgit revert 9e8f7a6
ourgit revert 9e8f7a6 --apply
```

Com `--apply`, o OurGit chama `git revert --no-edit` após confirmar que a worktree está limpa. Isso cria **um novo commit inverso**, mantendo os commits antigos. Reversão de merge/root ou conflitos complexos precisa ser tratada manualmente.

### Pipeline de histórico e auditoria

A v0.3.0 também inclui o workflow [`.github/workflows/history.yml`](.github/workflows/history.yml), que executa a cada push e pode ser iniciado manualmente pela aba **Actions → OurGit - Histórico de Commits → Run workflow**. Ele gera um arquivo `ourgit-history.json` como artefato de CI (retenção de sete dias), usando o próprio Git do repositório e **sem servidor dedicado**. Em execuções automáticas, o relatório **oculta hostname, IP LAN e IP público**, mesmo que tais campos estejam incorporados aos commits. Para gerar um relatório com esses dados, é necessário um disparo manual com a opção `include_network_metadata=true` e autorização para a exposição a quem puder acessar os artefatos do repositório. O workflow não consegue descobrir retroativamente de qual máquina saiu um commit antigo sem metadados gravados no momento da criação.

O formato JSON já permite que outras ferramentas ou GitHub Actions consumam o histórico, por exemplo:

```powershell
ourgit history --all --limit 100 --json |
  Out-File -Encoding utf8 ".\historico-ourgit.json"
```

Esse arquivo é um **relatório gerado**, não um banco de dados nem um servidor dedicado. Se houver dados de IP na saída, trate o relatório como sensível e não publique como artefato público de CI. Os hooks funcionam localmente, independentemente de o SSH da VPS estar configurado.

---

## Desenvolvimento, builds e licença

A implementação inicial usa **Python 3.10+**, sem dependências Python obrigatórias para execução pelo código-fonte. Os binários são produzidos com **PyInstaller** no GitHub Actions; Git e SSH permanecem instalados no sistema operacional.

```bash
python ourgit.py --version
python -m unittest discover -s tests -v
```

- **CI:** [GitHub Actions · testes Windows/Linux](https://github.com/llongaray/OurGit/actions/workflows/ci.yml).
- **Distribuição:** [GitHub Releases](https://github.com/llongaray/OurGit/releases) com ZIP (Windows), TAR.GZ (Linux) e `checksums.txt`.
- **Contribuições:** abra Issue com passos reproduzíveis; envie PR incluindo testes. Não inclua IPs reais, senhas ou segredos em issues públicas.
- **Roadmap:** interface TUI, diff remota detalhada, workflows declarativos, aprovação por ambiente, assinaturas de release e rollback com healthchecks.
- **Licença:** [GNU GPL-3.0](LICENSE).

---

# English documentation

## OurGit — LAN Git synchronization and VPS deployment

[Back to Portuguese](#ourgit--git-remoto-e-deploy-de-vps-pela-lan) · [Releases](https://github.com/llongaray/OurGit/releases) · [CI](https://github.com/llongaray/OurGit/actions) · [License](LICENSE)

**OurGit** is a Windows/Linux command-line tool that manages Git repositories, commits, branch synchronization, SSH-connected Linux servers, and opt-in deployment actions. Its default topology is designed for a VPS with a **public IP but no publicly reachable SSH port** while **LAN/VPN SSH remains accessible**.

> **Important:** **installation happens over outbound HTTPS (443)** on each machine; **source-code synchronization happens over Git-over-SSH to the VPS private LAN/VPN IP and configured SSH port**. Installation and runtime transport are separate. No public SSH exposure or inbound HTTP service is required.

### Contents

1. [Network architecture](#network-architecture)
2. [Capabilities and limitations](#capabilities-and-limitations)
3. [Prerequisites](#prerequisites)
4. [Install over HTTPS](#install-over-https)
5. [Prepare private LAN SSH](#prepare-private-lan-ssh)
6. [Register and pair the developer PC with the VPS](#register-and-pair-the-developer-pc-with-the-vps)
7. [Inspect file and commit differences](#inspect-file-and-commit-differences)
8. [Push, pull, and synchronization](#push-pull-and-synchronization)
9. [Automated deployment actions](#automated-deployment-actions)
10. [Internal design](#internal-design)
11. [Alternative outbound HTTPS Pull Agent](#alternative-outbound-https-pull-agent)
12. [Security, troubleshooting, and CLI reference](#security-troubleshooting-and-cli-reference)
13. [Development, releases, and licensing](#development-releases-and-licensing)

## Network architecture

```text
                     PUBLIC INTERNET, OUTBOUND HTTPS :443
                           GitHub Releases
                            /           \
                       download       download
                          /               \
                 Developer PC         Linux VPS
               Windows / Linux      Private IP: 192.168.10.20
                  +----------+        +-------------------------+
                  | OurGit   |        | OurGit, bare Git repo  |
                  | local Git|        | separate deploy tree   |
                  | branch hml        | post-receive action     |
                  +----+-----+        +------------+------------+
                       |                           ^
                       +---- Git over LAN SSH:22 ---+
                            (or private VPN / port)
                             NO public SSH exposure
```

| Operation | Origin → destination | Transport | Port | Public incoming port required? |
|---|---|---|---|---|
| Install on PC | PC → GitHub Release | HTTPS | Outbound 443 | No |
| Install on VPS | VPS console → GitHub Release | HTTPS | Outbound 443 | No |
| Push commits | PC → VPS private IP | SSH + Git | LAN 22/custom | **No** |
| Pull commits | PC → VPS private IP | SSH + Git | LAN 22/custom | **No** |
| Run deploy | Server-side post-receive → local script | Local process | None | No |
| Optional GitHub remotes | PC → GitHub | Git HTTPS/SSH | Existing network policy | No inbound VPS port |

Example: the VPS publicly resolves to an address whose port 22 is blocked. If the PC can reach `192.168.10.20:22` over its LAN/VPN, choose `--host 192.168.10.20 --port 22`. Do **not** use the public address merely because the machine has one.

HTTPS installation cannot remotely execute commands without access to an authenticated shell. Run the first installer from the VPS provider console, private SSH, or another authorized administrative session.

## Capabilities and limitations

| Feature | Command | Availability |
|---|---|---|
| Register local repository | `ourgit init` | Implemented |
| Initialize Git explicitly | `ourgit init --git-init` | Implemented |
| Configure multiple Git destinations | `ourgit remote add` | Implemented |
| Pair a VPS using private LAN/VPN SSH | `ourgit connect` | Implemented |
| Display modified/untracked files | `ourgit status` | Implemented |
| Compare ahead/behind commit counts | `ourgit status --fetch` | Implemented |
| Stage and commit | `ourgit add` / `ourgit commit` | Implemented |
| Non-forced Git push | `ourgit push` | Implemented |
| Fast-forward-only pull | `ourgit pull` | Implemented |
| Plan or perform safe sync | `ourgit sync` / `ourgit sync --apply` | Implemented |
| Check the VPS bare/checkout state | `ourgit vps-status` | Implemented |
| Branch-triggered deployment | `post-receive` hook | Implemented |
| Deployment logs and action status | `ourgit server log` / `ourgit action-status` | Implemented |
| Multi-job YAML workflows and approvals | — | **Not implemented yet** |
| Web UI and live diff viewer | — | **Not implemented yet** |

OurGit uses the **real Git object database, references, commits, and SSH protocol**. It does not replace Git/GitHub. Status reporting includes local worktree changes and ahead/behind commit counts. The VPS status command also reports uncommitted remote checkout changes. File-by-file and line-by-line comparison is available through ordinary `git diff`, not through a dedicated OurGit comparison UI yet.

## Prerequisites

| Requirement | Windows developer workstation | Linux VPS |
|---|---|---|
| OS | Windows x64 | Linux x86_64, e.g. Ubuntu/Debian |
| OurGit | `ourgit.exe` | `ourgit` |
| Git | Git for Windows on PATH | `git` |
| SSH | OpenSSH client on PATH | SSH server listening on **LAN/VPN**, authorized account |
| Installation network | Outbound GitHub HTTPS | Outbound GitHub HTTPS |
| Sync network | Route to private VPS IP/port | Firewall allows SSH **from LAN/VPN** |
| Permissions | Write access to local Git repository | Write access to bare repository and checkout |
| Docker deployments | — | Docker/Compose if the app requires them |
| Source-based development | Python 3.10+ | Python 3.10+ |

Release binaries bundle Python runtime dependencies but **still rely on Git and SSH installed on the OS**. Official initial builds target x64.

On Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates openssh-client
git --version
```

Do not change the SSH server configuration or publish port 22 on the public interface merely to deploy OurGit.

## Install over HTTPS

Install independently on the PC and on the VPS; you **do not have to clone the OurGit repository**.

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.ps1 | iex
ourgit --version
ourgit --help
```

The script downloads the latest Windows Release over HTTPS, verifies SHA-256, extracts `ourgit.exe` to `%LOCALAPPDATA%\Programs\OurGit`, and updates the user PATH. Open a new terminal if the PATH is not visible.

Inspect before running if required by corporate policy:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.ps1 -OutFile "$env:TEMP\install-ourgit.ps1"
notepad "$env:TEMP\install-ourgit.ps1"
Get-Content -LiteralPath "$env:TEMP\install-ourgit.ps1" -Raw | Invoke-Expression
```

> **Restricted PowerShell Execution Policy:** invoking a downloaded `.ps1` with `&` may result in `PSSecurityException` even after a successful in-memory installation. The audited `Get-Content -Raw | Invoke-Expression` form above runs the reviewed content in the current session without changing the machine-wide execution policy. Follow company IT policy, and inspect settings with `Get-ExecutionPolicy -List`. You do not need to reinstall a working OurGit binary.

### Linux bash (run in the VPS terminal)

```bash
curl -fsSL https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
ourgit --version
ourgit --help
```

This uses outbound HTTPS and installs to `$HOME/.local/bin/ourgit`, without root or Git cloning. The installer validates the release archive hash.

To review first:

```bash
curl -fsSL https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.sh -o /tmp/install-ourgit.sh
less /tmp/install-ourgit.sh
sh /tmp/install-ourgit.sh
```

Assets: [latest release](https://github.com/llongaray/OurGit/releases/latest) · [Windows ZIP](https://github.com/llongaray/OurGit/releases/latest/download/ourgit-windows-x86_64.zip) · [Linux TAR.GZ](https://github.com/llongaray/OurGit/releases/latest/download/ourgit-linux-x86_64.tar.gz) · [checksums.txt](https://github.com/llongaray/OurGit/releases/latest/download/checksums.txt).

A checksum is an integrity mechanism, **not an independent cryptographic signature**. For production, review and pin the required release version and verify provenance.

## Windows enterprise compatibility and code signing (v0.3.1)

Corporate **App Control for Business / Code Integrity event 3077** can block an unsigned PyInstaller Windows executable even after HTTPS delivery and checksum verification. This is not a Git/SSH problem. Even a valid Authenticode signature does **not** automatically satisfy an enterprise policy; IT must approve the publisher/certificate or the exact file hash.

**Safe installer update and rollback:** `install/install.ps1` verifies archive SHA-256, checks Authenticode status, backs up the previous `ourgit.exe`, then tests the candidate at its final installation path. On an application-control block or other execution failure, it restores the previous file, without disabling Defender, App Control, AppLocker, or execution policies. If there was no previous installation, it removes the failed candidate.

~~~powershell
$exe = "$env:LOCALAPPDATA\Programs\OurGit\ourgit.exe"
Get-AuthenticodeSignature -LiteralPath $exe | Format-List Status, SignerCertificate
Get-FileHash -LiteralPath $exe -Algorithm SHA256
Get-WinEvent -FilterHashtable @{ LogName = "Microsoft-Windows-CodeIntegrity/Operational"; StartTime = (Get-Date).AddHours(-2); Id = 3077 } -ErrorAction SilentlyContinue | Where-Object { $_.Message -match "ourgit.exe" } | Select-Object -First 5 TimeCreated, Id, Message | Format-List
~~~

To **require a Windows-trusted signature** before installing:

~~~powershell
$env:OURGIT_REQUIRE_SIGNED = "1"
irm https://raw.githubusercontent.com/llongaray/OurGit/main/install/install.ps1 | iex

# Optional: require an IT-approved code-signing certificate thumbprint
$env:OURGIT_TRUSTED_SIGNER_THUMBPRINT = "IT_APPROVED_THUMBPRINT"
~~~

Do not use a fabricated thumbprint. An unsigned Release is rejected before replacing the installed binary when `OURGIT_REQUIRE_SIGNED=1`.

**CI signing:** `scripts/sign_windows.ps1` supports an organization-approved exportable Authenticode PFX and trusted timestamping. Configure a **protected GitHub Environment** named `ourgit-code-signing`, with authorized branch/tag restrictions and reviewers. Add secrets `OURGIT_CODESIGN_PFX_BASE64` and `OURGIT_CODESIGN_PFX_PASSWORD` to that Environment only if company key-management rules permit this approach. Prefer managed signing/HSM if private keys must not be exported. To prohibit an unsigned release, set `OURGIT_REQUIRE_SIGNED_RELEASE=1` in the Environment variables.

The published `windows-signature.json` reports signing mode, signer and executable SHA-256. **Without configured credentials, the Windows build remains unsigned and may still be blocked**. Final enforcement is determined by the organization's Code Integrity policy.

---

## Prepare private LAN SSH

HTTPS is used for installation only; SSH is used for **PC ↔ VPS Git operations**.

### 1. Test the private port

In Windows PowerShell:

```powershell
Test-NetConnection -ComputerName 192.168.10.20 -Port 22
```

`TcpTestSucceeded : True` indicates that the TCP connection works. A false result means checking the LAN/VPN route, the internal firewall, the actual SSH port, and the SSH daemon; **do not expose the public SSH port** to fix private connectivity.

### 2. Prepare SSH key authentication

On the PC, if needed:

```powershell
ssh-keygen -t ed25519 -C "ourgit-developer-workstation"
Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
```

Add the **public key only** to the deploy user's `~/.ssh/authorized_keys` on the VPS using an authorized administrative terminal. Standard VPS-side file permissions:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Never upload a private SSH key to the server, a Git repository, an issue, or a README.

### 3. Verify authentication

```powershell
ssh -p 22 deploy@192.168.10.20
```

OurGit uses non-interactive SSH; key authentication must succeed before pairing. Verify server host-key fingerprints out of band, particularly on the first connection. Site-to-site VPN access is supported whenever the private route and firewall permit it.

## Register and pair the developer PC with the VPS

### 1. Register the local application repository

```powershell
cd C:\Users\Developer\github\MyProject
ourgit init
ourgit status
```

Use `ourgit init --git-init` only if the folder does not already contain a Git repository and you explicitly want to create one.

### 2. Install OurGit on the VPS over HTTPS

Run the Linux installer from the VPS console and validate:

```bash
$HOME/.local/bin/ourgit --version
git --version
```

Use a dedicated, authorized `deploy` account with writable directories within its own home.

### 3. Pair from the PC over LAN SSH

```powershell
ourgit connect --host 192.168.10.20 --port 22 --user deploy --repo /home/deploy/repos/myproject-hml.git --worktree /home/deploy/apps/myproject-hml --branch hml --name vps-hml
```

| Option | Meaning |
|---|---|
| `--host` | VPS **private LAN or VPN IP/hostname** |
| `--port` | Internal VPS SSH port, e.g. 22 or 2222 |
| `--user` | SSH deploy account |
| `--repo` | Absolute bare Git repository directory on VPS (ends in `.git`) |
| `--worktree` | Separate absolute directory for checkout/deployment |
| `--branch` | Git branch to associate with the remote |
| `--name` | Local remote alias |
| `--identity` | Optional PC-side private SSH key path; the key is not copied to VPS |
| `--install-server` | Optional installer invoked **over SSH**; unnecessary when preinstalled from the VPS console over HTTPS |

`connect` invokes the installed VPS agent over private SSH, creates/configures the bare repository and receiving hook, and registers the local Git remote. It does **not start the application** or automatically enable a deployment action.

### 4. Verify pairing

```powershell
ourgit remote list
git remote -v
ourgit remote default vps-hml
ourgit status --remote vps-hml
ourgit vps-status --remote vps-hml
```

One application repository can retain several remotes, such as a corporate GitHub `origin`, a personal remote, and `vps-hml`. OurGit does not overwrite those remotes.

## Inspect file and commit differences

Once the VPS branch exists:

```powershell
ourgit status --remote vps-hml --fetch
git status --short
git diff
git diff --cached

git log --oneline vps-hml/hml..HEAD
git log --oneline HEAD..vps-hml/hml
git diff --stat vps-hml/hml HEAD

ourgit vps-status --remote vps-hml
```

The status displays **pending push commits**, **pending pull commits**, and uncommitted local files. If the two branches have diverged, OurGit refuses automatic synchronization, preserving history on both ends.

## Push, pull, and synchronization

### Commit and initial push

```powershell
ourgit add --all
ourgit commit -m "feat: first staging release"
ourgit push --remote vps-hml --dry-run
ourgit push --remote vps-hml
```

Only **committed** files are transported. Untracked or modified-but-uncommitted files are not automatically uploaded. The server hook records the Git update, while deployment remains disabled until explicitly enabled.

### Pull changes from VPS

```powershell
ourgit pull --remote vps-hml
```

The command performs fetch and `merge --ff-only`. A dirty local working tree or divergent commits prevent the operation; OurGit never silently resets or force-overwrites local work.

### Assisted synchronization

```powershell
ourgit sync --remote vps-hml
ourgit sync --remote vps-hml --apply
```

Without `--apply`, only a plan is displayed. With `--apply`, the tool performs a safe push or pull when the Git graph allows it; it never automatically merges divergent histories.

### Server-side changes

The deployment checkout is a normal Git working tree. If changes must be made directly on the server:

```bash
cd /home/deploy/apps/myproject-hml
git status
git add -- path/to/file
git commit -m "fix: server-side adjustment"
git push origin hml
```

Then run `ourgit pull --remote vps-hml` on the PC. Uncommitted server modifications block automatic checkout updates to avoid discarding changes.

## Automated deployment actions

The VPS bare repository contains a Git `post-receive` hook installed by `ourgit connect`. After the repository accepts a valid push to the configured branch, the hook can fast-forward the deployment checkout and execute an explicitly approved script.

**No HTTP webhook or internet-facing SSH port is involved.**

### 1. Create a reviewed script **outside the deployed Git checkout**

On the Linux VPS:

```bash
mkdir -p /home/deploy/actions

cat > /home/deploy/actions/myproject-hml.sh <<'SH'
#!/bin/sh
set -eu
: "$OURGIT_WORKTREE"
: "$OURGIT_SHA"
cd "$OURGIT_WORKTREE"

# Example only: adjust Docker project, compose files, and permissions first.
docker compose -p myproject-hml -f compose.yaml up -d --build
docker compose -p myproject-hml -f compose.yaml ps
SH

chmod 700 /home/deploy/actions/myproject-hml.sh
```

Review the script, resource limits, Docker access, and isolation before enabling it. Do not use an example deployment script against critical production services without approval.

### 2. Enable the action explicitly

```bash
$HOME/.local/bin/ourgit server action set --repo /home/deploy/repos/myproject-hml.git --script /home/deploy/actions/myproject-hml.sh --timeout 600
$HOME/.local/bin/ourgit server action status --repo /home/deploy/repos/myproject-hml.git
```

Each **new accepted push** to branch `hml` now triggers the workflow. To run a deployment of the current branch manually:

```bash
$HOME/.local/bin/ourgit server deploy --repo /home/deploy/repos/myproject-hml.git
```

### 3. Check logs and disable

```bash
$HOME/.local/bin/ourgit server log --repo /home/deploy/repos/myproject-hml.git --lines 40
$HOME/.local/bin/ourgit server action disable --repo /home/deploy/repos/myproject-hml.git
```

On the developer PC:

```powershell
ourgit action-status --remote vps-hml
ourgit vps-status --remote vps-hml
```

A successful Git push **does not guarantee a successful application deployment**. The post-receive action happens after Git accepts commits and may fail on checkout, Docker, permissions, build, or health checks. Check deployment logs and application health; automatic rollback is not implemented.

### Detailed hook lifecycle

1. Git validates the push and updates `refs/heads/hml`.
2. The hook verifies that actions are enabled and the commit SHA still matches the branch.
3. A deployment lock prevents concurrent checkouts.
4. A separate working tree is created or fast-forwarded, with no hard reset.
5. Wrong branch, dirty checkout, or divergent history blocks updates.
6. The reviewed script runs with `OURGIT_WORKTREE`, `OURGIT_BRANCH`, and `OURGIT_SHA`.
7. Results and failures are saved to `ourgit-actions.log` under the bare repository.

This is a **branch-specific deployment action**, not yet a full hosted GitHub Actions replacement with YAML runners, multiple jobs, approvals, or transactional rollbacks.

## Internal design

- **Git transport:** Git push/fetch uses an `ssh://user@PRIVATE_IP:PORT/bare.git` remote. The SSH private key stays on the client PC.
- **Change comparison:** `git status --porcelain` reports local worktree changes, and `git rev-list --left-right --count` calculates commit divergence.
- **Local configuration:** `.git/ourgit.json` records remote aliases, branches, and SSH parameters and is not committed to the repository.
- **Server-side Git:** a bare repository holds commit objects and the post-receive hook; a separate checkout holds executable application files.
- **Safety:** non-fast-forward and branch deletions are refused by the configured bare repository; OurGit avoids force push and hard reset.
- **Deployment:** a reviewed script outside the checkout, enabled explicitly, executes under the SSH Linux account.
- **Distribution:** GitHub Actions produces Windows/Linux binaries, SHA-256 checksums, and HTTPS installation scripts.
- **Monitoring:** local server logs and SSH queries; no publicly exposed management HTTP dashboard.

### Repository layout

```text
OurGit/
├── ourgit.py
├── ourgit_pull_agent.py
├── install/
│   ├── install.ps1
│   └── install.sh
├── .github/workflows/
│   ├── ci.yml
│   └── release.yml
├── scripts/package_release.py
├── examples/deploy-docker.sh
├── tests/
├── README.md
└── LICENSE
```

## Alternative outbound HTTPS Pull Agent

This option is **not required when private LAN SSH is working**. It is reserved for environments where a VPS cannot accept SSH connections **even on its LAN/VPN**. In that situation, the VPS itself periodically fetches a configured Git HTTPS branch using an outbound-only connection, and an opt-in local action can deploy updates through a user-level systemd timer.

```bash
ourgit agent init --name myapp-hml --url https://github.com/ORGANIZATION/REPOSITORY.git --branch hml --worktree /home/deploy/apps/myapp-hml
ourgit agent check --name myapp-hml
ourgit agent check --name myapp-hml --apply
ourgit agent status --name myapp-hml
ourgit agent timer render --name myapp-hml --minutes 5
```

HTTPS credentials for private repositories must be configured securely, with read-only scope, outside Git URLs and source files. The polling agent does not receive direct SSH pushes and is not the default mode for LAN-connected VPS deployments.

## Security, troubleshooting, and CLI reference

### Security requirements

- Restrict VPS SSH ingress to **LAN/VPN** addresses; use a dedicated deploy account with SSH keys.
- Do not enable public port 22, root login, or password-based SSH merely for OurGit.
- Independently verify SSH host-key fingerprints; first-connection trust-on-first-use is not sufficient for sensitive systems.
- Restrict write access to the bare Git directory, deployment checkout, and administrator-controlled action scripts.
- Keep `.env`, API tokens, SSH private keys, and credentials out of Git commits and public issue reports.
- Treat deployment scripts as privileged application operations: review the exact commands and OS user permissions.
- Separate staging and production projects; enforce resource limits, backups, and application-specific recovery plans.
- Downloads use HTTPS and SHA-256; no independent release signature or attestation is currently provided.

### Troubleshooting

| Symptom | Likely cause | Safe response |
|---|---|---|
| Public SSH fails, LAN SSH works | Expected restricted-public-port setup | Connect to **private IP/port** |
| LAN TCP port test fails | Missing VPN route, firewall rule, wrong port | Check internal network; avoid exposing public port |
| `Permission denied (publickey)` | SSH public key not authorized | Verify deploy user and `authorized_keys` |
| `Host key verification failed` | Host identity changed or unverified | Verify fingerprint with administrator |
| Git unavailable | Git missing from PATH | Install system Git and reopen terminal |
| OurGit not recognized | User PATH not refreshed | Open new terminal; Linux: prepend `$HOME/.local/bin` |
| Zero push/pull commits | Git history synchronized | Check local uncommitted files separately |
| Remote branch missing | No initial push | Confirm branch name and push first commit |
| Divergent history | Unique commits on both sides | Resolve conflicts manually; avoid force push |
| Dirty VPS checkout | Uncommitted direct server changes | Commit/stash/reconcile; no automatic reset |
| Git push succeeds but deploy fails | Action disabled/error | Inspect action status and server logs |
| HTTPS installation fails | Outbound firewall/DNS/proxy/TLS | Validate GitHub/Release connectivity from VPS |
| Docker permissions denied | Deploy user not authorized | Request access; do not broadly enable root |
| SSH listens on custom LAN port | Incorrect port in connect | Use `--port PRIVATE_PORT` |

### CLI quick reference

| Command | Action |
|---|---|
| `ourgit --help` / `--version` | Help/version |
| `ourgit init [--git-init] [--path PATH]` | Register/init repository |
| `ourgit remote add --name N --url URL --branch B` | Register existing remote |
| `ourgit remote list` / `remote default N` | List/set default |
| `ourgit connect --host IP --port PORT --user USER --repo BARE --worktree CHECKOUT --branch B --name N` | Pair VPS over LAN SSH |
| `ourgit status [--fetch] [--remote N]` | Inspect change counts |
| `ourgit add --all` | Stage files |
| `ourgit commit -m "message"` | Commit changes |
| `ourgit push [--dry-run] [--remote N]` | Push committed changes |
| `ourgit pull [--remote N]` | Fetch and fast-forward |
| `ourgit sync [--apply] [--remote N]` | Preview/apply safe sync |
| `ourgit vps-status --remote N` | Inspect VPS bare and checkout |
| `ourgit action-status --remote N` | Inspect remote action |
| `ourgit server init / action / log / deploy` | Operate Linux server agent |
| `ourgit agent init / check / timer` | Optional outbound HTTPS Pull Agent |

## Commit history, machine auditing, and safe recovery (v0.3.0)

**No dedicated history server is necessary.** Git already stores commits and historical file contents in its object database inside each clone (`.git`), a VPS bare repository, or a regular Git remote. OurGit provides history, audit, and safe recovery commands on top of Git.

> Recovery requires the desired objects to still exist in at least **one available repository copy**. If every replica is lost or unreachable objects have been pruned, recovery may be impossible. Maintain independent backups as appropriate; there is no requirement to run a new always-on server.

### Read commit history before configuring a VPS remote

```powershell
ourgit history
ourgit history --limit 50
ourgit history --all
ourgit history --json --limit 100
ourgit show a1b2c3d
ourgit show a1b2c3d --file vivomonitor/web/app.py
ourgit diff --from a1b2c3d --to 9e8f7a6 --names
ourgit diff --from a1b2c3d --to 9e8f7a6
```

Replace example SHAs with those listed by `ourgit history`. The JSON report contains commit SHA, date, author, title, and available machine/IP audit details. None of these history commands require an OurGit remote.

### Optional commit auditing: hostname and private/public IP

**Auditing is opt-in for each repository.** Enabling installs a Git `post-commit` hook, so it captures new commits created through OurGit, ordinary Git CLI, or IDE Git integration that runs hooks.

**Private local-only audit (recommended):**

```powershell
ourgit audit enable
ourgit audit status
ourgit add --all
ourgit commit -m "feat: update application"
ourgit audit log
ourgit audit log --json
```

Records include SHA, branch, Git author/timestamp, subject, hostname, a route-selected local IP, and the audit UTC timestamp. They are stored in **`.git/ourgit-audit.jsonl`**, not added to shared Git commits. This file is plaintext; secure access to your local `.git` directory.

**Public IP lookup is disabled by default.** To opt in:

```powershell
ourgit audit enable --public-ip
```

This makes an outbound HTTPS request to `https://api.ipify.org` per recorded commit. The result is the **public egress IP**, potentially representing corporate NAT, VPN, or a proxy rather than a unique host. The external IP service sees the request. Offline failures are recorded as `unavailable` without blocking commits.

**Portable metadata in commit trailers (explicit consent required):**

```powershell
ourgit audit enable --embed --confirm-share

# Also share the public egress IP if explicitly intended:
ourgit audit enable --public-ip --embed --confirm-share
```

The `prepare-commit-msg` hook adds fields such as `OurGit-Machine`, `OurGit-LAN-IP`, optional `OurGit-Public-IP`, and `OurGit-UTC` to **new commits**. They will be carried by pushes to GitHub and VPS. These values may remain permanently visible in shared or public repositories; **do not enable this mode without reviewing your network privacy requirements**. OurGit cannot reconstruct machine/IP details for older commits.

To disable hooks while preserving previous records:

```powershell
ourgit audit disable
```

OurGit refuses to overwrite third-party Git hooks. Machine and IP metadata are **self-reported**, not cryptographically authenticated device identity; signed commits address a separate concern.

### Recover one file from a previous commit

```powershell
# Preview: no modifications
ourgit recover --commit a1b2c3d --file vivomonitor/web/app.py

# Apply when working-tree file is clean
ourgit recover --commit a1b2c3d --file vivomonitor/web/app.py --apply

# Preserve outstanding changes in .git/ourgit-backups before restoration
ourgit recover --commit a1b2c3d --file vivomonitor/web/app.py --backup --apply

git status --short
```

Recovery does not automatically commit or push. Files outside the repository are rejected. Outstanding changes block restoration unless the backup option is explicitly supplied.

### Recover the full source tree into a new branch

Avoid overwriting your current branch via hard reset:

```powershell
ourgit recover --commit a1b2c3d --branch recovery/previous-working-version
ourgit recover --commit a1b2c3d --branch recovery/previous-working-version --apply

# Switch only when you are ready:
git switch recovery/previous-working-version
```

Creating the recovery branch does **not** change the current checkout, HEAD, or remotes.

### Revert a commit without destroying history

```powershell
ourgit revert 9e8f7a6
ourgit revert 9e8f7a6 --apply
```

The apply form requires a clean working tree and creates an inverse commit using `git revert --no-edit`. The original historical commit is kept. Merge/root reverts and complex conflicts need manual Git resolution.

### Use history JSON in pipelines

Version 0.3.0 also ships [`.github/workflows/history.yml`](.github/workflows/history.yml), which runs on push and supports manual execution under **Actions → OurGit - Histórico de Commits → Run workflow**. It creates a seven-day `ourgit-history.json` workflow artifact using native Git, **without any dedicated history server**. Automatic reports **redact hostname, LAN IP and public egress IP**, even when embedded in commit trailers. Including those fields requires a manually dispatched run with `include_network_metadata=true` and an explicit review of who can access the resulting artifact. A CI runner cannot retrospectively infer the actual developer machine or network address of a historical commit without data recorded at commit time.

```powershell
ourgit history --all --limit 100 --json |
  Out-File -Encoding utf8 ".\ourgit-history.json"
```

This output is a report, **not a dedicated database/server**. Treat it as sensitive if IP or machine metadata are included; do not upload network inventory to public CI artifacts. Local audit hooks work whether or not a VPS is currently reachable over SSH.

---

## Development, releases, and licensing

The core is written in **Python 3.10+**, distributed as self-contained executables built with **PyInstaller**. Git and SSH remain external OS dependencies.

```bash
python ourgit.py --version
python -m unittest discover -s tests -v
```

- **CI:** [Windows/Linux test workflow](https://github.com/llongaray/OurGit/actions/workflows/ci.yml).
- **Binary releases:** [GitHub Releases](https://github.com/llongaray/OurGit/releases), including Windows ZIP, Linux TAR.GZ, and `checksums.txt`.
- **Contributing:** submit a reproducible issue or a PR with regression tests, never including production hostnames, passwords, or credentials.
- **Roadmap:** richer terminal UI, remote line-by-line diffs, declarative workflows, environment approvals, signed releases, and healthcheck-driven rollbacks.
- **License:** [GNU GPL-3.0](LICENSE).

