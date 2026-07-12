# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Enhanced error handling with custom exception classes
- Batch memory operations (`add_memories`, `get_memories`)
- Database backup and restore functionality
- Advanced FTS5 query building with phrase support
- Comprehensive input validation for all fields
- Project listing functionality
- Database statistics and health monitoring
- Event callbacks for memory operations

### Changed
- Improved database schema with additional indexes for better performance
- Enhanced CLI with more commands and better error handling
- Better logging throughout the codebase
- Improved type hints and documentation
- Enhanced memory model with helper methods

### Fixed
- Various edge cases in input validation
- Improved error messages for better debugging

## [0.1.0] - 2024-XX-XX

### Added
- Initial release of Memorycore v0.1
- SQLite database with FTS5 full-text search
- MemoryService for memory management
- CLI for database initialization and health checks
- Basic memory CRUD operations
- Project-scoped memory retrieval
- Memory archiving functionality
- Comprehensive test suite

### Changed
- N/A (Initial release)

### Fixed
- N/A (Initial release)

---

## Types of Changes

- **Added**: New features
- **Changed**: Changes in existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Vulnerability fixes
