# Local development tasks.
#
# The AWS CardDemo CICS end-to-end tests are MANDATORY locally (they run on a
# dev machine and are skipped only in CI). `make test` sets up the required
# toolchain environment so they execute; a plain `pytest` without these vars
# will hard-fail those ~3 modules by design (see tests/integration/cics/conftest.py).
#
# Override any path via the environment if your checkouts live elsewhere, e.g.
#   CARDDEMO_HOME=/path/to/carddemo/app make test
CARDDEMO_HOME      ?= $(HOME)/code/aws-mainframe-carddemo/app
BMS_TOOLS_HOME     ?= $(HOME)/code/bms-tools
PROLEAP_BRIDGE_JAR ?= $(CURDIR)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar

E2E_ENV = CARDDEMO_HOME=$(CARDDEMO_HOME) BMS_TOOLS_HOME=$(BMS_TOOLS_HOME) PROLEAP_BRIDGE_JAR=$(PROLEAP_BRIDGE_JAR)
PYTEST  = uv run python -m pytest
PYTEST_ARGS ?=

.PHONY: help test test-cics jar jar-force fmt lint

help:
	@echo "make test       - full suite locally WITH the CardDemo toolchain (builds the JAR if missing)"
	@echo "make test-cics  - just the gated CardDemo CICS e2e (+ CICS integration tests)"
	@echo "make jar        - build the ProLeap bridge JAR if it is missing"
	@echo "make jar-force  - rebuild the ProLeap bridge JAR (run after changing Java/bridge sources)"
	@echo "make fmt        - black-format the codebase"
	@echo "make lint       - import-linter contracts"
	@echo ""
	@echo "Toolchain (override via env): CARDDEMO_HOME=$(CARDDEMO_HOME)"
	@echo "                              BMS_TOOLS_HOME=$(BMS_TOOLS_HOME)"
	@echo "                              PROLEAP_BRIDGE_JAR=$(PROLEAP_BRIDGE_JAR)"

# Build the shaded JAR only when it is missing (file target).
$(PROLEAP_BRIDGE_JAR):
	cd proleap-bridge && mvn -DskipTests package -q

jar: $(PROLEAP_BRIDGE_JAR)

jar-force:
	cd proleap-bridge && mvn -DskipTests package -q

# Full local suite with the CardDemo e2e toolchain set up (so they run, not fail).
test: jar
	$(E2E_ENV) $(PYTEST) $(PYTEST_ARGS)

# Just the CICS integration tests, incl. the gated CardDemo e2e.
test-cics: jar
	$(E2E_ENV) $(PYTEST) tests/integration/cics/ $(PYTEST_ARGS)

fmt:
	uv run python -m black .

lint:
	uv run lint-imports
