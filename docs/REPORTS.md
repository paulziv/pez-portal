# Reports & KPIs — Definitions and Gotchas

> Cross-cutting reference for every report in the TruAge/NACS ecosystem: what each
> KPI measures, where its data comes from, and the definitional subtleties that bite.
> Companion to `docs/ARCHITECTURE.md`. Last verified against code: **2026-07-02**.

The reports live in three backend services and are surfaced (proxied or linked) through
the Innovation Portal (`dashboard.mytruage.org`):

| Report | Backing repo | Railway service | How portal shows it |
|---|---|---|---|
| TruAge Activation Report | `truage-activation-report` | `nacstar` | proxied (`/apps/truage-activation/`) |
| AM Assignment Audit | `truage-pulse` | `nacstam` | proxied (`/apps/truage-account/`) |
| Daily Sales Pulse *(stub)* | `truage-pulse` | `nacstam` | (not yet live) |
| HubSpot Data Dictionary | `truage-pulse` | `nacstam` | external link `/dictionary` |
| BenchPoint (990 benchmarking) | `nacs-990-benchmark` | `nacs-990-benchmark` | external card |
| C-Store Intel (market BI) | `convenience-store-intel` | `cstore-*` | external card |

---

## 1. TruAge Activation Report  (`truage-activation-report` → `nacstar`)

Weekly KPI + forecast report tracking convenience stores going live on TruAge, against a
goal of **25,000 stores by Dec 31, 2026** (`GOAL = 25_000` — the *only* hardcoded number;
everything else is computed from the HubSpot pull).

### Two HubSpot data sources — and why the numbers disagree
1. **Deals** — the `Retailer Activations` pipeline (`pipeline=default`). Deal **`amount`
   is used as a store count, not dollars.**
2. **Stores** — the custom **Stores** object (`STORE_OBJECT_TYPE = "2-48839355"`), with a
   `status` field (Active/Pending/Ready/…). This is *operational truth*.

Sales-side (deal amounts) and ops-side (store status) diverge because deal Amount fields
aren't updated when a store actually activates. The report treats **Store status as
authoritative** and surfaces the gap as a data-quality flag.

### ⭐ The two definitions of "Active" (the headline gotcha)
`M["active_stores"]` (the number every other figure keys off) is chosen as:
- **`active_stores_real`** = count of **Store** records with `status == "Active"` (test
  records excluded). **Used whenever store data is present** — this is the real number.
- **`active_stores_deals`** = sum of **deal `amount`** in the `closedwon` stage (test
  excluded). **Fallback only**, used when there is no store data.

They disagree by design (deal amounts lag activation). The report's data-quality panel
explicitly prints the gap: *"Stores object: N active · Deal Amount sum (legit): M · Gap: +X."*

### Committed Pipeline (the stacked bar)
"Stores by Stage" across the committed mid-funnel stages. Computed as:
```
committed_stores = Σ(deal.amount for deals NOT in closedlost, NOT early-funnel,
                     NOT active, NOT test)              # the mid-funnel stages
                 + M["active_stores"]                    # add the authoritative active #
```
It **adds `active_stores`** rather than re-summing closedwon deal amounts. Re-summing a
second, differently-defined "active" number here is exactly what made the 2026-07-01
report show **9,949 vs 9,839** (the bar total vs the funnel denominator). Keep them tied.

### Funnel Conversion Rate
`round(100 × active_stores / committed_stores)` — active stores as a % of the whole
committed pipeline.

### Mid-funnel stage KPIs
In Lab, Awaiting Software, Awaiting Activation, Awaiting Transactions, Onboarding — each is
`stage_sum(stage_id)` = sum of non-test deal `amount` in that stage.

### Test-record exclusion — TWO different mechanisms (important)
- **Deals**: name-based (`Deal.is_test_record()`). `TEST_EXACT_NAMES` = {tester, self
  employed, send proud, rita, pan, na, clover}; `TEST_SUBSTRING_PATTERNS` = {thinksys,
  qrjwxjqsbuxciwmljofcd, demo unit, homeless not helpless, muhammad hassan, mendietaaaa,
  bunny palace}.
- **Stores**: the **`is_test_data` field is authoritative — NO name matching.** A store
  literally named "…Test…" with `is_test_data=false` is treated as a real store.
- Test exclusion must be applied in `stage_sum()` too — a single test deal in a mid-funnel
  stage otherwise inflates the Committed bar but not the funnel denominator, breaking
  reconciliation.

### Stage-role → HubSpot stage-ID mappings (`fetch_from_hubspot.py::STAGE_ROLES`)
Stage *labels* are pulled live from HubSpot (renames absorb automatically); the *semantic
role* of each stage is hardcoded:

| Role | Stage ID |
|---|---|
| Active | `closedwon` |
| In Lab | `1270202953` |
| Awaiting Software | `1270163972` |
| Awaiting Activation | `1270128498` |
| Awaiting Transactions | `1270078996` |
| Onboarding | `contractsent` |
| Early-funnel (excluded from Committed Pipeline) | leads `1346410815`, unqualified `1350980982`, `qualifiedtobuy`, `appointmentscheduled`, `presentationscheduled`, `decisionmakerboughtin`, parking-lot `1335845536` |

If any role-assigned stage ID vanishes from the live pipeline, the fetch **fails loudly**
rather than silently reporting 0 for that KPI.

### Reliability note (2026-07-01 incident)
A burst of HubSpot 429s made the Stores fetch return empty; downstream treated empty as
valid → a **~1,600-store phantom swing**. The fetch now **raises after retries** (never
returns partial/empty) — store data is all-or-nothing, and a failed pull produces no
report rather than a wrong one.

---

## 2. AM Assignment Audit  (`truage-pulse` → `nacstam`, `/audit`)

Audits HubSpot **account-manager hygiene**: are companies and their contacts owned by the
right, active AM?

### Scope — the "priority population"
Companies with **≥2 associated contacts AND ≥1 associated deal** (~58 accounts). Plus a
separate **inactive-owner sweep**: every company/contact/deal still owned by a designated
inactive user, regardless of counts (catches orphaned vendor/manufacturer records).

### The five account categories
| Category | Meaning |
|---|---|
| **Clean** | Single owner across company and every contact; none unassigned. |
| **Partial** | Right company AM, but some contacts unowned *or* owned by a non-AM (e.g. Support). |
| **Overlap** | ≥2 *active* AMs across the contacts. |
| **Conflict** | Company owner set but owns none of the contacts (or company unowned while a contact is owned). |
| **Orphaned** | No active AM anywhere (owner null/inactive AND no AM on any contact). |

### Hygiene Score (0–100)
```
score = (Clean×1.0 + Partial×0.6 + Overlap×0.4 + Conflict×0.2 + Orphaned×0.0) / Total × 100
```
Thresholds: **≥85 green ("Healthy")**, **60–84 yellow ("Needs attention")**, **<60 red
("Systemic issues")**.

### Owner-ID mappings (hardcoded org constants, `pulse/audit/data.py`)
- **AMs (active)**: `79423140` Eddie McFarlane, `87813531` Megan Terry, `1367430633` Lisa Rountree.
- **Inactive (swept)**: `79761095` Grant Bleecher, `1285253947` Bryan Esser.
- **Other active non-AM (labels only)**: `87367233` Patrick Abernathy (Support), `89184631` Lia LoBello Reynolds (NACS), `78438676` Stephanie Sikorski.

> Note: this report reads the HubSpot token from `HUBSPOT_PRIVATE_APP_TOKEN`, whereas the
> Activation Report reads `HUBSPOT_TOKEN`. The env-var names differ but (confirmed 2026-07-02)
> they hold the **same token / same HubSpot private app** — reused deliberately.

---

## 3. Daily Sales Pulse  (`truage-pulse`, `/daily`) — STUB / not yet live

Spec in `truage-pulse/DAILY_PULSE_SPEC.md`. Intended manager-facing EOD report:
- **Health Score (0–100)** weighted: stall rate 35%, doors velocity vs plan 25%, blocker-reason
  completeness 20%, top-of-funnel 10%, time-in-stage 10%.
- **Top-5 "work these tomorrow"** ranked by
  `urgency = (stores_to_activate or total_stores or 1) × stall_multiplier × stage_progress_multiplier`.
- Not yet wired (`pulse/daily/` is a stub). Open decisions (weekly door target, per-stage
  time thresholds, recipients) still pending.

---

## 4. BenchPoint — 990 Peer Benchmarking  (`nacs-990-benchmark`)

Finds nonprofits similar to **NACS (EIN 95-2237749)**, pulls their IRS Form 990 data, and
generates side-by-side comparisons (Excel + PowerPoint + HTML).
- **Data sources (priority)**: IRS TEOS bulk XML (primary) → manual XML upload → ProPublica
  Nonprofit Explorer (discovery/fallback) → Candid/GuideStar (stub, needs paid key).
- **Peer discovery** uses an LLM cascade (Gemini 2.5 Flash → OpenAI → Anthropic). Seed peers
  (NRF/CTA/NRA/NGA) are force-injected so they survive the candidate cap.
- Metrics are the standard 990 financial lines (revenue, expenses, assets, comp, program
  ratios) compared reference-org-vs-peers. See `app/analysis/comparator.py` + `metrics.py`.

---

## 5. C-Store Intel — Market BI  (`convenience-store-intel`)

170k+ US convenience-store records deduped from up to 6 sources (OSM, USDA SNAP, TomTom,
HERE, Foursquare; Yelp deprecated). State-level analytics.
- **Opportunity Score (0–100)** — `scraper-engine/services/bi.py::market_summary()`:
  **density gap 50% + SNAP gap 30% + population 20%**. Higher = more underserved vs national
  averages.
- **SNAP coverage** — stores with `snapAuth=true` (USDA FNS authoritative store list).
- **storeType** — USDA taxonomy codes (CS, SM, LG, MG, SG, SP, FM, FS, CG, MS, WC).

---

## Cross-report gotchas (quick reference)
- **"Active" is overloaded**: in the Activation Report it means Store-status="Active"
  (preferred) or closedwon deal-amount sum (fallback). Never quote one without knowing which.
- **Two test-exclusion rules**: deals by *name pattern*, stores by the *`is_test_data` field*.
- **Deal `amount` = store count**, not currency, in the activation pipeline.
- **Two HubSpot token env-var names** across the two TruAge services (`HUBSPOT_TOKEN` vs
  `HUBSPOT_PRIVATE_APP_TOKEN`) — but they hold the **same token / same private app**.
- **Stores custom object** (`2-48839355`, operational status) is a different thing from
  **Deals** (Retailer Activations pipeline, sales stages). "Stores vs Deals" = ops truth vs
  sales view.


---

## Note — shared definitions (2026-07-03)
The KPI primitives described above (stage-role → ID mappings, the two test-record rules, deal/store
property lists, the 25k goal, owner-ID maps) now live in **`truage_core.config`** and
**`truage_core.testrecords`**, imported by both report services. Definitions are unchanged — this
is where they're sourced from, so edits happen in one place.
