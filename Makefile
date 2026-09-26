# Local development tasks.
PROLEAP_BRIDGE_JAR ?= $(CURDIR)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
export PROLEAP_BRIDGE_JAR

# The ProLeap parser is NOT on Maven Central: version 4.0.0 is this fork's own
# version, declared by the vendored submodule. It must be built and installed
# into the local ~/.m2 repo before proleap-bridge can resolve it. Version is
# read from the bridge pom so it stays single-sourced.
PROLEAP_VERSION    := $(shell sed -n 's|.*<proleap.version>\(.*\)</proleap.version>.*|\1|p' $(CURDIR)/proleap-bridge/pom.xml)
PROLEAP_PARSER_DIR := $(CURDIR)/proleap-bridge/proleap-cobol-parser
# Only src/main: the install runs with -DskipTests, so test sources cannot
# affect the installed artifact and must not trigger a ~90s rebuild.
PROLEAP_PARSER_SRC := $(shell find $(PROLEAP_PARSER_DIR)/src/main -type f 2>/dev/null)
PROLEAP_PARSER_JAR := $(HOME)/.m2/repository/io/github/uwol/proleap-cobol-parser/$(PROLEAP_VERSION)/proleap-cobol-parser-$(PROLEAP_VERSION).jar

PYTEST      = uv run python -m pytest
PYTEST_ARGS ?=

.PHONY: help setup test jar jar-force parser parser-force fmt lint

help:
	@echo "make setup      - initialise submodules + build the ProLeap JAR (run once after clone)"
	@echo "make test       - full suite (builds the JAR if missing)"
	@echo "make jar        - build the ProLeap bridge JAR if it is missing"
	@echo "make parser     - install the vendored ProLeap parser into ~/.m2 if stale/missing"
	@echo "make parser-force - reinstall the ProLeap parser unconditionally"
	@echo "make jar-force  - rebuild the ProLeap bridge JAR (run after changing Java/bridge sources)"
	@echo "make fmt        - black-format the codebase"
	@echo "make lint       - import-linter contracts"
	@echo ""
	@echo "PROLEAP_BRIDGE_JAR=$(PROLEAP_BRIDGE_JAR)"
	@echo "PROLEAP_PARSER_JAR=$(PROLEAP_PARSER_JAR)"

# One-time setup from a fresh clone: pull submodules, install the parser into
# ~/.m2 (via the jar's prerequisites), then build the bridge JAR.
setup:
	git submodule update --init --recursive
	$(MAKE) jar

# Check out the submodule if it is not there yet (file target on its pom), so
# `make test`/`make jar` also work from a bare clone, not just `make setup`.
$(PROLEAP_PARSER_DIR)/pom.xml:
	git submodule update --init --recursive

# Build + install the vendored parser when it is absent from ~/.m2, or when the
# submodule's pom/sources are newer than the installed jar -- otherwise grammar
# edits would silently never reach the bridge. The build command itself lives in
# proleap-bridge/build.sh so it is not duplicated here.
$(PROLEAP_PARSER_JAR): $(PROLEAP_PARSER_DIR)/pom.xml $(PROLEAP_PARSER_SRC)
	cd $(CURDIR)/proleap-bridge && ./build.sh parser

parser: $(PROLEAP_PARSER_JAR)

# Unconditional parser reinstall (the analogue of jar-force).
parser-force:
	cd $(CURDIR)/proleap-bridge && ./build.sh parser

# Build the shaded JAR only when it is missing (file target).
$(PROLEAP_BRIDGE_JAR): $(PROLEAP_PARSER_JAR)
	cd proleap-bridge && mvn -DskipTests package -q

jar: $(PROLEAP_BRIDGE_JAR)

jar-force: $(PROLEAP_PARSER_JAR)
	cd proleap-bridge && mvn -DskipTests package -q

test: jar
	$(PYTEST) $(PYTEST_ARGS)

fmt:
	uv run python -m black .

lint:
	uv run lint-imports
