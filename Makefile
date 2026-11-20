VENV := .venv
PYTHON := $(VENV)/bin/python3
UV := uv
PROG := sandbox
TESTBED_PATH := $(shell pwd)
MCP_MBPP_CMD ?= python3 mcp_tools_mbpp.py
MCP_SWE_CMD ?= python3 mcp_tools_swebench.py
CONFIG ?= configs/sandbox_template.json
MCP_URL ?= http://localhost:8000/mcp
SRCFILES := src/ agent_mbpp/ agent_swebench/ mcp_tools_*.py

help:
	@echo "Available commands:"
	@echo "  make install              - Install dependencies"
	@echo "  make run                  - Run the sandbox CLI without mcp server"
	@echo "  make run-stdio-mbpp       - Run the sandbox CLI with mcp server with mbpp tools by stdio transport. make run-stdio-mbpp [CONFIG=...] [MCP_MBPP_CMD=...]"
	@echo "  make run-stdio-swebench   - Run the sandbox CLI with mcp server with swebench tools by stdio transport. make run-stdio-swebench [CONFIG=...] [MCP_SWE_CMD=...]"
	@echo "  make serve-http           - Run a MCP server in http with mbpp tools."
	@echo "  make run-server           - Run the sandbox CLI with mcp server by http transport. make run-server [CONFIG=...] [MCP_URL=...]"
	@echo "  make clean                - Clean temporary files"
	@echo "  make clean-all            - Clean virtual environment"
	@echo "  make lint                 - Run linters and type checkers"
	@echo "  make lint-strict          - Run linters and type checkers in strict mode"

install:
	@$(UV) sync

run:
	@$(UV) run $(PROG)

run-stdio-mbpp:
	@$(UV) run $(PROG) --mcp-stdio "$(MCP_MBPP_CMD)" $(CONFIG)

run-server:
	@$(UV) run $(PROG) --mcp-server $(MCP_URL) $(CONFIG)

serve-http:
	@$(UV) run fastmcp run mcp_tools_mbpp.py --transport http --port 8000

run-stdio-swebench:
	@TESTBED_PATH=$(TESTBED_PATH) $(UV) run $(PROG) --mcp-stdio "$(MCP_SWE_CMD)" $(CONFIG)

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete

clean-all: clean
	@rm -rf $(VENV)

lint:
	@$(UV) run $(PYTHON) -m flake8 $(SRCFILES)
	@$(UV) run $(PYTHON) -m mypy $(SRCFILES) \
	--warn-return-any \
	--warn-unused-ignores \
	--ignore-missing-imports \
	--disallow-untyped-defs \
	--check-untyped-defs \

lint-strict:
	@$(UV) run $(PYTHON) -m flake8 $(SRCFILES)
	@$(UV) run $(PYTHON) -m mypy $(SRCFILES) --strict

.PHONY: help install run clean lint lint-strict clean-all run-stdio-mbpp run-server run-stdio-swebench serve-http
