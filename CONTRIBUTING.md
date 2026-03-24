# Contributing

To make contributions to this charm, you'll need a working
[development setup](https://documentation.ubuntu.com/juju/3.6/howto/manage-your-deployment/#set-up-your-deployment-local-testing-and-development).

## Testing

This project uses `tox` (with `tox-uv`) for managing test environments:

```shell
tox run -e format        # auto-fix lint + format (ruff)
tox run -e lint          # code style (ruff) + type checking (ty)
tox run -e unit          # unit tests with coverage
tox run -e integration   # integration tests (jubilant)
tox                      # runs 'lint' and 'unit' environments
```

## Build the charm

Build the charm in this git repository using:

```shell
charmcraft pack
```
