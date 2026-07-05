# Contributing to Memorycore

Thank you for your interest in contributing to Memorycore! We welcome contributions from everyone.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/Memorycore.git
   cd Memorycore
   ```
3. **Set up a development environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```
4. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

## Development Workflow

### Making Changes

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the coding standards below

3. **Run tests and linting**:
   ```bash
   make test
   make lint
   ```
   Or use pre-commit:
   ```bash
   pre-commit run -a
   ```

4. **Commit your changes** with a clear, descriptive message:
   ```bash
   git commit -m "feat: add new memory type validation"
   ```
   
   We follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages:
   - `feat:` - A new feature
   - `fix:` - A bug fix
   - `docs:` - Documentation only changes
   - `style:` - Changes that do not affect the meaning of the code
   - `refactor:` - A code change that neither fixes a bug nor adds a feature
   - `perf:` - A code change that improves performance
   - `test:` - Adding missing tests
   - `chore:` - Changes to the build process or auxiliary tools

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Open a Pull Request** to the main repository

### Pull Request Guidelines

- **Title**: Clear and descriptive
- **Description**: Explain what your PR does and why it's needed
- **Tests**: Include tests for new functionality
- **Documentation**: Update documentation if needed
- **Breaking Changes**: Clearly mark any breaking changes

## Coding Standards

### Python Code

- **Formatting**: Use [Black](https://github.com/psf/black) for code formatting
- **Imports**: Use [isort](https://github.com/pycqa/isort) for import sorting
- **Linting**: Follow [flake8](https://flake8.pycqa.org/) guidelines
- **Type Hints**: Use type hints for all public functions and methods
- **Docstrings**: Follow [Google-style docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)

### Testing

- **Test Coverage**: Aim for high test coverage (80%+)
- **Test Files**: Place tests in the `tests/` directory
- **Test Naming**: Use `test_` prefix for test functions
- **Fixtures**: Use pytest fixtures for test dependencies

### Documentation

- **README**: Keep the README up to date
- **Docstrings**: All public functions should have docstrings
- **Examples**: Include usage examples in docstrings

## Reporting Issues

When reporting issues, please include:

1. **Python version** (`python --version`)
2. **Operating System**
3. **Steps to reproduce** the issue
4. **Expected behavior**
5. **Actual behavior**
6. **Relevant code snippets** (if applicable)

## Code Review Process

1. All PRs require at least one approval from a maintainer
2. CI checks must pass (tests, linting, etc.)
3. Code must follow the project's coding standards
4. Tests must be added for new functionality
5. Documentation must be updated if needed

## Release Process

Releases are managed by maintainers and follow semantic versioning:

- **Patch** (x.x.Z): Bug fixes and minor improvements
- **Minor** (x.Y.x): New features (backward compatible)
- **Major** (X.x.x): Breaking changes

### Release Checklist

- [ ] All tests pass
- [ ] Documentation is updated
- [ ] Changelog is updated
- [ ] Version is updated in `pyproject.toml`
- [ ] Git tag is created
- [ ] Package is published to PyPI

## Community

- **Discussions**: Use GitHub Discussions for questions and ideas
- **Issues**: Use GitHub Issues for bug reports and feature requests
- **Pull Requests**: Use GitHub Pull Requests for code contributions

## License

By contributing to Memorycore, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

Thank you for contributing to Memorycore! Your contributions help make this project better for everyone.
