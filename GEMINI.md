# Agent Instructions

> Mirrored as `CLAUDE.md`, `AGENTS.md` and `GEMINI.md` — same rules apply in any AI environment.

---

## Architecture: 3 Layers

| Layer | Role | Location |
|---|---|---|
| **Directive** | What to do (SOPs in Markdown) | `directives/` |
| **Orchestration** | You — routing, decisions, error handling | — |
| **Execution** | Deterministic Python scripts | `execution/` |

**Why it works:** LLMs are probabilistic; business logic must be deterministic. Pushing complexity into scripts means you focus only on decision-making. At 90% accuracy per step, 5 chained steps yield only 59% success — deterministic code breaks that chain.

---

## Operating Principles

### Before acting
- Check `execution/` for existing scripts before writing new ones.
- Read the relevant directive before calling any tool.

### When something breaks (self-anneal)
1. Read the error and stack trace.
2. Fix the script and retest. *(If it consumes paid credits, ask the user first.)*
3. Update the directive with what you learned (API limits, edge cases, timing).
4. Confirm the fix works, then move on.

### Directives are living documents
Update them when you discover API limits, better approaches, or common errors. Don't create new directives or overwrite existing ones without user permission.

---

## File Structure

```
.tmp/           # Intermediary files (always regenerable — delete freely)
execution/      # Deterministic Python scripts
directives/     # Markdown SOPs
.env            # Env vars and API tokens
credentials.json / token.json  # OAuth (gitignored)
```

Local files are for processing only. Deliverables (Sheets, Slides, etc.) live in the cloud.

---

## Code Standards

### Style
- Functions: 4–20 lines. Split if longer.
- Files: under 500 lines. Split by responsibility.
- One responsibility per function and per module (SRP).
- Names must be specific. Avoid `data`, `handler`, `Manager`. Prefer names with <5 grep hits in the codebase.
- Types: always explicit. No `any`, no untyped functions.
- No duplication — extract shared logic into a function or module.
- Early returns over nested ifs. Max 2 levels of indentation.
- Exception messages must include the offending value and expected shape.

### Comments
- Write **WHY**, not WHAT. Skip `# increment counter` above `i += 1`.
- Preserve your own comments on refactors — they carry intent and provenance.
- Public functions get docstrings: intent + one usage example.
- Reference issue numbers or commit SHAs when a line exists because of a specific bug or upstream constraint.

### Tests
- Every new function gets a test. Bug fixes get a regression test.
- Tests run with a single command (project-specific).
- Mock external I/O (API, DB, filesystem) with named fake classes, not inline stubs.
- Tests must be **F.I.R.S.T**: fast, independent, repeatable, self-validating, timely.

### Dependencies & Structure
- Inject dependencies through constructor or parameter — not globals.
- Wrap third-party libs behind a thin interface owned by this project.
- Follow the framework's conventions (Rails, Django, Next.js, etc.).
- Predictable paths: `controller/model/view`, `src/lib/test`, etc.

### Formatting & Logging
- Use the language's default formatter (`black`, `prettier`, `gofmt`, `rustfmt`, etc.). Don't debate style beyond that.
- Structured JSON for debug/observability logs. Plain text only for user-facing CLI output.

---

## Summary

You sit between human intent (directives) and deterministic execution (Python scripts). Read instructions → make decisions → run tools → handle errors → improve the system. Be pragmatic. Be reliable. Self-anneal always.