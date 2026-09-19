"""
database.py
-----------
Manages the Motor (async MongoDB) client lifecycle.
Supports live MongoDB (Atlas or local) with automatic, zero-config
file-persisted MongoMock fallback for offline demonstrations or
restrictive network/TLS environments.

Usage:
    from app.database import get_db, get_collection, connect_db, close_db, save_mock_db
"""

import json
import os
from datetime import datetime, timezone
import certifi
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

# Module-level client & state
_client = None
_is_mock: bool = False

_MOCK_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_MOCK_STORAGE_FILE = os.path.join(_MOCK_STORAGE_DIR, "mock_db.json")


def _custom_dump(obj):
    if isinstance(obj, datetime):
        return {"__dt__": obj.isoformat()}
    if isinstance(obj, ObjectId):
        return {"__oid__": str(obj)}
    raise TypeError(f"Type {type(obj)} not serializable")


def _custom_load(dct):
    if "__dt__" in dct:
        return datetime.fromisoformat(dct["__dt__"])
    if "__oid__" in dct:
        return ObjectId(dct["__oid__"])
    return dct


async def _load_mock_from_disk(db) -> None:
    if not os.path.exists(_MOCK_STORAGE_FILE):
        return
    try:
        with open(_MOCK_STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f, object_hook=_custom_load)
        for col_name, docs in data.items():
            if docs:
                col = db[col_name]
                await col.delete_many({})
                await col.insert_many(docs)
    except Exception as e:
        print(f"[DB] Warning loading mock DB from disk: {e}")


async def save_mock_db() -> None:
    """Persist collections to disk if running in MongoMock fallback mode."""
    global _client, _is_mock
    if not _is_mock or _client is None:
        return
    try:
        os.makedirs(_MOCK_STORAGE_DIR, exist_ok=True)
        db = _client[settings.database_name]
        data = {}
        for col_name in ["vendors", "vendor_stats", "scan_events"]:
            col = db[col_name]
            cursor = col.find({})
            docs = await cursor.to_list(length=None)
            data[col_name] = docs
        with open(_MOCK_STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, default=_custom_dump, indent=2)
    except Exception as e:
        print(f"[DB] Warning saving mock DB to disk: {e}")


async def connect_db() -> None:
    """Called once at application startup via FastAPI lifespan or CLI scripts."""
    global _client, _is_mock
    _client = None

    # 1. Try connecting to live MongoDB first (with 2.5s timeout)
    try:
        candidate = AsyncIOMotorClient(
            settings.mongodb_url,
            serverSelectionTimeoutMS=2500,
            tlsCAFile=certifi.where(),
        )
        await candidate.admin.command("ping")
        _client = candidate
        _is_mock = False
        masked_host = settings.mongodb_url.split("@")[-1] if "@" in settings.mongodb_url else "localhost"
        print(f"[DB] MongoDB connected -> ...@{masked_host} / db={settings.database_name}")
        return

    except Exception as exc:
        print(f"[DB] Live MongoDB unavailable ({exc.__class__.__name__}). Falling back to resilient local MongoMock store.")

    # 2. Resilient local fallback
    import mongomock_motor
    _client = mongomock_motor.AsyncMongoMockClient()
    _is_mock = True
    db = _client[settings.database_name]
    await _load_mock_from_disk(db)
    print(f"[DB] Local MongoMock engine ready (file-persisted: {_MOCK_STORAGE_FILE})")


async def close_db() -> None:
    """Called once at application shutdown via FastAPI lifespan."""
    global _client, _is_mock
    if _is_mock:
        await save_mock_db()
    if _client:
        _client.close()
        print("[DB] MongoDB connection closed.")


def is_mock_db() -> bool:
    """Return whether app is currently running against local MongoMock store."""
    return _is_mock


def get_db():
    """Return the active database handle. Raises if not connected."""
    if _client is None:
        raise RuntimeError("MongoDB client not initialized. Call connect_db() first.")
    return _client[settings.database_name]


# ── Named collection accessors ──────────────────────────────────────────────


def vendors_col():
    return get_db()["vendors"]


def scan_events_col():
    return get_db()["scan_events"]


def vendor_stats_col():
    return get_db()["vendor_stats"]
