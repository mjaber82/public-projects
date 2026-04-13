# Contribution Guide

Welcome to the project! This guide outlines the development workflow, Git conventions, and pre-commit hooks setup to ensure a smooth contribution process.

---

## Table of Contents

1. [Development Workflow](#development-workflow)
2. [Git Commit Conventions](#git-commit-conventions)
3. [Pre-Commit Hooks Setup](#pre-commit-hooks-setup)

---

## 1. Development Workflow

Follow these steps when contributing to the repository:

1. **Create a new branch** for your work:
   ```bash
   git checkout -b feature/short-description
   ```
2. **Make changes and commit** following the Git conventions.
3. **Push your branch** to the remote repository:
   ```bash
   git push origin feature/short-description
   ```
4. **Create a Pull Request (PR)** targeting the `main` branch.
5. **Request reviews** from the maintainers.
6. **Ensure all checks pass** before merging.

---

## 2. Git Commit Conventions

We follow the [Conventional Commits](https://www.conventionalcommits.org/) standard. Use the following format:

```
<type>(<scope>): <short description>

[optional body]

[optional footer(s)]
```

### Common Types:

- **feat**: A new feature
- **fix**: A bug fix
- **docs**: Documentation updates
- **style**: Code style changes (no functional changes)
- **refactor**: Code refactoring (no new features or bug fixes)
- **test**: Adding or modifying tests
- **chore**: Maintenance tasks (e.g., dependency updates)

### Examples:

```bash
git commit -sm "feat(auth): add JWT authentication"
git commit -sm "fix(database): resolve connection timeout issue"
git commit -sm "docs(readme): update setup instructions"
```

---

## 3. Pre-Commit Hooks Setup

To maintain code quality, set up **pre-commit hooks**:

1. Install `pre-commit`:

   ```bash
   pip install pre-commit
   ```

2. Install hooks for this repository:

   ```bash
   pre-commit install
   ```

3. Install Gitlint for commit message validation:

   ```bash
   pip install gitlint
   ```

4. Install Gitlint pre-commit hook:
   ```bash
   pre-commit install --hook-type commit-msg
   ```

### Running Pre-Commit Manually

To check files before committing:

```bash
pre-commit run --all-files
```

By following these guidelines, we ensure a clean and consistent codebase. Happy coding!
