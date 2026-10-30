VENV := .venv
PYTHON := $(VENV)/bin/python3
UV := uv
PROG := sandbox
MCP_CMD ?= python mcp_tools_mbpp.py
CONFIG ?= configs/sandbox_template.json
MCP_URL ?= http://localhost:8000/mcp
SRCFILES := main.py src/

help:
	@echo "Available commands:"
	@echo "  make install     - Install dependencies"
	@echo "  make run         - Run the sandbox CLI without mcp server"
	@echo "  make run-stdio   - Run the sandbox CLI with mcp server by stdio transport. make run-stdio [CONFIG=...] [MCP_CMD=...]"
	@echo "  make run-server  - Run the sandbox CLI with mcp server by http transportmake run-server [CONFIG=...] [MCP_URL=...]"
	@echo "  make clean       - Clean temporary files"
	@echo "  make clean-all   - Clean virtual environment"
	@echo "  make lint        - Run linters and type checkers"
	@echo "  make lint-strict - Run linters and type checkers in strict mode"

install:
	@$(UV) sync

run:
	@$(UV) run $(PROG)

run-stdio:
	@$(UV) run $(PROG) --mcp-stdio "$(MCP_CMD)" $(CONFIG)

run-server:
	@$(UV) run $(PROG) --mcp-server $(MCP_URL) $(CONFIG)

debug:
	@$(PYTHON) -m pdb $(PROG)

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

.PHONY: help install run clean lint lint-strict debug clean-all run-stdio run-server