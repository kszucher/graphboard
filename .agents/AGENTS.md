# Workspace Rules

These baseline guidelines apply to all development tasks in this repository.

## Architectural Rules
- **Documentation Maintenance**: **Always** read `README.md` to understand project constraints, architecture, and core data models before proposing or making changes. Keep `README.md` updated with key architectural changes, ensuring it remains token-efficient, high-density, and focused strictly on gotchas, non-standard behaviors, and design decisions (avoiding boilerplate directory maps or easily discoverable types).
- **State vs Visual Separation**: **Always** keep visual details (CSS rules, transitions, colors, opacity, interactive flags) inside the React components. **NEVER** calculate layout styles or visual flags inside layout calculation utilities or store them inside global store slices.
- **Challenge Function Signatures**: **Always** simplify function signatures through structural changes rather than code syntax improvements.
- **Code Cleanliness**: **Always** ensure no unused functions, imports, or variables remain in the code after modifications.

## Styling & Component Rules

### Frontend (frontend)
- **Prefer semantic elements** whenever possible.
- **Use Radix Tokens** for styling wherever possible, unless natural control requires bypassing it.

## Verification & Code Quality

### Backend (python-backend)
- **Always** use `uv` for executing commands and python tasks (e.g., `uv run pytest`, `uv run mypy app`, `uv run ruff check`).
- **Always** run linting and formatting commands after modifying Python source code.
- Format code and fix auto-fixable imports/lints before ending the task.
- **Always** ensure the backend code is fully formatted, clean of linter warnings/errors, and passes strict type checking (MyPy) with zero errors and zero warnings before completing the task.

### Frontend (frontend)
- **Always** run typecheck and build validation after modifying frontend source code.
- Run build verification using the local project build scripts (e.g., `npm run build`).
- **NEVER** try to open up a browser to validate UI functionality; the user will always handle visual validation.
- **NEVER** read or manually edit `schema.ts` or `openapi.json`. Always run the API generator (`npm run generate:api` in `frontend/`) to update frontend type schemas when API routes or structures change. To inspect data models token-efficiently, read the source Pydantic models directly in `python-backend/app/graphs/schemas.py`. Never commit `openapi.json` (untracked transient file).

