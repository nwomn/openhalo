#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="${OPENHALO_REPOSITORY:-https://github.com/nwomn/openhalo.git}"
REF=""
EDGE_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      REF="${2:-}"
      shift 2
      ;;
    --edge-only)
      EDGE_ONLY=true
      shift
      ;;
    *)
      echo "usage: install.sh --ref <40-character-commit>" >&2
      exit 2
      ;;
  esac
done

if [[ ! "$REF" =~ ^[0-9a-f]{40}$ ]]; then
  echo "install.sh requires a fixed 40-character commit through --ref" >&2
  exit 2
fi

RELEASE_HOME="${OPENHALO_RELEASE_HOME:-$HOME/.local/share/openhalo}"
BIN_HOME="${OPENHALO_BIN_HOME:-$HOME/.local/bin}"
RELEASE_DIR="$RELEASE_HOME/releases/$REF"
TEMPORARY_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMPORARY_DIR"' EXIT

if [[ -e "$RELEASE_DIR" ]]; then
  echo "OpenHalo release $REF is already installed." >&2
else
  git clone --no-checkout "$REPOSITORY" "$TEMPORARY_DIR/source"
  git -C "$TEMPORARY_DIR/source" fetch --depth=1 origin "$REF"
  git -C "$TEMPORARY_DIR/source" checkout --detach "$REF"
  if [[ "$(git -C "$TEMPORARY_DIR/source" rev-parse HEAD)" != "$REF" ]]; then
    echo "fetched source did not resolve to the requested commit" >&2
    exit 1
  fi
  mkdir -p "$RELEASE_DIR"
  python3 -m venv "$RELEASE_DIR/venv"
  "$RELEASE_DIR/venv/bin/pip" install --upgrade pip
  "$RELEASE_DIR/venv/bin/pip" install "$TEMPORARY_DIR/source"
fi

mkdir -p "$RELEASE_HOME" "$BIN_HOME"
chmod 700 "$RELEASE_HOME" "$RELEASE_HOME/releases" "$BIN_HOME"
TEMPORARY_LINK="$RELEASE_HOME/.current.$$"
ln -s "$RELEASE_DIR" "$TEMPORARY_LINK"
mv -Tf "$TEMPORARY_LINK" "$RELEASE_HOME/current"
if [[ "$EDGE_ONLY" == false ]]; then
  TEMPORARY_COMMAND="$BIN_HOME/.openhalo.$$"
  ln -s "$RELEASE_HOME/current/venv/bin/openhalo" "$TEMPORARY_COMMAND"
  mv -Tf "$TEMPORARY_COMMAND" "$BIN_HOME/openhalo"
fi
TEMPORARY_EDGE_COMMAND="$BIN_HOME/.openhalo-edge.$$"
ln -s "$RELEASE_HOME/current/venv/bin/openhalo-edge" "$TEMPORARY_EDGE_COMMAND"
mv -Tf "$TEMPORARY_EDGE_COMMAND" "$BIN_HOME/openhalo-edge"

if [[ "$EDGE_ONLY" == true ]]; then
  echo "OpenHalo Terminal Edge installed. Ensure $BIN_HOME is on PATH, then run: openhalo-edge setup"
else
  echo "OpenHalo installed. Ensure $BIN_HOME is on PATH, then run: openhalo setup"
fi
