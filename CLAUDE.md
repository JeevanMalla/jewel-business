# Jewel Manager Pro — Claude Code guide

Streamlit app for running a jewellery business end to end: build an estimate →
convert it to an order → track it through a 10-stage production pipeline → settle
gold and cash with the vendor in a ledger → print PDFs (estimate / invoice /
karigar work order).

Single-user for now. One shared password, no roles, no accounts.

> `README.md` is **stale** — it documents a `pages/` folder that no longer exists and
> predates the Production and Finance pages. Trust this file over it.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

`.streamlit/secrets.toml` must exist first — the app hard-fails on a missing
`mongodb_uri`. It's gitignored and present locally. There is no build step, no
tests, no linter, no CI.

Python only. Streamlit reruns the **entire script** top to bottom on every widget
interaction — that's the single most important thing to internalize before editing
anything here.

## Architecture

```
app.py                 password gate → CSS → sidebar → dispatch
  └─ components/       reusable widgets (sidebar, uploader, timeline, cards, vendor panel)
       └─ app_pages/   one module per screen, each exposes render(...)
            └─ services/   database.py · cloudinary.py · diamond_sheet.py · pdf_generator.py
                 └─ config/settings.py   every constant + global CSS
```

Strict direction of dependency: **pages never touch pymongo directly.** All Mongo
access goes through `services/database.py`. All magic numbers, stage names, dropdown
options and CSS live in `config/settings.py`.

### Boot sequence (`app.py`)

1. `st.set_page_config(**PAGE_CONFIG)` — must be the *first* Streamlit call in the process.
2. `check_password()` compares against `st.secrets["app_password"]`; `st.stop()` on failure.
3. `apply_global_css()` injects the shared stylesheet.
4. `render_sidebar()` returns `(page, gold_base, diamond_base, shape_dfs)`.
5. A plain `if/elif` on `page` **lazily imports** the matching `app_pages` module and
   calls its `render(...)`. Keep imports inside the branch — top-level imports would
   pay Mongo/gspread cost for every page on every rerun.

### Why `app_pages/` and not `pages/`

Streamlit auto-generates a multipage nav from any top-level `pages/` directory. The
folder was renamed to suppress that; the sidebar radio is the only navigation. **Do
not create a `pages/` directory.** (The module docstrings inside `app_pages/` still
say `pages/...` — harmless leftovers.)

### Page map

| Page | Module | `render()` signature |
|---|---|---|
| 🏠 Dashboard | `app_pages/dashboard.py` | `render()` |
| 📋 New Estimation | `app_pages/estimation.py` | `render(gold_base, diamond_base, shape_dfs)` |
| 📦 Orders | `app_pages/orders.py` | `render()` |
| 🏭 Production | `app_pages/production.py` | `render()` |
| 💰 Finance | `app_pages/finance.py` | `render(gold_base)` |
| ⚙️ Settings | `app_pages/settings.py` | `render(gold_base)` |

## Data model (MongoDB)

| Collection | Shape |
|---|---|
| `estimates` | quotes only — same shape as an order, `status: "Estimate"` |
| `orders` | confirmed orders only, keyed by string `order_id` (`ORD-YYMMDDHHMMSS`) |
| `prices` | exactly one doc, `_id: "main"` — `gold_price_24k`, `diamond_price_per_carat` |
| `settings` | key/value pairs (`business_name`, …) |
| `vendors` | vendor master — `name`, `phone`, `vendor_type`, `gstin`, `notes` |
| `transactions` | global ledger, both customers and vendors |
| `order_vendor_txns` | per-order vendor activity (feeds the Vendor & Costs tab) |
| `production_stages` | **10 docs per order**, one per stage in `PRODUCTION_STAGES` |
| `production_events` | append-only audit log of every production change |

`_id` is stringified on read in every getter, so callers get plain JSON-ish dicts.
Deletes that take an `_id` re-wrap it with `ObjectId(...)`.

### The order document

`order_id` is the business key everywhere — **not** `_id`. A quote is saved to
`estimates`; converting **moves the document** into `orders` with
`status: "Pending"`, from where it follows `ORDER_STATUSES`.

**An estimate is inert.** Nothing reacts to it — no production pipeline, no
vendor ledger, no revenue on the dashboard, no P&L row. All of that begins at
`convert_estimate_to_order()`. Keep it that way when adding features: if a new
side effect should fire for real orders, hang it off conversion, not off save.

Every money line carries a **sell** value and a **cost** value. This pairing is what
the P&L tab is built on — when adding a new charge, add both halves:

| Sell | Cost |
|---|---|
| `gold_price_gram` / `gold_value` | `gold_cost_per_gram` / `gold_cost_value` |
| `price_per_ct` (per diamond row) / `total_diamond_value` | `cost_per_ct` / `total_diamond_cost` |
| `making_per_gram` / `making_value` | `making_cost_per_gram` / `making_cost_value` |
| `cert_cost` | `cert_actual_cost` |
| `hallmark_value` | `hallmark_cost_per` / `hallmark_cost_value` |
| `net_amount`, `gst_amount`, `gross_amount` | `total_cost`, `total_profit`, `profit_pct` |

`diamond_rows` is a list of dicts (label, shape, quality, sieve, wt_per_pc, pcs,
prices, tcw, value, cost_value) — stored nested, not normalized.
Images: `item_image`, `customer_image`, `cad_image` (Cloudinary URLs).

### Production docs

`production_stages`: `order_id`, `stage_name`, `stage_index`, `assigned_to`,
`status` (one of `PRODUCTION_STATUSES`), `deadline`, `completed_at`, `notes`, `images[]`.

The "current stage" of an order is always **the first non-`COMPLETED` doc** by
`stage_index` (`get_current_stage`). `get_all_active_production()` does this with an
aggregation and returns one row per active order — it backs both the Kanban board and
the dashboard alerts.

## Key flows

**Estimate → Order** (`app_pages/orders.py`, Actions tab): `convert_estimate_to_order()`
moves the doc from `estimates` to `orders` as `"Pending"` (idempotent), then
`init_production_pipeline(oid)` creates the 10 stage docs, then — if a vendor is
assigned — **auto-posts two ledger transactions**: gold sent out (as 24K equivalent)
and cash payable (making + diamonds + cert + hallmark). Those rows carry
`auto_posted: True`.

The Orders page lists **both** collections so an estimate is reachable for
conversion; `is_estimate` decides which collection an edit/delete/image-save
targets. Dashboard revenue, Finance and P&L read `orders` only, so estimates can
never inflate revenue.

**Editing an order:** Orders → Edit tab stashes `editing_order_id` +
`editing_order_data` (the *raw* order doc, not the coerced DataFrame row) and
navigates to Estimation. `_enter_edit_mode()` runs once per order — guarded by
`_loaded_edit_for` — and **deletes all `d_*` widget keys and `gold_cost_gram`** first,
because stale widget state from a previous session would otherwise silently override
the loaded order. Saving uses `update_order` and deliberately leaves `status` alone.

**Production movement:** `move_stage(order_id, "forward"|"backward")` — no validation
gates, by design; the jeweller can override the pipeline in either direction at any
time. `mark_order_delivered()` closes out every remaining stage at once.
`update_production_stage()` diffs each field against its current value and writes one
`production_events` row per actual change — that's what powers the Full History expander.

**Diamond pricing:** `services/diamond_sheet.py` loads one Google Sheet worksheet per
diamond shape (cached 1h). `COL_ALIASES` in `config/settings.py` does fuzzy,
case-insensitive header matching so slight column-name drift in the sheet doesn't
break lookups. If the sheet has no price for a shape/sieve/quality, the row falls
back to manual entry (the sheet/manual badge in the UI reflects which one is live).

## Conventions & gotchas

- **Cross-page navigation:** set `st.session_state["nav_request"] = "📦 Orders"` plus a
  payload key, then `st.rerun()`. `render_sidebar()` pops `nav_request` into
  `nav_radio` *before* the radio widget is created — assigning to a widget's own key
  after instantiation raises `StreamlitAPIException`. Don't bypass this.
  Payload keys in use: `order_search`, `production_open_order`, `editing_order_id` +
  `editing_order_data`.
- **Always `st.rerun()` after a mutation**, otherwise the page shows pre-write state.
- **Widget keys must be unique per rendered instance.** Anything rendered in a loop
  suffixes the order id / index (`key=f"upd_{oid}"`). Collisions are the most common
  bug class here.
- **Cloudinary uploads are cached in session state** (`upload_image_widget`) keyed on
  `uploaded.file_id` — without this, every unrelated keystroke on the page would
  re-upload the same file, since `st.tabs()` runs *both* tabs' code on every rerun.
- **Gold sent to a vendor is always converted to 24K-equivalent grams** before it hits
  the ledger, using the purity factor. Item grams stay on the `order_vendor_txns` row.
- **Ledger signs:** negative `cash_amount` / `gold_grams` = money or metal going *out*.
- **Styling** is CSS classes from `apply_global_css()` rendered with
  `unsafe_allow_html=True` — `.metric-card`, `.gold-header`, `.total-box`, `.img-label`,
  `.price-badge-sheet` / `.price-badge-manual`. Reuse them rather than inlining new styles.
- **Database errors have a contract** (see the `services/database.py` docstring):
  reads never raise — they degrade to an empty default and record the reason;
  writes raise `DatabaseError`. `app.py` catches it once around the page dispatch
  and renders a clean error, so **never** wrap a save in a bare `except`.
- **Defensive DataFrame coercion:** `_safe_df` (orders) and `_txn_df` (finance) force
  every expected column to exist and coerce types, because Mongo docs are
  schema-less and older docs are missing newer fields. Follow that pattern when adding
  columns.
- **New constants go in `config/settings.py`.** Adding a stage to `PRODUCTION_STAGES`
  or a column to `KANBAN_STAGES` requires no other code change.

## Known issues (still open in `main`)

1. **Phantom field names — ₹ totals read as 0.** `app_pages/orders.py:35-36`,
   `app_pages/dashboard.py:63` and `app_pages/finance.py:510` read `gross`, `gst`,
   `gold_wt`, `diamond_tcw`, `diamond_pcs`. `estimation.py` saves `gross_amount`,
   `gst_amount`, `gold_weight`, `total_tcw`, `total_pcs`. Nothing anywhere writes the
   short names, so those columns are always 0 — dashboard revenue/profit and the
   Orders card headers all show ₹0. **This is the highest-value fix outstanding.**
2. **GST is off but labelled 3%.** `GST_RATE = 0.00` (`config/settings.py:65`) while
   the totals box in `estimation.py` hardcodes the text "GST 3%".
3. **Purity labels don't match their factors.** `GOLD_PURITY` is authoritative and
   correct (18K = 0.760, 14K = 0.595) but the *label text* still reads
   "18K (75.0%)" / "14K (58.3%)". The labels are stored verbatim as `gold_purity`
   on existing order documents, so renaming them would orphan saved orders —
   needs a migration, not just an edit.
4. **No `app_password` in `.streamlit/secrets.toml`.** `check_password()` falls back
   to `st.secrets.get("app_password", "")`, so the gate compares against an empty
   string. Set a real password.
5. **Sidebar refresh buttons are blunt.** "Refresh Prices" calls
   `st.cache_resource.clear()` (`components/sidebar.py:50`), which drops the Mongo and
   gspread clients — but `get_prices()` isn't cached, so it achieves nothing except a
   reconnect. "Refresh Diamond Prices" calls a global `st.cache_data.clear()`.
6. **Deprecated Streamlit arg:** `use_column_width=True` in
   `services/cloudinary.py:84,95` and `components/image_uploader.py:52` —
   `use_container_width` is the modern replacement.
7. **`README.md` is stale** (documents `pages/`, omits Production/Finance).
8. **No `secrets.toml.template`** despite the README referencing one. The canonical
   schema is the on-screen guide in `app_pages/settings.py`.
9. **Dead `!= "Estimate"` filters** remain in `app_pages/dashboard.py` (lines ~126,
   140, 154) and `production.py`. Harmless no-ops now that estimates live in their
   own collection, but they imply otherwise.

### Recently fixed (don't re-report these)

- Estimates moved out of `orders` into their own `estimates` collection; saving an
  estimate now has zero side effects. Legacy estimates are migrated automatically
  on first connect by `_migrate_estimates_out_of_orders()`.
- `vendor_panel` had its own purity map (18K = 0.750, 14K = 0.583) that disagreed
  with `GOLD_PURITY`; it now imports the shared one.
- Sidebar `Gold ₹/gram` / `Diamond ₹/carat` were white text on a white field
  (invisible). `apply_global_css()` now styles BaseWeb's nested `base-input`
  wrapper too — contrast is 12.7:1.
- Every `services/database.py` function swallowed exceptions. Reads now degrade and
  report; writes raise `DatabaseError`. See the module docstring.
- MongoDB connections failed with `CERTIFICATE_VERIFY_FAILED` on macOS; the client
  now passes `tlsCAFile=certifi.where()`.

## Secrets (`.streamlit/secrets.toml`)

```toml
app_password = "..."

mongodb_uri = "mongodb+srv://USER:PASS@cluster.mongodb.net/?retryWrites=true&w=majority"
mongodb_db  = "jewel_manager"          # optional, defaults to jewel_manager

cloudinary_cloud_name = "..."
cloudinary_api_key    = "..."
cloudinary_api_secret = "..."

diamond_sheet_id = "..."               # optional — sheet features hide if absent

[gcp_service_account]                  # service-account JSON, for the diamond sheet
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
auth_uri  = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
```

The diamond price sheet must be shared with `client_email` as an Editor.

## Working on this repo

There are no tests and no linter — verification means running `streamlit run app.py`
and clicking through the affected flow. When touching money math, check the P&L tab in
Finance and the profit metrics on the Estimation page, since sell and cost paths are
computed separately and drift easily.
