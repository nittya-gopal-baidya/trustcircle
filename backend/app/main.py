"""
main.py
-------
TrustCircle FastAPI application entry point.

Startup:
  - Connect to MongoDB (ping verified)
  - Create indexes
  - Seed demo vendors if collection is empty

Shutdown:
  - Close MongoDB connection

Routes registered:
  /api/vendors     → vendors.py
  /api/scans       → scans.py
  /api/simulation  → simulation.py
  /ws/vendor/{id}  → websocket/handler.py
"""
# Startup & Lifespan management
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import close_db, connect_db, get_db, vendors_col
from app.routes import scans, simulation, vendors
from app.websocket import handler as ws_handler


# ── Demo vendor seed data ─────────────────────────────────────────────────────

DEMO_VENDORS = [
    {
        "vendor_id": "sharma_chai_001",
        "name": "Sharma Chai Corner",
        "category": "Tea Stall",
        "city": "Jaipur",
        "created_at": datetime(2023, 6, 15, tzinfo=timezone.utc),
        "dispute_count": 0,
        "total_transactions": 0,
    },
    {
        "vendor_id": "vendor_growing_cafe",
        "name": "Ravi's Breakfast & Chai",
        "category": "Quick Service Cafe",
        "city": "Mumbai",
        "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        "dispute_count": 0,
        "total_transactions": 0,
    },
    {
        "vendor_id": "vendor_trusted_kirana",
        "name": "Gupta Kirana & General Store",
        "category": "Daily Grocery & Provisions",
        "city": "Delhi",
        "created_at": datetime(2023, 6, 1, tzinfo=timezone.utc),
        "dispute_count": 1,
        "total_transactions": 500,
    },
    {
        "vendor_id": "vendor_community_sweets",
        "name": "Jodhpur Sweets & Namkeen",
        "category": "Heritage Confectionery",
        "city": "Jaipur",
        "created_at": datetime(2022, 11, 5, tzinfo=timezone.utc),
        "dispute_count": 2,
        "total_transactions": 2200,
    },
    {
        "vendor_id": "vendor_chai_stall",
        "name": "Ravi's Chai Stall",
        "category": "Food & Beverage",
        "city": "Mumbai",
        "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        "dispute_count": 0,
        "total_transactions": 0,
    },
]


# ── Lifespan: startup + shutdown ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Replaces deprecated @app.on_event("startup") / @app.on_event("shutdown").
    """
    # ── STARTUP ───────────────────────────────────────────────────────────────
    try:
        await connect_db()

        db = get_db()

        # Create indexes for efficient queries
        await db["scan_events"].create_index([("vendor_id", 1), ("customer_hash", 1)])
        await db["scan_events"].create_index([("vendor_id", 1), ("timestamp", -1)])
        await db["vendor_stats"].create_index([("vendor_id", 1)], unique=True)
        await db["vendors"].create_index([("vendor_id", 1)], unique=True)
        print("[DB] MongoDB indexes created")

        # Ensure all demo vendors exist via upsert
        for v in DEMO_VENDORS:
            await vendors_col().update_one(
                {"vendor_id": v["vendor_id"]},
                {"$setOnInsert": v},
                upsert=True,
            )
        print(f"[DB] Ensured {len(DEMO_VENDORS)} demo vendors seeded (including sharma_chai_001)")
    except Exception as e:
        print(f"[DB] Warning: Could not connect to MongoDB on startup: {e}")

    yield  # Application runs here

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    await close_db()


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="TrustCircle API",
    description=(
        "Trust signal engine for offline QR-code vendors. "
        "Aggregates repeat-scan behavior to compute a vendor trust tier. "
        "[HACKATHON PROTOTYPE] Not connected to real payment data."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS — allow React frontend on localhost & production domains ──────────────
from app.config import settings

configured_origins = [
    "http://localhost:5173",   # Vite default
    "http://localhost:3000",   # fallback
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
if settings.allowed_origins:
    for o in settings.allowed_origins.split(","):
        clean_origin = o.strip()
        if clean_origin and clean_origin not in configured_origins:
            configured_origins.append(clean_origin)

is_wildcard = "*" in configured_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if is_wildcard else configured_origins,
    allow_origin_regex=None if is_wildcard else r"https://.*\.vercel\.app",
    allow_credentials=False if is_wildcard else True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Register routers ──────────────────────────────────────────────────────────

app.include_router(vendors.router)
app.include_router(scans.router)
app.include_router(simulation.router)
app.include_router(ws_handler.router)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "TrustCircle API",
        "status": "running",
        "docs": "/docs",
        "note": "Hackathon prototype - simulated QR scan data only",
    }


@app.get("/health", tags=["Health"])
async def health():
    """Ping MongoDB and return sanitized health status (never leak internal exceptions)."""
    try:
        await get_db().command("ping")
        return {"status": "healthy", "mongodb": "connected"}
    except Exception:
        return {"status": "unhealthy", "mongodb": "disconnected"}


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Prevent internal server exceptions or stack traces from leaking to clients."""
    from fastapi.responses import JSONResponse
    print(f"[SECURITY] Unhandled internal exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Request could not be processed."},
    )

