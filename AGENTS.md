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

- All error codes and messages use `ErrorCode` enum (`app/enums.py`), never raw strings
- All domain data uses Pydantic models or dataclasses, never raw dicts
- All configuration values (rate limits, TTLs, timeouts, feature flags, search defaults, FTS parameters) use `app/config.py` `Settings`, never hardcoded literals
- Every module, class, and function/method must have a concise Google-style docstring describing its purpose, Args (for methods with params), and Returns (for methods that return a value)

