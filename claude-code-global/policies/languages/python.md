# Python Coding Standards

> **Policy module**: Activated via `## Selected Policies` in project `.claude/CLAUDE.md`.
> Apply these guidelines when writing new Python code or refactoring existing Python code.

---

## Key Principles
- Prioritize readability over efficiency
- Use functional programming where appropriate; avoid unnecessary classes
- Use descriptive variable names that reflect the data they contain or their purpose (e.g., `is_active`, `has_permission`)
- Use descriptive function names
- Use the Receive an Object, Return an Object (RORO) pattern where it makes sense
- Keep functions under 10 statements
- Avoid introducing new global state; prefer dependency injection
- Avoid functions/methods with more than 5 parameters; group them when more are needed
- Code should read from top to bottom, with descriptive function and variable names

## Style and Syntax
- Target Python >=3.12
- Follow PEP 8 style guidelines with 120-character line limit
- Use `def` for pure functions and `async def` for asynchronous operations
- Do not write comments beyond docstrings unless complex design patterns or algorithms are used
- Use type hints for all function signatures; prefer `list` over `List` and `dict` over `Dict`
- Prefer Pydantic models over raw dictionaries for input validation
- Avoid complex conditional logic in list comprehensions; avoid nested list comprehensions

## Tooling & Libraries
- Use `pyproject.toml` for project configuration
- Use `uv` for packaging
- Use `ruff` for linting
- Use `pytest` for testing with `pytest-cov` for coverage
- Use Pydantic v2 for data modeling
- Create a Makefile with aliases for build, test, and run operations

## Error Handling
- Implement data quality checks at the beginning of analysis
- Handle missing data appropriately (imputation, removal, or flagging)
- Use try-except blocks for error-prone operations, especially when reading external data
- Validate data types and ranges to ensure data integrity
- Handle errors and edge cases at the beginning of functions
- Use early returns for error conditions to avoid deeply nested if statements
- Place the happy path last in the function for improved readability
- Avoid unnecessary else statements; use the if-return pattern instead
- Use guard clauses to handle preconditions and invalid states early
- Implement proper error logging and user-friendly error messages
- Use custom error types or error factories for consistent error handling

## Testing
- Place `tests/` at the same level as the files they test
- Leverage pytest markers declared in `pyproject.toml` (unit, integration, slow, performance)
- Mark long-running or network-dependent flows to keep CI lean
- Maintain coverage by extending fixtures and factories in `tests/fixtures/`
- Name tests following `test_unit_<name_file>.py` or `test_integration_<capability>.py` pattern
- Test error handling and edge cases
- Prioritize behavioral contracts over implementation-coupled tests (see core Test Philosophy)
- Use coverage as a diagnostic for gaps in critical paths, not as a target to maximize
- Prefer integration tests with real collaborators over heavily-mocked unit tests where practical

## Documentation
- Add a README.md explaining project architecture, build, test, and run instructions

## Data Analysis (when applicable)
- Use pandas for data manipulation and analysis
- Prefer method chaining for data transformations when possible
- Use `loc` and `iloc` for explicit data selection
- Utilize groupby operations for efficient data aggregation

## Visualization (when applicable)
- Use matplotlib for low-level plotting control and customization
- Use seaborn for statistical visualizations and aesthetically pleasing defaults
- Create informative plots with proper labels, titles, and legends
- Use appropriate color schemes and consider color-blindness accessibility

## Performance Optimization
- Use vectorized operations in pandas and numpy for improved performance
- Use efficient data structures (e.g., categorical data types for low-cardinality string columns)
- Consider using dask for larger-than-memory datasets
- Profile code to identify and optimize bottlenecks
