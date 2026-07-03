# `truage-core` — Shared Library Blueprint (Phase 1)

> Design for the shared package that ends the drift between the two TruAge report backends.
> **Blueprint only — no live-repo changes.** Grounded in the current code: signatures below map
> 1:1 to symbols that exist today in `truage-activity-report`, `truage-pulse`, and `pez-portal`.
> `truage-core` holds **primitives** (HubSpot access, KPI constants, test rules, email, logging,
> run/error records). It does NOT hold report logic — each report keeps its own compute module.

## Distribution & versioning

- Ship as a pip-installable package `paulziv/truage-core`, pinned by tag in each service's
  `requirements.txt`:
  `truage-core @ git+https://github.com/paulziv/truage-core@v0.1.0`
- **Private-repo install on Railway:** add a build-time `GITHUB_TOKEN` (or deploy key) and use
  `git+https://${GITHUB_TOKEN}@github.com/paulziv/truage-core@v0.1.0`. Alternatives if you'd rather
  not manage that: a **git submodule** vendored into each repo, or copy-vendor with a version stamp.
  Recommendation: private repo + PAT — it keeps one canonical source and clean version pins.
- SemVer tags; services pin exact tags and bump deliberately. Rollback = re-pin previous tag.

## Package layout

```
truage_core/
  __init__.py            # __version__
  config.py              # canonical org/pipeline constants (the KPI "dials")
  testrecords.py         # the two test-record rules, one place
  hubspot/
    client.py            # unified HubSpotClient (fail-loud retry) + get_client()
    pull.py              # high-level pulls (deals, stores, stage labels)
  email.py               # Resend wrapper (one provider)
  logging.py             # structlog config + correlation-id helpers/middleware
  runlog.py              # shared run_history + error_log (writes to shared Postgres)
  reportapp.py           # (Phase 4) FastAPI report skeleton + standalone-HTML export
  cache.py               # (transitional) in-proc cached(); retired when portal owns cache (Phase 5)
```

---

## `truage_core.config`

Canonical constants (today duplicated across both repos). Pure data — adopt first, zero risk.

```python
PIPELINE_ID: str = "default"
STORE_OBJECT_TYPE: str = "2-48839355"
GOAL: int = 25_000
GOAL_DATE: datetime  # 2026-12-31 UTC

STAGE_ROLES: dict          # active_stage_ids + in_lab/awaiting_sw/awaiting_activation/
                           # awaiting_transactions/onboarding stage IDs
EARLY_FUNNEL_STAGES: set[str]
DEAL_PROPERTIES: list[str]
STORE_PROPERTIES: list[str]

AM_OWNER_IDS: dict[str, str]        # 79423140 Eddie McFarlane, 87813531 Megan Terry, 1367430633 Lisa Rountree
INACTIVE_OWNER_IDS: dict[str, str]  # 79761095 Grant Bleecher, 1285253947 Bryan Esser
OTHER_OWNER_IDS: dict[str, str]     # 87367233 Patrick, 89184631 Lia, 78438676 Stephanie
```

Replaces: `fetch_from_hubspot.py` (`STAGE_ROLES`, `STORE_OBJECT_TYPE`, `DEAL_PROPERTIES`,
`STORE_PROPERTIES`, `PIPELINE_ID`), `generate_report_html.py` (`GOAL`, `GOAL_DATE`,
`EARLY_FUNNEL_STAGES`), and `pulse/audit/data.py` (`AM_OWNER_IDS`, `INACTIVE_OWNER_IDS`,
`OTHER_OWNER_IDS`). Longer term these become editable via the portal admin (they're already
"rarely-changing org constants" per the pulse code).

## `truage_core.testrecords`

```python
def is_test_deal(name: str) -> bool: ...
    # name-based: TEST_EXACT_NAMES + TEST_SUBSTRING_PATTERNS
def is_test_store(store: dict) -> bool: ...
    # field-based: (store.get("is_test_data") or "").lower() == "true"  — NEVER name-matched
```

Replaces: `Deal.is_test_record()` + the `TEST_*` constants in `generate_report_html.py`, and
`is_test_store()` in `generate_report_html.py`. Single definition kills the exclusion-drift that
caused the 9,949-vs-9,839 reconciliation bug.

## `truage_core.hubspot.client`

One client with the fail-loud retry policy (the 2026-07-01 fix), superseding both ad-hoc clients.

```python
class HubSpotError(Exception): ...

class HubSpotClient:
    def __init__(self, token: str | None = None, *, timeout: int = 30): ...
    def _request(self, method, path, *, json_body=None, label="", **kw) -> dict: ...
        # 200 → json; 429 → respect Retry-After else exp backoff+jitter;
        # 5xx/network → backoff+jitter; other 4xx → raise immediately;
        # exhausts MAX_RETRIES → raise (NEVER returns None/empty)
    def search(self, object_type, filter_groups, properties,
               sorts=None, limit=200, after=None) -> dict: ...
    def search_all(self, object_type, filter_groups, properties,
                   sorts=None, page_size=200, pace_seconds=0.15) -> list[dict]: ...
        # auto-paginate with inter-page pacing
    def get_pipeline_stages(self, pipeline_id="default") -> dict[str, str]: ...  # id → label
    def list_owners(self) -> list[dict]: ...
    def owner_by_id(self, owner_id) -> dict | None: ...
    def get_associations(self, ...) -> ...: ...
    def batch_read_associations(self, ...) -> ...: ...
    def batch_read_objects(self, ...) -> ...: ...

def get_client(token: str | None = None) -> HubSpotClient: ...
    # token resolution order: explicit arg → HUBSPOT_TOKEN → HUBSPOT_PRIVATE_APP_TOKEN
    # (same underlying private app; fallback keeps pulse working until the Railway var is renamed)
```

Replaces:
- activation `fetch_from_hubspot.py`: `_request_with_retry`, `hs_post`, `hs_get`,
  `fetch_stage_labels` (→ `get_pipeline_stages` + validation in `pull.py`).
- pulse `pulse/hubspot_client.py`: the whole module (`HubSpotClient`, `_request`, `search`,
  `list_owners`, `owner_by_id`, `get_associations`, `batch_read_associations`,
  `batch_read_objects`, `get_client`, `HubSpotError`).

Note: pulse's `_request` retries 3× on 429 but did NOT fail loud the way activation's does — this
unification upgrades pulse to the safer policy.

## `truage_core.hubspot.pull`

High-level pulls that validate stage roles and exclude nothing (callers decide bucketing).

```python
def fetch_stage_labels(client, pipeline_id="default") -> dict[str,str]: ...
    # pulls live labels AND validates every STAGE_ROLES id exists → else raises (fail loud)
def fetch_all_deals(client, *, pipeline_id="default", properties=None) -> list[dict]: ...
def fetch_all_stores(client, *, object_type=STORE_OBJECT_TYPE, properties=None) -> list[dict]: ...
```

Replaces activation `fetch_from_hubspot.py`: `fetch_all_deals`, `fetch_all_stores`,
`fetch_stage_labels`, `summarize_stores`. (`write_pull`/`main` stay in the activation service — or
disappear once it computes in-process in Phase 3.)

## `truage_core.email`

```python
def send(to, subject, html_body, text_body=None, *, from_email=None) -> dict: ...
    # Resend; no-op (logs) without RESEND_API_KEY; default from = RESEND_FROM / portal@dashboard.mytruage.org
```

Replaces: pulse `pulse/email.py` (Postmark → Resend, Phase 6), activation `alerting.py`'s Resend
call, and becomes the primitive the portal's `app/email_service.py::send_report(...)` wraps.

## `truage_core.logging`

```python
def configure_logging(level: str = "INFO") -> None: ...     # structlog JSON, one format everywhere
def get_logger(name: str): ...
REQUEST_ID_HEADER = "X-Request-ID"
def bind_request_id(rid: str) -> None: ...                  # structlog contextvars
def new_request_id() -> str: ...
class RequestIDMiddleware:  # FastAPI/ASGI: read-or-mint X-Request-ID, bind, echo on response
    ...
def outgoing_headers() -> dict: ...   # {"X-Request-ID": <current>} to forward on proxied calls
```

Adoption (Phase 2): portal mints/propages the ID on every proxied call + cron fan-out
(`app/routers/truage_activation`, `truage_account`, `run_daily`); backends install the middleware
and log with it. Replaces the stdlib `logging.basicConfig` blocks in both TruAge `app.py` files and
matches portal/990's existing structlog.

## `truage_core.runlog`

Shared run/error history in the shared Postgres (svc `6b0771a2`), written by ALL TruAge services.

```python
def init_tables() -> None: ...
def record_run(service, report, status, *, duration_s=None,
               correlation_id=None, step=None, error=None) -> None: ...
def recent_runs(limit=50, *, service=None, report=None) -> list[dict]: ...
def record_error(service, source, message, *, traceback_text=None, correlation_id=None) -> None: ...
def recent_errors(limit=50, *, service=None) -> list[dict]: ...
```

Replaces: activation `run_history.py` (`record_run`, `recent_runs`, `_ensure_table`) and pulse
`pulse/storage.py` (`record_error`, `get_recent_errors`) — folded into one schema keyed by
`service` + `correlation_id`. The portal ops page (`app/static/ops.html` + a new `/api/ops` route)
reads `recent_runs`/`recent_errors` across all services — replacing per-service `/history` + `/errors`.
(pulse's settings/rules/score helpers — `get_setting`, `list_rules`, `record_score`, etc. — stay in
pulse; they're audit-specific, not shared.)

## `truage_core.reportapp` (Phase 4) & `cache` (transitional)

```python
# reportapp.py — the shared FastAPI skeleton (loading shell, /health, /errors, standalone export)
def build_report_router(*, slug, title, compute, template) -> APIRouter: ...
def to_standalone_html(html: str) -> str: ...     # from pulse/export.py
def report_filename(report_name: str) -> str: ... # from pulse/export.py::filename_for

# cache.py — pulse's cached(ttl) decorator, moved as-is BUT marked transitional:
# retire from backends in Phase 5 when the portal's Postgres report_cache becomes the only cache.
```

Replaces (Phase 4): pulse `pulse/export.py` (`to_standalone_html`, `filename_for`) and the
loading-shell HTML currently inline in `pulse/app.py`; gives activation the same skeleton.

---

## What deliberately STAYS per service (the two reports remain distinct)

- **Activation Report** (`truage-activity-report`): `generate_report_html.py` compute — `Deal`,
  `compute_metrics()`, `load_data()`, `render_html()` and the page builders. It *uses*
  `truage_core` for the client, constants, test rules, email, logging, runlog.
- **AM Audit** (`truage-pulse`): `pulse/audit/{data,analysis,score}.py`, `pulse/dictionary/`,
  `pulse/daily/`, templates, and settings/rules storage. Same — uses `truage_core` primitives.
- **Portal**: `app/daily_cache.py`, `app/report_tokens.py`, `app/auth.py`, `APP_REGISTRY`/`USER_ROLES`
  stay; `email_service.send_report` becomes a thin wrapper over `truage_core.email.send`.

## Call-site replacement map (quick reference)

| Today | → `truage_core` |
|---|---|
| `fetch_from_hubspot._request_with_retry/hs_post/hs_get` | `hubspot.client.HubSpotClient._request` |
| `fetch_from_hubspot.fetch_all_deals/stores/stage_labels` | `hubspot.pull.*` |
| `pulse/hubspot_client.py` (whole module) | `hubspot.client` |
| `generate_report_html` `STAGE_ROLES/GOAL/EARLY_FUNNEL_*` + `fetch_*` `DEAL/STORE_PROPERTIES` | `config` |
| `generate_report_html.Deal.is_test_record` + `is_test_store` + `TEST_*` | `testrecords` |
| `pulse/audit/data.AM_OWNER_IDS/INACTIVE_OWNER_IDS/OTHER_OWNER_IDS` | `config` |
| `pulse/email.send` (Postmark) + `alerting.send_crash_alert` email | `email.send` (Resend) |
| activation `run_history.*` + pulse `storage.record_error/get_recent_errors` | `runlog` |
| both `app.py` `logging.basicConfig` | `logging.configure_logging` + `RequestIDMiddleware` |
| pulse `export.to_standalone_html/filename_for` + inline loading shell | `reportapp` (Phase 4) |

## Phase-1 adoption order (each step independently shippable, char-tested)

1. **`config`** — import in both services; delete local constant copies. (Pure data; no behavior change.)
2. **`testrecords`** — swap both services' test logic; snapshot-diff each report's metrics on a fixed pull.
3. **`hubspot.client` + `hubspot.pull`** — swap activation's `fetch_*` and pulse's `HubSpotClient`;
   diff the pull JSON and rendered metrics before/after. Set one Railway `HUBSPOT_TOKEN` shared var.
4. **`runlog` + `logging`** — land with Phase 2 (needs the shared tables + correlation ID).
5. **`email`** — land with Phase 6 (pulse → Resend).
6. **`reportapp`/`cache`** — land with Phases 4–5.

**Char-test harness (build once, reuse every step):** given a saved `hubspot_pull.json`, render each
report and capture (a) the metrics dict and (b) the HTML; assert identical across the refactor. This
is the gate that lets us move plumbing under two live reports without changing what they show.

## `truage-core` v0.1.0 scope (suggested first tag)
`config` + `testrecords` + `hubspot.client` + `hubspot.pull`, with unit tests for the retry policy
(429/5xx/4xx/exhaustion), `is_test_deal`/`is_test_store`, and stage-role validation. Everything else
lands in later tags aligned to the migration phases.
