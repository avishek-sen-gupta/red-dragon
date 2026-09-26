#!/usr/bin/env bash
# Builds ProLeap from the vendored submodule, then builds the bridge.
#
# Usage: cd proleap-bridge && ./build.sh [parser|bridge|all]    (default: all)
#
# The Makefile delegates its parser step to `./build.sh parser`, so the parser
# build command lives here only, in one place.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-all}"

build_parser() {
  # The parser is not on Maven Central -- its version is this fork's own -- so it
  # must be installed into the local ~/.m2 repo before the bridge can resolve it.
  # `clean` because this is a generated-parser build: stale ANTLR output fails in
  # confusing ways. Not -q: this is the slow step (~90s) and quieting it hides
  # dependency-resolution failures.
  echo "==> Building ProLeap COBOL Parser from submodule..."
  cd "$SCRIPT_DIR/proleap-cobol-parser"
  mvn clean install -DskipTests
}

build_bridge() {
  echo "==> Building ProLeap Bridge..."
  cd "$SCRIPT_DIR"
  mvn clean package -q
  echo "==> Done. Fat JAR: target/proleap-bridge-0.1.0-shaded.jar"
}

case "$TARGET" in
  parser) build_parser ;;
  bridge) build_bridge ;;
  all)    build_parser; build_bridge ;;
  *)      echo "usage: ${0##*/} [parser|bridge|all]" >&2; exit 2 ;;
esac
