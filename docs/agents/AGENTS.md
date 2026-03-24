# Agent guidance

## Tech Stack

- **Python 3.12**, Juju machine charm using the **ops** framework
- **pyyaml** for config parsing
- **ruff** + **ty** for linting/type-checking, **pytest** + **coverage** for tests
- **jubilant** for integration tests against live Juju models
- **charmcraft** (uv plugin) for building `.charm` artifacts

## Commands

```bash
tox -e lint              # ruff check + format check + ty
tox -e format            # auto-fix lint + format
tox -e unit              # unit tests with coverage (80% threshold)
tox -e integration       # integration tests (requires juju + built charms)
tox -e build-dummy       # build the dummy-requirer test charm

# Single test
PYTHONPATH=lib:src pytest tests/unit/test_charm.py::TestCharm::test_name -v

# Build the charm
charmcraft pack
```

## Architecture

Three layers with clear separation:

1. **`src/charm.py`** — Charm framework layer. `RoleDistributorCharm` funnels all events into `_reconcile()`, which parses config, computes assignments, and publishes them. Only the leader writes to relation databags.

2. **`src/role_distributor.py`** — Framework-agnostic business logic. `parse_config()` validates YAML into typed dataclasses. `compute_assignments()` resolves per-unit roles following precedence: unit-level roles fully override machine-level; workload-params shallow-merge (machine base scoped by app name, unit overrides keys).

3. **`lib/charms/role_distributor/v0/role_assignment.py`** — Interface library shared with requirer charms. Defines `RoleAssignmentProvider`/`RoleAssignmentRequirer` and data classes (`UnitRoleAssignment`, `RegisteredUnit`). The lib does NOT write `machine-id` — that's the requirer charm's responsibility.

## Conventions

- Specs go in `docs/agents/specs/`
- Implementation plans go in `docs/agents/plans/`
- No date/timestamp prefixes in filenames

## Git Commit Attribution

When creating commits, use the `Assisted-by` trailer instead of `Co-Authored-By`. Format:
```
Assisted-by: <harness> (<model>)
```
Example:
```
Assisted-by: Claude Code (claude-opus-4-6)
```

Do NOT use `Co-Authored-By`, that trailer is meant for human co-authors, not tools.

Do NOT add `Signed-off-by` trailers. Only the human reviewer signs off on commits. This is enforced in CI.

Place the `Assisted-By` trailer at the end of the commit message, separated by a blank line from the body.

## Goals

- Robust cross-model role distribution: the charm must work reliably across Juju model boundaries via `juju offer`/`juju consume`
- 100% unit test coverage on `src/role_distributor.py` (pure logic, no side effects)
- Integration tests covering the full relation lifecycle: assignment, override, scale-up, and relation removal
