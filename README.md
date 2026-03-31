# role-distributor

A Juju machine charm that acts as a central role distributor. The operator
provides a YAML mapping of models, applications, machines, and units via
config, and the charm resolves and publishes assignments to related
applications through the `role-assignment` interface.

## Quick Start

```bash
juju deploy ./role-distributor_*.charm
```

Configure role assignments:

```bash
juju config role-distributor role-mapping="$(cat <<'EOF'
my-model:
  microceph:
    machines:
      "0":
        roles: [control, storage, network]
        workload-params:
          region: us-east
      "1":
        roles: [storage, network]
    units:
      microceph/0:
        roles: [control, storage, gateway]
        workload-params:
          flavors: [rgw, s3]
EOF
)"
```

Schema:

```yaml
<model-name>:
  <application-name>:
    machines:
      <machine-id>:
        roles: [role1, role2]
        workload-params: {key: value}
    units:
      <application-name>/<unit-id>:
        roles: [role3]
        workload-params: {key: value}
```

Notes:

- Top-level keys are Juju model names.
- Under each model, keys are application names.
- `machines` and `units` are both optional, but each application must define at
  least one of them.
- Unit keys must be full unit names and must belong to the enclosing
  application.
- `roles` are required for each machine or unit entry.

Resolution rules:

- Machine-level config applies to units that report a matching `machine-id`.
- Unit-level `roles` fully replace machine-level `roles`; they are not merged.
- `workload-params` are shallow-merged: machine-level values are the base, and
  unit-level values override matching keys.
- Units with no matching machine-level or unit-level entry remain pending.

Integrate with a requirer charm:

```bash
juju integrate role-distributor:role-assignment microceph:role-assignment
```

## Development

```bash
uv sync --group dev --group test
pre-commit install
tox run -e format        # auto-fix lint + format (ruff)
tox run -e lint          # code style (ruff) + type checking (ty)
tox run -e unit          # unit tests with coverage
tox run -e integration   # integration tests (jubilant)
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
