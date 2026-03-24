# role-distributor

A Juju machine charm that acts as a central role distributor. The operator
provides a YAML mapping of machines and units to roles via config, and the
charm resolves and publishes assignments to all related applications through
the `role-assignment` interface.

## Quick Start

```bash
juju deploy ./role-distributor_*.charm
```

Configure role assignments:

```bash
juju config role-distributor role-mapping="$(cat <<'EOF'
machines:
  "0":
    roles: [control, storage, network]
    workload-params:
      microceph:
        flavors: [rgw]
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

Integrate with a requirer charm:

```bash
juju integrate role-distributor:role-assignment microceph:role-assignment
```

## Development

```bash
uv sync --group dev --group test
pre-commit install
tox -e lint     # ruff + ty
tox -e unit     # pytest + coverage
tox -e format   # auto-fix
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
