# Local development tasks.
PROLEAP_BRIDGE_JAR ?= $(CURDIR)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
export PROLEAP_BRIDGE_JAR

PYTEST      = uv run python -m pytest
PYTEST_ARGS ?=

.PHONY: help setup test jar jar-force fmt lint

help:
	@echo "make setup      - initialise submodules + build the ProLeap JAR (run once after clone)"
	@echo "make test       - full suite (builds the JAR if missing)"
	@echo "make jar        - build the ProLeap bridge JAR if it is missing"
	@echo "make jar-force  - rebuild the ProLeap bridge JAR (run after changing Java/bridge sources)"
	@echo "make fmt        - black-format the codebase"
	@echo "make lint       - import-linter contracts"
	@echo ""
	@echo "PROLEAP_BRIDGE_JAR=$(PROLEAP_BRIDGE_JAR)"

# One-time setup from a fresh clone: pull submodules then build the JAR.
setup:
	git submodule update --init --recursive
	$(MAKE) jar

# Build the shaded JAR only when it is missing (file target).
$(PROLEAP_BRIDGE_JAR):
	cd proleap-bridge && mvn -DskipTests package -q

jar: $(PROLEAP_BRIDGE_JAR)

jar-force:
	cd proleap-bridge && mvn -DskipTests package -q

test: jar
	$(PYTEST) $(PYTEST_ARGS)

fmt:
	uv run python -m black .

lint:
	uv run lint-imports
