"""
services/database.py
All MongoDB operations - estimates, orders, prices, settings, transactions,
vendors, production tracking.

Error handling contract
-----------------------
Reads  : never raise. On failure they record the error (see `get_db_error`)
         and return a safe empty default, so a page can still render. The UI
         shows a "database unavailable" banner instead of silently pretending
         the database is empty.
Writes : raise `DatabaseError` with a human-readable message. `app.py` catches
         it once at the dispatch level and renders a clean error card, so a
         failed save is always visible and never a raw traceback.
"""
import certifi
import streamlit as st
from functools import wraps
from pymongo import MongoClient
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
    OperationFailure,
    ConfigurationError,
    PyMongoError,
)
from datetime import datetime
from bson import ObjectId

from config.settings import PRODUCTION_STAGES


class DatabaseError(Exception):
    """Raised when a write could not be completed. Carries a user-facing message."""


# ── Error reporting ───────────────────────────────────────────────────────────
_DB_ERROR_KEY = "_db_error"


def _humanize(exc: Exception) -> str:
    """Turn a pymongo exception into something a jeweller can act on."""
    if isinstance(exc, (ServerSelectionTimeoutError, ConnectionFailure)):
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            return ("Couldn't verify MongoDB's SSL certificate. This machine's "
                    "Python is missing its CA bundle — run "
                    "`pip install --upgrade certifi`, or "
                    "`/Applications/Python 3.x/Install Certificates.command`.")
        return ("Can't reach MongoDB. Check your internet connection and that "
                "this machine's IP is allowed in Atlas → Network Access.")
    if isinstance(exc, ConfigurationError):
        return "MongoDB is misconfigured. Check `mongodb_uri` in .streamlit/secrets.toml."
    if isinstance(exc, OperationFailure):
        code = getattr(exc, "code", None)
        if code in (13, 18):     # Unauthorized / AuthenticationFailed
            return "MongoDB rejected the credentials in .streamlit/secrets.toml."
        return f"MongoDB rejected the operation: {exc!s}"
    if isinstance(exc, KeyError):
        return f"Missing secret: {exc!s}. Add it to .streamlit/secrets.toml."
    if isinstance(exc, PyMongoError):
        return f"Database error: {exc!s}"
    return f"Unexpected error: {exc!s}"


def _record_db_error(where: str, exc: Exception):
    try:
        st.session_state[_DB_ERROR_KEY] = {
            "where":   where,
            "message": _humanize(exc),
            "when":    datetime.now(),
        }
    except Exception:
        # session_state is unavailable outside a script run — never let error
        # reporting itself become the failure.
        pass


def get_db_error():
    """The most recent read failure, or None. Used to render the UI banner."""
    try:
        return st.session_state.get(_DB_ERROR_KEY)
    except Exception:
        return None


def clear_db_error():
    try:
        st.session_state.pop(_DB_ERROR_KEY, None)
    except Exception:
        pass


def _safe_read(default_factory):
    """Reads degrade to a safe default and record why."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                _record_db_error(fn.__name__, exc)
                return default_factory()
        return wrapper
    return deco


def _safe_write(action: str):
    """Writes surface a clean, actionable DatabaseError instead of failing quietly."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except DatabaseError:
                raise
            except Exception as exc:
                _record_db_error(fn.__name__, exc)
                raise DatabaseError(f"Couldn't {action}. {_humanize(exc)}") from exc
        return wrapper
    return deco


# ── Connection ────────────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    """
    Connects and verifies the connection with a ping. MongoClient is lazy, so
    without the ping a bad URI would surface much later as a confusing error
    in the middle of a page.
    """
    try:
        uri     = st.secrets["mongodb_uri"]
        db_name = st.secrets.get("mongodb_db", "jewel_manager")
        # tlsCAFile: macOS Python builds ship without a usable system CA
        # bundle, so verifying Atlas's certificate fails with
        # CERTIFICATE_VERIFY_FAILED. certifi is already a dependency.
        client  = MongoClient(
            uri,
            serverSelectionTimeoutMS=8000,
            tlsCAFile=certifi.where(),
        )
        client.admin.command("ping")
        db = client[db_name]
    except Exception as exc:
        raise DatabaseError(_humanize(exc)) from exc

    _migrate_estimates_out_of_orders(db)
    _ensure_indexes(db)
    return db


def _ensure_indexes(db):
    """
    Every query in this module filters by order_id, party_name, status or
    stage_name — none of which were indexed, so each lookup was a full
    collection scan. create_index is idempotent, so this is safe to run on
    every connect and is a no-op once the indexes exist.

    order_id is unique on both `estimates` and `orders`: it is the business
    key that update_order/convert_estimate_to_order match on, so a duplicate
    would silently cross-write two customers' orders.
    """
    try:
        db["estimates"].create_index("order_id", unique=True)
        db["orders"].create_index("order_id", unique=True)
        db["orders"].create_index("status")
        db["orders"].create_index([("created_at", -1)])
        db["production_stages"].create_index([("order_id", 1), ("stage_index", 1)])
        db["production_stages"].create_index("status")
        db["production_events"].create_index([("order_id", 1), ("created_at", -1)])
        db["order_vendor_txns"].create_index([("order_id", 1), ("date", -1)])
        db["transactions"].create_index([("party_name", 1), ("party_type", 1)])
        db["transactions"].create_index([("date", -1)])
        db["vendors"].create_index("name")
        db["settings"].create_index("key")
    except Exception as exc:
        # A duplicate order_id in legacy data will make the unique index fail.
        # That must not stop the app from opening — surface it in the banner
        # and carry on with whatever indexes did get created.
        _record_db_error("_ensure_indexes", exc)


def _col(name):
    return get_db()[name]


def db_is_reachable() -> bool:
    """Cheap health check for the UI banner. Never raises."""
    try:
        get_db().client.admin.command("ping")
        return True
    except Exception:
        return False


# ── One-time migration ────────────────────────────────────────────────────────
def _migrate_estimates_out_of_orders(db):
    """
    Estimates used to live in `orders` with status "Estimate". They now have
    their own collection. Moves any leftovers across on first connect.
    Idempotent and near-free once done.
    """
    try:
        legacy = list(db["orders"].find({"status": "Estimate"}))
        if not legacy:
            return
        for doc in legacy:
            oid = doc.get("order_id")
            if not oid:
                continue
            if not db["estimates"].find_one({"order_id": oid}):
                db["estimates"].insert_one(doc)
        db["orders"].delete_many({"status": "Estimate"})
    except Exception:
        # A failed migration must never block the app from opening.
        pass


# ── Estimates ─────────────────────────────────────────────────────────────────
# Estimates are quotes, not commitments. Nothing else in the system reacts to
# them: no production pipeline, no vendor ledger, no revenue. All of that starts
# at convert_estimate_to_order().

@_safe_read(list)
def get_all_estimates(filters=None):
    docs = list(_col("estimates").find(filters or {}).sort("created_at", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


@_safe_read(lambda: None)
def get_estimate(order_id):
    doc = _col("estimates").find_one({"order_id": order_id})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


@_safe_write("save the estimate")
def save_estimate(doc):
    doc = dict(doc)
    doc["status"]     = "Estimate"
    doc["created_at"] = datetime.now()
    result = _col("estimates").insert_one(doc)
    return str(result.inserted_id)


@_safe_write("update the estimate")
def update_estimate(order_id, updates):
    updates = dict(updates)
    updates.pop("_id", None)
    updates["status"] = "Estimate"          # editing never promotes an estimate
    _col("estimates").update_one({"order_id": order_id}, {"$set": updates})


@_safe_write("delete the estimate")
def delete_estimate(order_id):
    _col("estimates").delete_one({"order_id": order_id})


@_safe_write("convert the estimate to an order")
def convert_estimate_to_order(order_id):
    """
    Moves the estimate document into `orders` with status "Pending" and
    removes it from `estimates`. Returns the resulting order document so the
    caller can start the production pipeline and post the vendor ledger.

    Safe to call twice — if the order already exists the estimate is simply
    cleaned up and the existing order returned.
    """
    existing = _col("orders").find_one({"order_id": order_id})
    if existing:
        _col("estimates").delete_one({"order_id": order_id})
        existing["_id"] = str(existing["_id"])
        return existing

    doc = _col("estimates").find_one({"order_id": order_id})
    if not doc:
        raise DatabaseError(f"Estimate {order_id} no longer exists.")

    doc.pop("_id", None)
    doc["status"]       = "Pending"
    doc["created_at"]   = doc.get("created_at") or datetime.now()
    doc["converted_at"] = datetime.now()

    _col("orders").insert_one(dict(doc))
    _col("estimates").delete_one({"order_id": order_id})
    return doc


# ── Orders ────────────────────────────────────────────────────────────────────
@_safe_read(list)
def get_all_orders(filters=None):
    docs = list(_col("orders").find(filters or {}).sort("created_at", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


@_safe_write("save the order")
def save_order(doc):
    doc = dict(doc)
    doc["created_at"] = datetime.now()
    result = _col("orders").insert_one(doc)
    return str(result.inserted_id)


@_safe_write("update the order")
def update_order(order_id, updates):
    updates = dict(updates)
    updates.pop("_id", None)
    _col("orders").update_one({"order_id": order_id}, {"$set": updates})


@_safe_write("delete the order")
def delete_order(order_id):
    _col("orders").delete_one({"order_id": order_id})


# ── Prices ────────────────────────────────────────────────────────────────────
_DEFAULT_PRICES = {"gold": 9220.49, "diamond": 7500.0}


@_safe_read(lambda: dict(_DEFAULT_PRICES))
def get_prices():
    doc = _col("prices").find_one({"_id": "main"})
    if not doc:
        return dict(_DEFAULT_PRICES)
    return {
        "gold":    float(doc.get("gold_price_24k",          _DEFAULT_PRICES["gold"])),
        "diamond": float(doc.get("diamond_price_per_carat", _DEFAULT_PRICES["diamond"])),
    }


@_safe_write("save the prices")
def save_prices(gold, diamond):
    _col("prices").replace_one(
        {"_id": "main"},
        {"_id": "main", "gold_price_24k": gold, "diamond_price_per_carat": diamond},
        upsert=True,
    )


# ── Settings ──────────────────────────────────────────────────────────────────
@_safe_read(lambda: "")
def get_setting(key, default=""):
    doc = _col("settings").find_one({"key": key})
    return str(doc["value"]) if doc else default


@_safe_write("save the setting")
def set_setting(key, value):
    _col("settings").replace_one(
        {"key": key},
        {"key": key, "value": value},
        upsert=True,
    )


# ── Vendors ───────────────────────────────────────────────────────────────────
@_safe_read(list)
def get_all_vendors():
    docs = list(_col("vendors").find().sort("name", 1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


@_safe_write("save the vendor")
def save_vendor(doc):
    doc = dict(doc)
    doc["created_at"] = datetime.now()
    _col("vendors").insert_one(doc)


@_safe_write("delete the vendor")
def delete_vendor(vendor_id):
    _col("vendors").delete_one({"_id": ObjectId(vendor_id)})


# ── Transactions (Ledger) ─────────────────────────────────────────────────────
@_safe_read(list)
def get_transactions(filters=None):
    docs = list(_col("transactions").find(filters or {}).sort("date", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


@_safe_write("save the transaction")
def save_transaction(doc):
    doc = dict(doc)
    doc["created_at"] = datetime.now()
    _col("transactions").insert_one(doc)


@_safe_write("delete the transaction")
def delete_transaction(txn_id):
    _col("transactions").delete_one({"_id": ObjectId(txn_id)})


@_safe_read(lambda: {"cash_balance": 0.0, "gold_balance": 0.0})
def get_party_balance(party_name, party_type):
    """
    Returns {cash_balance, gold_balance_grams} for a customer or vendor.
    Positive cash  = they owe us  (customer) / we owe them (vendor)
    Positive gold  = they gave us gold / we gave them gold
    """
    txns = list(_col("transactions").find({
        "party_name": party_name,
        "party_type": party_type,
    }))
    cash_bal = 0.0
    gold_bal = 0.0
    for t in txns:
        cash_bal += float(t.get("cash_amount", 0) or 0)
        gold_bal += float(t.get("gold_grams",  0) or 0)
    return {"cash_balance": cash_bal, "gold_balance": gold_bal}


# ── Order Vendor Transactions ─────────────────────────────────────────────────
@_safe_read(list)
def get_order_vendor_txns(order_id):
    """All vendor transactions linked to a specific order."""
    docs = list(_col("order_vendor_txns").find(
        {"order_id": order_id}
    ).sort("date", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


@_safe_write("save the vendor transaction")
def save_order_vendor_txn(doc):
    doc = dict(doc)
    doc["created_at"] = datetime.now()
    _col("order_vendor_txns").insert_one(doc)


@_safe_write("delete the vendor transaction")
def delete_order_vendor_txn(txn_id):
    _col("order_vendor_txns").delete_one({"_id": ObjectId(txn_id)})


_EMPTY_VENDOR_SUMMARY = {
    "gold_sent": 0.0, "gold_received": 0.0,
    "net_gold": 0.0, "cash_paid": 0.0, "goods_received": 0,
}

# Public alias — pages use this as the default for an order with no vendor
# activity when reading from the bulk get_vendor_summaries() map.
EMPTY_VENDOR_SUMMARY = _EMPTY_VENDOR_SUMMARY


@_safe_read(dict)
def get_vendor_summaries(order_ids):
    """
    Bulk form of get_order_vendor_summary: one aggregation for many orders
    instead of one query each. Returns {order_id: summary}; callers should
    use `.get(oid, dict(_EMPTY_VENDOR_SUMMARY))` for orders with no activity.

    The Orders page renders one card per order and Streamlit executes every
    expander and tab body on every rerun, so the per-order version turned a
    single page into O(N) round-trips per keystroke.
    """
    order_ids = list(order_ids)
    if not order_ids:
        return {}
    rows = _col("order_vendor_txns").aggregate([
        {"$match": {"order_id": {"$in": order_ids}}},
        {"$group": {
            "_id": {"order_id": "$order_id", "txn_type": "$txn_type"},
            "gold":  {"$sum": {"$ifNull": ["$gold_grams",  0]}},
            "cash":  {"$sum": {"$ifNull": ["$cash_amount", 0]}},
            "count": {"$sum": 1},
        }},
    ])
    out = {}
    for r in rows:
        oid      = r["_id"]["order_id"]
        txn_type = r["_id"]["txn_type"]
        s = out.setdefault(oid, dict(_EMPTY_VENDOR_SUMMARY))
        if txn_type == "gold_sent":
            s["gold_sent"]      = float(r["gold"] or 0)
        elif txn_type == "gold_received":
            s["gold_received"]  = float(r["gold"] or 0)
        elif txn_type == "cash_paid":
            s["cash_paid"]      = float(r["cash"] or 0)
        elif txn_type == "goods_received":
            s["goods_received"] = int(r["count"])
    for s in out.values():
        s["net_gold"] = s["gold_sent"] - s["gold_received"]
    return out


@_safe_read(dict)
def get_stages_for_orders(order_ids):
    """
    Bulk form of get_order_stages. Returns {order_id: [stage docs in order]}.
    """
    order_ids = list(order_ids)
    if not order_ids:
        return {}
    docs = _col("production_stages").find(
        {"order_id": {"$in": order_ids}}
    ).sort([("order_id", 1), ("stage_index", 1)])
    out = {}
    for d in docs:
        d["_id"] = str(d["_id"])
        out.setdefault(d["order_id"], []).append(d)
    return out


@_safe_read(lambda: dict(_EMPTY_VENDOR_SUMMARY))
def get_order_vendor_summary(order_id):
    """
    Returns summary for an order:
      gold_sent     : total grams sent to vendor (positive = sent out)
      gold_received : total grams received back  (positive = received)
      cash_paid     : total cash paid to vendor
      goods_received: count of goods-received entries
    """
    docs = list(_col("order_vendor_txns").find({"order_id": order_id}))
    gold_sent     = 0.0
    gold_received = 0.0
    cash_paid     = 0.0
    goods_count   = 0
    for d in docs:
        txn_type = d.get("txn_type", "")
        if txn_type == "gold_sent":
            gold_sent     += float(d.get("gold_grams", 0) or 0)
        elif txn_type == "gold_received":
            gold_received += float(d.get("gold_grams", 0) or 0)
        elif txn_type == "cash_paid":
            cash_paid     += float(d.get("cash_amount", 0) or 0)
        elif txn_type == "goods_received":
            goods_count   += 1
    return {
        "gold_sent":      gold_sent,
        "gold_received":  gold_received,
        "net_gold":       gold_sent - gold_received,   # positive = still with vendor
        "cash_paid":      cash_paid,
        "goods_received": goods_count,
    }


# ── Production Pipeline ───────────────────────────────────────────────────────
# One doc per (order_id, stage_name) in "production_stages" — 10 per order.
# Every change to a stage is also logged to "production_events" for audit.

@_safe_write("start the production pipeline")
def init_production_pipeline(order_id):
    """
    Call once, right when an Estimate is converted into a confirmed Order.
    Creates the 10 stage docs for the order. Stage 0 (Requirement Received)
    starts COMPLETED since the order already exists; stage 1 (CAD Design)
    opens IN_PROGRESS. Safe to call more than once — no-ops if the order
    already has stages.
    """
    if _col("production_stages").find_one({"order_id": order_id}):
        return
    now  = datetime.now()
    docs = []
    for i, stage in enumerate(PRODUCTION_STAGES):
        docs.append({
            "order_id":     order_id,
            "stage_name":   stage,
            "stage_index":  i,
            "assigned_to":  "",
            "status":       "COMPLETED" if i == 0 else ("IN_PROGRESS" if i == 1 else "NOT_STARTED"),
            "deadline":     None,
            "completed_at": now if i == 0 else None,
            "notes":        "",
            "images":       [],
        })
    _col("production_stages").insert_many(docs)
    log_production_event(order_id, "System", "pipeline_started", "", PRODUCTION_STAGES[1])


@_safe_read(list)
def get_order_stages(order_id):
    """All 10 stage docs for an order, in pipeline order."""
    docs = list(_col("production_stages").find({"order_id": order_id}).sort("stage_index", 1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


def get_current_stage(order_id):
    """The first non-COMPLETED stage doc, or the last stage if all are done."""
    stages = get_order_stages(order_id)
    if not stages:
        return None
    for s in stages:
        if s["status"] != "COMPLETED":
            return s
    return stages[-1]


@_safe_read(list)
def get_all_active_production():
    """
    One row per order that has an active (not-yet-Delivered) pipeline —
    each row is that order's *current* stage doc. This is what the Kanban
    board and dashboard alerts are built from.
    """
    pipeline = [
        {"$match": {"status": {"$ne": "COMPLETED"}}},
        {"$sort": {"stage_index": 1}},
        {"$group": {"_id": "$order_id", "stage": {"$first": "$$ROOT"}}},
    ]
    rows = list(_col("production_stages").aggregate(pipeline))
    out  = []
    for r in rows:
        s = r["stage"]
        s["_id"] = str(s["_id"])
        out.append(s)
    return out


@_safe_write("update the production stage")
def update_production_stage(order_id, stage_name, updates, user="Admin"):
    """
    Generic field updater for one stage doc. Diffs against the current
    value for each field and logs a production_events row per change —
    this is what powers the "Full History" expander.
    """
    current = _col("production_stages").find_one({"order_id": order_id, "stage_name": stage_name})
    if not current:
        raise DatabaseError(f"Stage \"{stage_name}\" doesn't exist for order {order_id}.")
    for field, new_val in updates.items():
        old_val = current.get(field)
        if old_val != new_val:
            log_production_event(order_id, user, f"update_{field}", old_val, new_val, stage_name)
    _col("production_stages").update_one(
        {"order_id": order_id, "stage_name": stage_name},
        {"$set": updates},
    )


@_safe_write("move the production stage")
def move_stage(order_id, direction, user="Admin"):
    """
    direction: "forward" or "backward". No validation blocks this — the
    jeweller can override the pipeline at any time in either direction.
    Forward: marks the current stage COMPLETED, opens the next as IN_PROGRESS.
    Backward: reopens the current stage as NOT_STARTED, re-activates the
    previous stage as IN_PROGRESS (clearing its completed_at).
    """
    stages = get_order_stages(order_id)
    if not stages:
        raise DatabaseError(f"Order {order_id} has no production pipeline yet.")
    idx = next((i for i, s in enumerate(stages) if s["status"] != "COMPLETED"), len(stages) - 1)
    now = datetime.now()

    if direction == "forward" and idx == len(stages) - 1:
        # Last stage (Delivered) — nothing to open next, just close it out.
        cur = stages[idx]
        _col("production_stages").update_one(
            {"_id": ObjectId(cur["_id"])},
            {"$set": {"status": "COMPLETED", "completed_at": now}},
        )
        log_production_event(order_id, user, "move_forward", cur["stage_name"], "— (delivered)")

    elif direction == "forward" and idx < len(stages) - 1:
        cur, nxt = stages[idx], stages[idx + 1]
        _col("production_stages").update_one(
            {"_id": ObjectId(cur["_id"])},
            {"$set": {"status": "COMPLETED", "completed_at": now}},
        )
        _col("production_stages").update_one(
            {"_id": ObjectId(nxt["_id"])},
            {"$set": {"status": "IN_PROGRESS"}},
        )
        log_production_event(order_id, user, "move_forward", cur["stage_name"], nxt["stage_name"])

    elif direction == "backward" and idx > 0:
        cur, prev = stages[idx], stages[idx - 1]
        _col("production_stages").update_one(
            {"_id": ObjectId(cur["_id"])},
            {"$set": {"status": "NOT_STARTED"}},
        )
        _col("production_stages").update_one(
            {"_id": ObjectId(prev["_id"])},
            {"$set": {"status": "IN_PROGRESS", "completed_at": None}},
        )
        log_production_event(order_id, user, "move_backward", cur["stage_name"], prev["stage_name"])


def flag_stage_needs_changes(order_id, stage_name, notes="", user="Admin"):
    """Used for Customer CAD Approval when the customer rejects a design."""
    updates = {"status": "NEED_CHANGES"}
    if notes:
        updates["notes"] = notes
    update_production_stage(order_id, stage_name, updates, user)


@_safe_write("mark the order as delivered")
def mark_order_delivered(order_id, user="Admin"):
    """
    Jeweller override: skip straight to Delivered regardless of what stage
    the order is currently sitting in (rush job, walk-in pickup, backfilled
    historical order, etc). Closes out every remaining stage in one shot.
    """
    stages = get_order_stages(order_id)
    if not stages:
        return
    now = datetime.now()
    for s in stages:
        if s["status"] != "COMPLETED":
            _col("production_stages").update_one(
                {"_id": ObjectId(s["_id"])},
                {"$set": {"status": "COMPLETED", "completed_at": now}},
            )
    log_production_event(order_id, user, "mark_delivered", "", "Delivered (skipped remaining stages)")


def assign_karigar(order_id, stage_name, karigar_name, user="Admin"):
    update_production_stage(order_id, stage_name, {"assigned_to": karigar_name}, user)


def set_stage_deadline(order_id, stage_name, deadline, user="Admin"):
    update_production_stage(order_id, stage_name, {"deadline": str(deadline)}, user)


def add_stage_note(order_id, stage_name, note, user="Admin"):
    update_production_stage(order_id, stage_name, {"notes": note}, user)


@_safe_write("attach the image to the stage")
def add_stage_image(order_id, stage_name, image_url, user="Admin"):
    stage  = _col("production_stages").find_one({"order_id": order_id, "stage_name": stage_name}) or {}
    images = stage.get("images", [])
    images.append(image_url)
    _col("production_stages").update_one(
        {"order_id": order_id, "stage_name": stage_name},
        {"$set": {"images": images}},
    )
    log_production_event(order_id, user, "add_image", "", image_url, stage_name)


# ── Production Events (audit trail) ───────────────────────────────────────────
def log_production_event(order_id, user, action, old_value, new_value, stage_name=""):
    """
    Audit logging is best-effort by design: a failure to write history must
    never block the actual production update the user asked for.
    """
    try:
        _col("production_events").insert_one({
            "order_id":   order_id,
            "stage_name": stage_name,
            "user":       user,
            "action":     action,
            "old_value":  "" if old_value is None else str(old_value),
            "new_value":  "" if new_value is None else str(new_value),
            "created_at": datetime.now(),
        })
    except Exception as exc:
        _record_db_error("log_production_event", exc)


@_safe_read(list)
def get_production_events(order_id):
    docs = list(_col("production_events").find({"order_id": order_id}).sort("created_at", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


# ── Production KPIs (dashboard + Kanban header) ───────────────────────────────
_EMPTY_KPIS = {"total_active": 0, "delayed": 0, "due_today": 0, "waiting_approval": 0}


@_safe_read(lambda: dict(_EMPTY_KPIS))
def get_production_kpis():
    active = get_all_active_production()
    today  = datetime.now().date()

    delayed = due_today = waiting_approval = 0
    for s in active:
        dl = s.get("deadline")
        if dl:
            try:
                dl_date = datetime.strptime(str(dl)[:10], "%Y-%m-%d").date()
                if dl_date < today:
                    delayed += 1
                elif dl_date == today:
                    due_today += 1
            except (ValueError, TypeError):
                pass
        if s["stage_name"] == "Customer CAD Approval":
            waiting_approval += 1

    return {
        "total_active":     len(active),
        "delayed":          delayed,
        "due_today":        due_today,
        "waiting_approval": waiting_approval,
    }
