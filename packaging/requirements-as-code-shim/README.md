# requirements-as-code → **rac-core**

> **This package has been renamed.** `requirements-as-code` is now published as
> [`rac-core`](https://pypi.org/project/rac-core/).

```bash
pip install rac-core
```

The import package and CLI are unchanged — you still `import rac` and run `rac`.
Only the PyPI distribution name changed (see ADR-092).

This release of `requirements-as-code` is a **transitional redirect**: it contains
no code of its own and simply depends on `rac-core`, so existing
`pip install requirements-as-code` and CI keep working. It will not be updated
further — point new installs at `rac-core`.
