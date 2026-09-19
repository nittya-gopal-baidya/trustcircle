"""
models/scan_event.py
--------------------
Represents a single QR scan event as stored in MongoDB.
customer_hash is NEVER returned in any customer-facing API response.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class ScanEventDocument(BaseModel):
    """Shape of a document in the `scan_events` collection."""
    vendor_id: str
    customer_hash: str        # SHA-256 of the customer identifier — internal only
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    amount: float = 0.0       # Simulated transaction amount (INR)
