# Agent Rules (local)

- Update `PROGRESS.md` after each build step.
- Requirements are listed in `REQUIREMENTS.md`
- Application specs are defined in `SPEC.md`
- We will put our high level design in `DESIGN.md`

## Testing

- Always rebuild Docker containers (`docker compose up -d --build`) before running checks to ensure the latest code is deployed.

## When Stuck

- Ask one focused clarifying question.
- Propose a short execution plan.
- Document assumptions and tradeoffs clearly.

## Conventions

### Typing (strict)

- **All status/type/kind values** must be defined as `str` enums in a dedicated enums module. Never use raw string literals (e.g. `"create"`, `"pending"`, `"admin"`) as parameters, return values, or comparison targets. Use the enum member directly.
- **All domain data** must be typed with a schema/model library (Pydantic, dataclass, TypedDict, etc.) — never raw dicts. In particular:
  - Message payloads (Kafka, SQS, etc.) must be deserialized via a model's validation method, never via `.get()` access on a raw dict.
  - API request/response bodies, query builders, and cache values must use typed models, not bare `{...}` literals.
  - Repository/internal layer methods may return dicts only for transient DB row conversion; all public return types must be models.
- **All function signatures** must use concrete types, not `str`, `dict`, or `Any` where a more specific type exists.
- **All configuration values** (rate limits, TTLs, timeouts, feature flags, external service URLs/credentials) must come from a centralized settings/config object, never hardcoded as literals.

### Code quality

- Every module, class, and function/method must have a concise docstring describing its purpose, Args (for methods with params), and Returns (for methods that return a value).
- Unused imports must be removed immediately; never leave dead imports behind.

