# Install the `rac` CLI

The RAC extension is a thin client — it runs your local `rac` CLI and never
reimplements its analysis. So the first step is to make `rac` available.

**Recommended (isolated):**

```sh
pipx install requirements-as-code
```

or with pip:

```sh
pip install requirements-as-code
```

Already have `rac` somewhere specific? Set its path in **`rac.path`** instead.

Once `rac` is on your `PATH` (or `rac.path` is set), the extension validates RAC
artifacts as you open and save them.
