# Memorycore Development Makefile
# Provides common development tasks and shortcuts

.PHONY: help test lint format clean build install docs backup restore

# Default target
help:
	@echo "Memorycore Development Tasks"
	@echo "==========================="
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run all tests"
	@echo "  make test-cov       - Run tests with coverage"
	@echo "  make test-quick     - Run tests quickly without coverage"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Run all linters"
	@echo "  make lint-black     - Run Black formatter check"
	@echo "  make lint-isort     - Run isort check"
	@echo "  make lint-flake8    - Run flake8"
	@echo "  make lint-mypy      - Run mypy type checker"
	@echo ""
	@echo "Formatting:"
	@echo "  make format         - Format all code"
	@echo "  make format-black   - Format with Black"
	@echo "  make format-isort   - Format with isort"
	@echo ""
	@echo "Build & Install:"
	@echo "  make install        - Install package in development mode"
	@echo "  make install-test   - Install with test dependencies"
	@echo "  make install-dev    - Install with all development dependencies"
	@echo "  make build          - Build distribution packages"
	@echo ""
	@echo "Database:"
	@echo "  make db-init        - Initialize database"
	@echo "  make db-doctor      - Check database health"
	@echo "  make db-stats       - Show database statistics"
	@echo "  make db-backup      - Create database backup"
	@echo "  make db-restore     - Restore database from backup"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          - Clean build artifacts and cache"
	@echo "  make clean-all      - Deep clean (includes __pycache__)"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs           - Generate documentation"

# Configuration
PYTHON ?= python
PYPROJECT ?= pyproject.toml
SRC_DIR ?= src
TEST_DIR ?= tests
DIST_DIR ?= dist
BUILD_DIR ?= build
COVERAGE_DIR ?= .coverage
DB_PATH ?= .memorycore/memorycore.db
BACKUP_PATH ?= .memorycore/backup/memorycore-$(date +%Y%m%d-%H%M%S).db

# Testing
test: test-quick

test-quick:
	$(PYTHON) -m pytest --ignore=tests/test_mcp.py -v

test-cov:
	$(PYTHON) -m pytest --ignore=tests/test_mcp.py --cov=src/memorycore --cov-report=html --cov-report=xml -v

test-watch:
	@echo "Watching for changes and running tests..."
	@echo "Install watchdog: pip install watchdog"
	watchmedo shell-command --patterns="*.py" --recursive --command='make test-quick' .

# Linting
lint: lint-black lint-isort lint-flake8 lint-mypy

lint-black:
	black --check $(SRC_DIR) $(TEST_DIR)

lint-isort:
	isort --check $(SRC_DIR) $(TEST_DIR)

lint-flake8:
	flake8 $(SRC_DIR) $(TEST_DIR)

lint-mypy:
	mypy $(SRC_DIR) $(TEST_DIR)

# Formatting
format: format-black format-isort

format-black:
	black $(SRC_DIR) $(TEST_DIR)

format-isort:
	isort $(SRC_DIR) $(TEST_DIR)

# Build and Install
install:
	$(PYTHON) -m pip install -e "."

install-test:
	$(PYTHON) -m pip install -e ".[test]"

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

build:
	$(PYTHON) -m build

# Database operations
db-init:
	$(PYTHON) -m memorycore.cli --db $(DB_PATH) init

db-doctor:
	$(PYTHON) -m memorycore.cli --db $(DB_PATH) doctor

db-stats:
	$(PYTHON) -m memorycore.cli --db $(DB_PATH) stats

db-projects:
	$(PYTHON) -m memorycore.cli --db $(DB_PATH) projects

db-backup:
	mkdir -p .memorycore/backup
	$(PYTHON) -m memorycore.cli --db $(DB_PATH) backup $(BACKUP_PATH)

db-restore: 
	@echo "Usage: make db-restore BACKUP=path/to/backup.db"
	@exit 1

db-restore-with-backup:
	$(PYTHON) -m memorycore.cli --db $(DB_PATH) restore $(BACKUP)

# Cleanup
clean:
	rm -rf $(DIST_DIR) $(BUILD_DIR) $(COVERAGE_DIR) *.egg-info

clean-all: clean
	rm -rf **/__pycache__ **/*.pyc .pytest_cache

# Documentation
docs:
	@echo "Generating documentation..."
	# Add documentation generation commands here

# Utility targets
compile:
	$(PYTHON) -m compileall $(SRC_DIR) $(TEST_DIR)

check:
	make lint
	make test

# Pre-commit hook simulation
pre-commit:
	make lint
	make test-quick
