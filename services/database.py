"""
services/database.py
All MongoDB operations - orders, prices, settings, transactions, vendors,
production tracking.
"""
import streamlit as st
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId

from config.settings import PRODUCTION_STAGES


# ── Connection ────────────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    uri     = st.secrets["mongodb_uri"]
    db_name = st.secrets.get("mongodb_db", "jewel_manager")
    client  = MongoClient(uri)
    return client[db_name]


def _col(name):
    return get_db()[name]


# ── Orders ────────────────────────────────────────────────────────────────────
def get_all_orders(filters=None):
    try:
        docs = list(_col("orders").find(filters or {}).sort("created_at", -1))
        print(docs)
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs
    except Exception:
        return []


def save_order(doc):
    doc["created_at"] = datetime.now()
    result = _col("orders").insert_one(doc)
    return str(result.inserted_id)


def update_order(order_id, updates):
    _col("orders").update_one({"order_id": order_id}, {"$set": updates})


def delete_order(order_id):
    _col("orders").delete_one({"order_id": order_id})


# ── Prices ────────────────────────────────────────────────────────────────────
def get_prices():
    try:
        doc = _col("prices").find_one({"_id": "main"})
        if not doc:
            return {"gold": 9220.49, "diamond": 7500.0}
        return {
            "gold":    float(doc.get("gold_price_24k",          9220.49)),
            "diamond": float(doc.get("diamond_price_per_carat", 7500.0)),
        }
    except Exception:
        return {"gold": 9220.49, "diamond": 7500.0}


def save_prices(gold, diamond):
    _col("prices").replace_one(
        {"_id": "main"},
        {"_id": "main", "gold_price_24k": gold, "diamond_price_per_carat": diamond},
        upsert=True,
    )


# ── Settings ──────────────────────────────────────────────────────────────────
def get_setting(key, default=""):
    try:
        doc = _col("settings").find_one({"key": key})
        return str(doc["value"]) if doc else default
    except Exception:
        return default


def set_setting(key, value):
    _col("settings").replace_one(
        {"key": key},
        {"key": key, "value": value},
        upsert=True,
    )


# ── Vendors ───────────────────────────────────────────────────────────────────
def get_all_vendors():
    try:
        docs = list(_col("vendors").find().sort("name", 1))
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs
    except Exception:
        return []


def save_vendor(doc):
    doc["created_at"] = datetime.now()
    _col("vendors").insert_one(doc)


def delete_vendor(vendor_id):
    _col("vendors").delete_one({"_id": ObjectId(vendor_id)})


# ── Transactions (Ledger) ─────────────────────────────────────────────────────
def get_transactions(filters=None):
    try:
        docs = list(_col("transactions").find(filters or {}).sort("date", -1))
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs
    except Exception:
        return []


def save_transaction(doc):
    doc["created_at"] = datetime.now()
    _col("transactions").insert_one(doc)


def delete_transaction(txn_id):
    _col("transactions").delete_one({"_id": ObjectId(txn_id)})


def get_party_balance(party_name, party_type):
    """
    Returns {cash_balance, gold_balance_grams} for a customer or vendor.
    Positive cash  = they owe us  (customer) / we owe them (vendor)
    Positive gold  = they gave us gold / we gave them gold
    """
    try:
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
    except Exception:
        return {"cash_balance": 0.0, "gold_balance": 0.0}


# ── Order Vendor Transactions ─────────────────────────────────────────────────
def get_order_vendor_txns(order_id):
    """All vendor transactions linked to a specific order."""
    try:
        docs = list(_col("order_vendor_txns").find(
            {"order_id": order_id}
        ).sort("date", -1))
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs
    except Exception:
        return []


def save_order_vendor_txn(doc):
    doc["created_at"] = datetime.now()
    _col("order_vendor_txns").insert_one(doc)


def delete_order_vendor_txn(txn_id):
    _col("order_vendor_txns").delete_one({"_id": ObjectId(txn_id)})


def get_order_vendor_summary(order_id):
    """
    Returns summary for an order:
      gold_sent     : total grams sent to vendor (positive = sent out)
      gold_received : total grams received back  (positive = received)
      cash_paid     : total cash paid to vendor
      goods_received: count of goods-received entries
    """
    try:
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
    except Exception:
        return {
            "gold_sent": 0.0, "gold_received": 0.0,
            "net_gold": 0.0, "cash_paid": 0.0, "goods_received": 0,
        }


# ── Production Pipeline ───────────────────────────────────────────────────────
# One doc per (order_id, stage_name) in "production_stages" — 10 per order.
# Every change to a stage is also logged to "production_events" for audit.

def init_production_pipeline(order_id):
    """
    Call once, right when an Estimate is converted into a confirmed Order.
    Creates the 10 stage docs for the order. Stage 0 (Requirement Received)
    starts COMPLETED since the order already exists; stage 1 (CAD Design)
    opens IN_PROGRESS. Safe to call more than once — no-ops if the order
    already has stages.
    """
    try:
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
    except Exception:
        pass


def get_order_stages(order_id):
    """All 10 stage docs for an order, in pipeline order."""
    try:
        docs = list(_col("production_stages").find({"order_id": order_id}).sort("stage_index", 1))
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs
    except Exception:
        return []


def get_current_stage(order_id):
    """The first non-COMPLETED stage doc, or the last stage if all are done."""
    stages = get_order_stages(order_id)
    if not stages:
        return None
    for s in stages:
        if s["status"] != "COMPLETED":
            return s
    return stages[-1]


def get_all_active_production():
    """
    One row per order that has an active (not-yet-Delivered) pipeline —
    each row is that order's *current* stage doc. This is what the Kanban
    board and dashboard alerts are built from.
    """
    try:
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
    except Exception:
        return []


def update_production_stage(order_id, stage_name, updates, user="Admin"):
    """
    Generic field updater for one stage doc. Diffs against the current
    value for each field and logs a production_events row per change —
    this is what powers the "Full History" expander.
    """
    try:
        current = _col("production_stages").find_one({"order_id": order_id, "stage_name": stage_name})
        if not current:
            return
        for field, new_val in updates.items():
            old_val = current.get(field)
            if old_val != new_val:
                log_production_event(order_id, user, f"update_{field}", old_val, new_val, stage_name)
        _col("production_stages").update_one(
            {"order_id": order_id, "stage_name": stage_name},
            {"$set": updates},
        )
    except Exception:
        pass


def move_stage(order_id, direction, user="Admin"):
    """
    direction: "forward" or "backward". No validation blocks this — the
    jeweller can override the pipeline at any time in either direction.
    Forward: marks the current stage COMPLETED, opens the next as IN_PROGRESS.
    Backward: reopens the current stage as NOT_STARTED, re-activates the
    previous stage as IN_PROGRESS (clearing its completed_at).
    """
    try:
        stages = get_order_stages(order_id)
        if not stages:
            return
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
    except Exception:
        pass


def flag_stage_needs_changes(order_id, stage_name, notes="", user="Admin"):
    """Used for Customer CAD Approval when the customer rejects a design."""
    updates = {"status": "NEED_CHANGES"}
    if notes:
        updates["notes"] = notes
    update_production_stage(order_id, stage_name, updates, user)


def assign_karigar(order_id, stage_name, karigar_name, user="Admin"):
    update_production_stage(order_id, stage_name, {"assigned_to": karigar_name}, user)


def set_stage_deadline(order_id, stage_name, deadline, user="Admin"):
    update_production_stage(order_id, stage_name, {"deadline": str(deadline)}, user)


def add_stage_note(order_id, stage_name, note, user="Admin"):
    update_production_stage(order_id, stage_name, {"notes": note}, user)


def add_stage_image(order_id, stage_name, image_url, user="Admin"):
    try:
        stage  = _col("production_stages").find_one({"order_id": order_id, "stage_name": stage_name}) or {}
        images = stage.get("images", [])
        images.append(image_url)
        _col("production_stages").update_one(
            {"order_id": order_id, "stage_name": stage_name},
            {"$set": {"images": images}},
        )
        log_production_event(order_id, user, "add_image", "", image_url, stage_name)
    except Exception:
        pass


# ── Production Events (audit trail) ───────────────────────────────────────────
def log_production_event(order_id, user, action, old_value, new_value, stage_name=""):
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
    except Exception:
        pass


def get_production_events(order_id):
    try:
        docs = list(_col("production_events").find({"order_id": order_id}).sort("created_at", -1))
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs
    except Exception:
        return []


# ── Production KPIs (dashboard + Kanban header) ───────────────────────────────
def get_production_kpis():
    try:
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
                except Exception:
                    pass
            if s["stage_name"] == "Customer CAD Approval":
                waiting_approval += 1

        return {
            "total_active":     len(active),
            "delayed":          delayed,
            "due_today":        due_today,
            "waiting_approval": waiting_approval,
        }
    except Exception:
        return {"total_active": 0, "delayed": 0, "due_today": 0, "waiting_approval": 0}