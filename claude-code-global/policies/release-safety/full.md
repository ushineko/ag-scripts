# Release Safety: Full

> **Policy module**: Activated via `## Selected Policies` in project `.claude/CLAUDE.md`.
> Comprehensive release safety practices for production services with databases, APIs, and infrastructure.

---

## Core Principle

AI coding tools let us produce more change per day. That increases release risk unless we build in reversibility.

**The question every release must answer:**
> "If this causes pain, can we undo it in minutes without data heroics?"

---

## Parallel Change: Expand, Migrate, Contract

Break risky changes into phases that stay compatible while different versions coexist:

| Phase | Action | Reversibility |
|-------|--------|---------------|
| **Expand** | Add new things without removing old ones | Full - just don't use new code |
| **Migrate** | Backfill and dual-write, then switch reads | Full - flip back to old reads |
| **Contract** | Remove old paths after confidence is established | Reduced - plan carefully |

**Key insight**: Changes stay additive during Expand and Migrate. Rollback becomes expensive only in Contract phase.

## Feature Flags for Release Control

Deploy code, then control exposure separately:
- **Deploy** = code is in production (can be instant)
- **Release** = behavior is enabled (can be gradual)

Use flags for:
- Behavior changes on existing endpoints
- Risky migrations during the Migrate phase
- Progressive rollout (internal → pilot → general)

---

## Stack-Specific Guidance

### APIs (DRF/FastAPI/GraphQL)
- **Add fields, don't rename/remove in-place**. Ship old and new together until migration is complete.
- **Behavior changes require a flag**. Same endpoint, two behaviors, one rollback lever.
- **Version only when contracts must diverge**. Otherwise, control exposure with flags.

### PostgreSQL / Database Migrations
- **Expand**: Add nullable columns, additive tables, use `CREATE INDEX CONCURRENTLY`
- **Migrate**: Backfill in batches, dual-write briefly, switch reads behind a flag
- **Contract**: Enforce constraints later, deprecate later, remove later (or never)

### Elasticsearch / Search Indices
- Mappings often can't be changed in place - treat indices as versions
- Create new versioned index → Reindex → Switch with alias
- Rollback = flip alias back

### Kubernetes / Container Deployments
- Release in rings: internal → pilot tenants → broader cohorts
- Canary or blue-green for high-risk changes
- Document the rollback lever: flag off, rollout undo, alias flip

---

## Concrete Example: Rename a Field

Want to rename `old_name` to `new_name`:

1. **Expand**: Add `new_name` nullable, return both in API, UI reads old field
2. **Migrate**: Dual-write, backfill, flip reads behind flag (internal → pilot)
3. **Contract**: Stop dual-write, deprecate old field in future release

**Rollback at any point**: Flip the flag off - old path still works.

---

## Phase 5.5 Detailed Checklists

### For Schema/Database Changes
- [ ] Uses Expand-Migrate-Contract pattern (or justified exception)
- [ ] New columns are nullable or have safe defaults
- [ ] Indexes created with `CONCURRENTLY` where supported
- [ ] Backfill strategy defined for data migrations
- [ ] Rollback path documented

### For API Changes
- [ ] Additive only (no breaking removals in same release)
- [ ] Behavior changes behind feature flag (if applicable)
- [ ] Backward compatible with existing clients
- [ ] Rollback = disable flag or revert deploy

### For Search/Index Changes
- [ ] Using versioned indices with alias strategy
- [ ] Rollback = flip alias to previous index

### For Infrastructure/Deployment
- [ ] Rollout rings defined (internal → pilot → general)
- [ ] Rollback lever documented (flag, undo, alias flip)
- [ ] No shared state that prevents independent rollback

---

## Rollback Plan Documentation

Every change must have an answer to: "How do we undo this in minutes?"

| Change Type | Rollback Approach |
|-------------|-------------------|
| Code-only | Revert commit, redeploy |
| Feature flag | Disable flag |
| Schema (Expand phase) | Ignore new columns |
| Schema (Migrate phase) | Flip reads to old path |
| Schema (Contract phase) | May require restore - document carefully |
| Index change | Flip alias |
