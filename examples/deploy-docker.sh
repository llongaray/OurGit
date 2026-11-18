#!/bin/sh
# MODELO: copiar para diretorio fora do deploy e revisar antes de habilitar.
set -eu
: "${OURGIT_WORKTREE:?}"
: "${OURGIT_SHA:?}"
cd "$OURGIT_WORKTREE"
echo "OurGit: deploy de $OURGIT_BRANCH ($OURGIT_SHA)"
# Personalize o nome e arquivos antes do uso. Nunca execute sem revisao.
docker compose -p projeto-hml -f compose.yaml up -d --build
docker compose -p projeto-hml -f compose.yaml ps
