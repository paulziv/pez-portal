# `truage-core` — Private Repo + Build-Time PAT Setup

> How to stand up the shared package as a **private** GitHub repo that Railway can `pip install`
> at build time. One-time setup; unblocks Phase 1. No live-service code changes here.

## 1. Create the repo
- New **private** repo `paulziv/truage-core`.
- Minimal package skeleton:
  ```
  truage-core/
    pyproject.toml
    src/truage_core/__init__.py     # __version__ = "0.1.0"
    src/truage_core/…               # modules per truage-core-BLUEPRINT.md
    tests/
    README.md                       # seed from truage-core-BLUEPRINT.md
  ```
- `pyproject.toml` (build-system + name `truage-core`, package dir `src/`), so
  `pip install git+https://…` builds cleanly. Tag releases (`v0.1.0`).

## 2. Create the PAT
- GitHub → Settings → Developer settings → **Fine-grained PAT**.
  - Resource owner: `paulziv`; Repository access: **only** `paulziv/truage-core`.
  - Permission: **Contents: Read-only**. That's all pip needs.
  - Expiry: 90 days (calendar a rotation reminder).
- Copy the token (starts `github_pat_…`).

## 3. Store the PAT in Railway (shared, not per-service)
- In the **`nacs-portal` project → Variables (shared)**, add `TRUAGE_CORE_PAT = github_pat_…`.
- Reference it from each service that installs the package (portal + the two TruAge services)
  via Railway's `${{shared.TRUAGE_CORE_PAT}}` reference — one copy, not three.
- ⚠️ It's a credential: shared project variable only; never commit it; rotate on the PAT expiry.

## 4. Reference the package from each service
In each consuming service's `requirements.txt`:
```
truage-core @ git+https://${TRUAGE_CORE_PAT}@github.com/paulziv/truage-core@v0.1.0
```
- Pin the **tag** (`@v0.1.0`), not a branch — deploys become reproducible; bumps are deliberate.
- Railway expands `${TRUAGE_CORE_PAT}` from the service env at build time. (If a builder doesn't
  interpolate in requirements.txt, use a `pip.conf` / `PIP_INDEX`-style env or a tiny build step
  `pip install "git+https://${TRUAGE_CORE_PAT}@github.com/paulziv/truage-core@v0.1.0"` — same effect.)

## 5. Local dev install
```bash
export TRUAGE_CORE_PAT=github_pat_…          # in your shell profile, not the repo
pip install "git+https://${TRUAGE_CORE_PAT}@github.com/paulziv/truage-core@v0.1.0"
# or editable, working on core + a service together:
git clone https://github.com/paulziv/truage-core && pip install -e ./truage-core
```

## 6. Rotation
- On PAT expiry: mint a new fine-grained PAT (same scope), update `TRUAGE_CORE_PAT` in the Railway
  shared vars, redeploy. No code changes. Because it's one shared var, rotation is a single edit.

## Alternatives (if you'd rather not manage a PAT)
- **git submodule**: vendor `truage-core` into each repo at a pinned SHA; no token, but you update
  submodule pointers per repo. **Copy-vendor**: simplest, but you lose the single-source benefit.
  Recommendation stands: private repo + fine-grained PAT is the cleanest single-source option.
