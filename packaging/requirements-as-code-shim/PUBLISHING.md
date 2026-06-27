# Publishing the requirements-as-code redirect (one-time)

This is a **one-time, final** release of the old `requirements-as-code` PyPI
project. After it, the old name is frozen; all real engine releases go to
`rac-core`. The redirect keeps pointing at the latest `rac-core` forever via its
unpinned dependency floor — it never needs republishing when `rac-core` updates.
(Maintainer-facing — not shipped in the wheel.)

## Order of operations

1. **Publish `rac-core` first** (the normal release: tag → `python-publish.yml`).
   The redirect depends on `rac-core`, so it should exist on PyPI first.
2. **Confirm the version** in `pyproject.toml` is strictly greater than the last
   real `requirements-as-code` release (currently `2026.06.4`), so an unpinned
   `pip install requirements-as-code` resolves here. `2026.6.99` satisfies this
   and signals "final". Optionally tighten `dependencies` to
   `rac-core>=<first rac-core version>`.
3. **Publish** via the workflow below.

## Publish — Trusted Publishing via `publish-shim.yml` (no token)

1. On PyPI, register a Trusted Publisher on the **`requirements-as-code`** project
   (Manage → Publishing → Add a pending/trusted publisher → GitHub):
   - Owner: `itsthelore` · Repository: `rac-core`
   - **Workflow name: `publish-shim.yml`** · Environment name: `pypi`
   (Same shape as the `rac-core` publisher — different project + workflow.)
2. Run it once: **Actions → "Publish requirements-as-code shim" → Run workflow**
   (`workflow_dispatch`). It builds the metadata-only shim and uploads via OIDC.
3. **Verify:**
   ```bash
   python -m venv /tmp/shimcheck && /tmp/shimcheck/bin/pip install requirements-as-code
   /tmp/shimcheck/bin/rac --version   # comes from rac-core, pulled in transitively
   ```
4. **Delete the Trusted Publisher** you just added from the `requirements-as-code`
   project. This is a single final upload — removing it ensures nothing can ever
   publish to the old name again. (The `publish-shim.yml` workflow can stay in the
   repo, inert: with no trusted publisher it cannot upload.)

## Fallback — manual (token)

If you would rather not register a publisher:

```bash
cd packaging/requirements-as-code-shim
python -m build                 # metadata-only sdist + wheel
python -m twine upload dist/*   # username __token__, a PyPI token scoped to requirements-as-code
```
