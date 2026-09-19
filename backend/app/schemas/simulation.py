"""
schemas/simulation.py
---------------------
Request/response schemas for the hackathon simulation endpoints.
"""

from typing import Optional
from pydantic import BaseModel, Field


class BurstSimulationRequest(BaseModel):
    """
    Fire a burst of simulated scan events for a vendor.
    Supports either:
      - `customers`: Number of repeat customers to simulate (each gets 3–5 realistic scans)
      - or `num_scans` / `num_customers`
    """
    vendor_id: str = Field(..., description="Target vendor ID, e.g. 'sharma_chai_001'")
    customers: Optional[int] = Field(
        default=None,
        ge=1,
        le=500,
        description="Number of repeat customers to simulate (scans >= 3 each)"
    )
    num_scans: Optional[int] = Field(default=None, ge=1, le=2000)
    num_customers: Optional[int] = Field(default=None, ge=1, le=500)
    min_amount: float = Field(default=15.0, ge=0, description="Min INR amount per scan")
    max_amount: float = Field(default=50.0, ge=0, description="Max INR amount per scan")
    dispute_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Fraction of scans marked as dispute")


class BurstSimulationResponse(BaseModel):
    status: str = "ok"
    vendor_id: str
    customers_simulated: int
    scans_inserted: int
    repeat_customers_total: int
    trust_score: float
    tier: str
    badge_visible: bool
    message: str


class SingleScanSimulationRequest(BaseModel):
    """Simulate a single live QR scan event for individual processing demo."""
    vendor_id: str = Field(default="sharma_chai_001", description="Target vendor ID")
    amount: float = Field(default=25.0, ge=0.0, description="Simulated payment amount in INR")
    customer_id: Optional[str] = Field(
        default=None,
        description="Optional customer ID string; auto-generated if omitted"
    )


class ResetRequest(BaseModel):
    """Reset all scan data for a specific vendor (or all vendors if vendor_id is omitted)."""
    vendor_id: Optional[str] = Field(default=None, description="Vendor ID to reset")


class ResetResponse(BaseModel):
    status: str = "ok"
    message: str
    vendors_affected: int
    vendor_id: Optional[str] = None
