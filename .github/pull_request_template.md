## What does this PR do?

<!-- One paragraph. Link to the related issue or blog post if applicable. -->

## Type of change

- [ ] Bug fix
- [ ] New feature (post-N implementation)
- [ ] Refactor / cleanup
- [ ] CI/CD / tooling
- [ ] Documentation

## Checklist

- [ ] All existing tests pass (`pytest` / `npm test`)
- [ ] New code has tests — coverage did not drop
- [ ] Architecture rules followed (see [ARCHITECTURE.md](../ARCHITECTURE.md)):
  - [ ] No `chromadb` import outside `rag/store.py`
  - [ ] Service functions receive dependencies as arguments (no new module-level singletons)
  - [ ] Extension: no `fetch()` calls outside `DhiClient`
- [ ] `ruff` and `mypy` pass with no new errors
- [ ] `tsc --noEmit` passes for any TypeScript changes
- [ ] Docker image builds cleanly (`docker build server/`)

## Testing notes

<!-- How did you test this? What edge cases did you consider? -->

## Blog post reference (if applicable)

<!-- Post number and title this implements, e.g. "Post 2 — Repository Intelligence" -->
