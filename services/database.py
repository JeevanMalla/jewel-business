"""
services/database.py
All MongoDB operations - orders, prices, settings, transactions, vendors.
"""
import streamlit as st
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId


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