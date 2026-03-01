#!/usr/bin/env bash
# Builds ProLeap from the vendored submodule, then builds the bridge.
# Usage: cd proleap-bridge && ./build.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Building ProLeap COBOL Parser from submodule..."
cd "$SCRIPT_DIR/proleap-cobol-parser"
mvn clean install -DskipTests -q

echo "==> Building ProLeap Bridge..."
cd "$SCRIPT_DIR"
mvn clean package -q

echo "==> Done. Fat JAR: target/proleap-bridge-0.1.0-shaded.jar"
