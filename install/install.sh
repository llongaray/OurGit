#!/bin/sh
# OurGit: instala Linux x86_64 sem clonar repositorio, com checksum SHA-256.
set -eu
BASE='https://github.com/llongaray/OurGit/releases/latest/download'
ASSET='ourgit-linux-x86_64.tar.gz'
DEST="${OURGIT_INSTALL_DIR:-${HOME}/.local/bin}"
command -v curl >/dev/null 2>&1 || { echo 'Erro: curl nao encontrado' >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo 'Erro: sha256sum nao encontrado' >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo 'Erro: instale Git antes' >&2; exit 1; }
[ "$(uname -m)" = 'x86_64' ] || { echo 'Somente Linux x86_64' >&2; exit 1; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
curl -fsSL --retry 3 "$BASE/$ASSET" -o "$tmp/$ASSET"
curl -fsSL --retry 3 "$BASE/checksums.txt" -o "$tmp/checksums.txt"
line=$(grep "  ${ASSET}\$" "$tmp/checksums.txt" | head -n 1 || true)
[ -n "$line" ] || { echo 'Erro: checksum ausente' >&2; exit 1; }
printf '%s\n' "$line" | (cd "$tmp" && sha256sum --check --status) || { echo 'Erro: SHA-256 invalido' >&2; exit 1; }
mkdir -p "$tmp/unpack" "$DEST"
tar -xzf "$tmp/$ASSET" -C "$tmp/unpack" ourgit
install -m 0755 "$tmp/unpack/ourgit" "$DEST/ourgit"
echo "OurGit instalado em: $DEST/ourgit"
"$DEST/ourgit" --version
case ":$PATH:" in
  *":$DEST:"*) ;;
  *)
    if [ "$DEST" = "$HOME/.local/bin" ]; then
      profile="$HOME/.profile"
      if ! grep -Fq '# OurGit user bin' "$profile" 2>/dev/null; then
        printf '\n# OurGit user bin\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$profile"
      fi
    fi
    echo "Para esta sessao: export PATH=\"$DEST:\$PATH\""
    ;;
esac
