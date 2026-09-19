"""
models/vendor.py
----------------
Represents a vendor document as stored in MongoDB.
"""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class VendorDocument(BaseModel):
    """Shape of a document in the `vendors` collection."""
    vendor_id: str
    name: str
    category: str
    city: str = "Unknown"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    dispute_count: int = 0
    total_transactions: int = 0
