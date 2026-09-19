"""
schemas/scan.py
---------------
Request/response schemas for the POST /api/scans endpoint.
Strictly ensures no customer_hash or individual transaction history is leaked.
"""

import hashlib
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

from app.schemas.vendor import BadgePayload


class ScanRequest(BaseModel):
    """
    Simulated QR scan event sent by the frontend or scanner simulator.
    customer_hash: SHA-256 of customer identifier (e.g. phone/account) computed client-side.
    Guaranteed: If a raw customer identifier is accidentally supplied, it is automatically
    hashed server-side so plaintext identifiers are NEVER persisted or processed.
    """
    vendor_id: str = Field(..., min_length=1, max_length=100, description="Unique vendor ID")
    customer_hash: str = Field(..., min_length=1, description="SHA-256 hash of customer identifier")
    amount: float = Field(default=0.0, ge=0.0, le=100000.0, description="Simulated payment amount in INR")
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Optional scan timestamp. Defaults to now if not provided."
    )

    @field_validator("customer_hash")
    @classmethod
    def ensure_sha256_hash(cls, v: str) -> str:
        v = v.strip()
        # If already a valid 64-character hex SHA-256 digest, preserve lowercase hex
        if len(v) == 64 and all(c in "0123456789abcdefABCDEF" for c in v):
            return v.lower()
        # Privacy defense-in-depth: hash immediately so plaintext PII is never stored
        return hashlib.sha256(v.encode("utf-8")).hexdigest()



class PipelineEvent(BaseModel):
    """Internal trace event of the QR scan processing pipeline."""
    stage: str = Field(..., description="Stage name (e.g. SCAN_RECEIVED, TRUST_CALCULATED)")
    timestamp: datetime = Field(..., description="Timestamp when the stage was completed")
    message: str = Field(..., description="Human-readable stage description")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Privacy-safe stage metrics (no customer hashes or raw transaction histories)"
    )


class ProcessingStageItem(BaseModel):
    """Granular 12-stage processing breakdown for developer/demo mode."""
    step: int = Field(..., description="Stage sequence number (1-12)")
    name: str = Field(..., description="Human-readable stage title")
    stage_id: str = Field(..., description="Machine identifier for the stage")
    status: str = Field(..., description="Status of the stage, e.g. COMPLETED, PASSED, MASKED")
    timestamp: str = Field(..., description="ISO or formatted timestamp")
    explanation: str = Field(..., description="Short explanation of what occurred")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-identifiable telemetry metrics"
    )


class ScanResponse(BaseModel):
    """
    Aggregated response returned to the client after QR scan processing.
    Privacy rules strictly enforced:
      - NO customer_hash is ever returned
      - NO individual customer or transaction history is exposed
      - Only aggregated trust/badge data and pipeline stage logs are returned
    """
    status: str = "success"
    scan_id: str
    vendor_id: str
    timestamp: datetime
    badge: BadgePayload
    pipeline_events: list[PipelineEvent] = Field(default_factory=list)
    processing_details: list[ProcessingStageItem] = Field(default_factory=list)
