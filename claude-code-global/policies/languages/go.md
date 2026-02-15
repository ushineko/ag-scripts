# Go Coding Standards

> **Policy module**: Activated via `## Selected Policies` in project `.claude/CLAUDE.md`.
> Apply these guidelines when writing new Go code or refactoring existing Go code.

---

## Project Structure
- `lib/` - Reusable, exported libraries with clean public APIs
- `internal/` - Internal implementation details (not exported outside the module)
- `cmd/` - CLI entry points (minimal main.go, delegate to packages)
- Platform-specific files: `*_windows.go`, `*_linux.go`, `*_darwin.go`
- Test files alongside source: `*_test.go`, `integration_test.go`

## Naming Conventions
- Interfaces: Do NOT prefix with `I` (use `DBManager`, not `IDBManager`)
- Avoid stuttering: `db.Manager` not `db.DatabaseManager`
- Exported (public): Capitalized (`CreateConnection()`)
- Unexported (internal): Lowercase (`openConnection()`)
- Helper implementations often unexported

## Error Handling
- Always wrap errors with context using `%w`: `fmt.Errorf("failed to initialize db: %w", err)`
- Use `errors.As()` for type assertion
- Define constant errors using custom `ConstError` type
- Return errors immediately, don't defer error checking
- Reserve `panic()` for truly unrecoverable initialization failures

## Testing
- Use `*_test.go` files alongside source
- Table-driven tests where appropriate
- Test helpers prefixed with underscore: `_testCreateConnection()`
- Run with race detector: `go test -race ./...`
- Use `testify/assert` for assertions
- Include panic recovery in tests that might panic
- Prefer testing through exported interfaces over mocking internal implementation (see core Test Philosophy)
- Use coverage to find untested critical paths, not as a metric to maximize

## Comments & Documentation
- Package-level comments using `/* ... */` block style
- Function comments for all exported functions
- Inline comments explain "why" not "what"
- Be factual and specific, no superlatives

## Concurrency
- `sync.WaitGroup` for goroutine synchronization
- Buffered channels for multi-producer scenarios
- `select` with channels for coordination
- `context.Context` for cancellation and timeouts
- `sync.Mutex` for shared state protection
- Singletons use `sync.Once` for initialization

## Dependency Injection
- Define interfaces for dependencies
- Use adapter pattern for flexibility
- Constructor functions: `func New(config *Config) (Interface, error)`
- Composition via embedded structs

## Globals and init()
**Globals** are acceptable but use sparingly:
- Always comment their purpose
- Prefer passing structs as state between calls when feasible
- Balance pros/cons and understand the tradeoffs before introducing a global
- If a different pattern works cleanly, prefer it over globals

**init()** is acceptable but use judiciously:
- Appropriate for module-level implicit initialization that can't be done cleanly otherwise
- Some libraries (e.g., Cobra) depend on it - follow their patterns
- For modules you control, avoid excessive use due to potential side effects
- Prefer explicit initialization functions when you have control over the call site

## Linting & Code Quality
- `golangci-lint` must pass before commits
- Line length: max 150 characters
- Cyclomatic complexity: max 25
- Cognitive complexity: max 50
- Document lint suppressions with rationale: `//nolint:gochecknoglobals // this is a singleton`

## Tooling
- Makefile with standard targets: `setup`, `lint`, `test`, `coverage`, `build`, `clean`
- `go.mod` and `go.sum` in version control
- Build-time version injection via generated `version.go`

## Logging
- Structured key-value logging (log15 style): `log.Info("message", "key", value)`
- Levels: Debug, Info, Warn, Error, Crit
- Never log sensitive data (credentials, tokens)

## Security
- Parameterized queries (never string concatenation for SQL)
- Safe process execution (args separate, not shell strings)
- Input validation on all external data
- Auth tokens encrypted at rest
- Use `//nolint:gosec` only with explanation

## Configuration
- Global config singleton with reload capability
- Mock config available for testing: `GetMock()`
- Viper for configuration management
- Cobra for CLI framework
