"""
routes/scans.py
---------------
POST /api/scans
  -> Execute the 7-stage QR scan processing pipeline
  -> Return privacy-safe aggregated trust response with pipeline execution trace
"""

from fastapi import APIRouter
from app.schemas.scan import ScanRequest, ScanResponse
from app.services.scan_pipeline import execute_scan_pipeline

router = APIRouter(prefix="/api/scans", tags=["Scans"])


@router.post("", response_model=ScanResponse, status_code=201)
async def record_scan(payload: ScanRequest):
    """
    Process a simulated QR scan through the complete TrustCircle pipeline:

      SCAN_RECEIVED -> SCAN_STORED -> AGGREGATION_UPDATED ->
      TRUST_CALCULATED -> PRIVACY_CHECK -> BADGE_UPDATED -> WEBSOCKET_BROADCAST

    Privacy guarantees:
      - customer_hash is stored internally, NEVER returned to the client.
      - Individual customer history and raw transactions are NOT exposed.
      - Small repeat-customer counts (< 5) are masked by k-anonymity.
    """
    scan_id, badge, events, processing_details = await execute_scan_pipeline(
        vendor_id=payload.vendor_id,
        customer_hash=payload.customer_hash,
        amount=payload.amount,
        scan_timestamp=payload.timestamp,
    )

    return ScanResponse(
        status="success",
        scan_id=scan_id,
        vendor_id=payload.vendor_id,
        timestamp=payload.timestamp or events[0].timestamp,
        badge=badge,
        pipeline_events=events,
        processing_details=processing_details,
    )
