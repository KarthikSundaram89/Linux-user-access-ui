"""
Reporting Routes.
Generate CSV, Excel, and PDF reports.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.database import get_db
from ...models.user import User
from ...models.request import AccessRequest, RequestStatus, AccessType
from ..dependencies.auth import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["Reports"])



@router.get("/user-access")
async def user_access_report(
    format: str = Query("json", regex="^(json|csv|excel)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Generate user access report."""
    result = await db.execute(
        select(AccessRequest)
        .options(selectinload(AccessRequest.servers))
        .where(AccessRequest.status == RequestStatus.PROVISIONED)
        .order_by(AccessRequest.created_at.desc())
    )
    requests = result.scalars().all()

    data = []
    for req in requests:
        user_result = await db.execute(
            select(User).where(User.id == req.requester_id)
        )
        user = user_result.scalar_one_or_none()
        servers = ", ".join(s.hostname or s.ip_address for s in req.servers)
        data.append({
            "request_id": req.request_id,
            "user": user.display_name if user else "Unknown",
            "email": user.email if user else "Unknown",
            "access_type": req.access_type.value,
            "servers": servers,
            "provisioned_at": str(req.provisioned_at) if req.provisioned_at else "",
            "sudo_expiry": str(req.sudo_expiry_date) if req.sudo_expiry_date else "N/A",
        })

    if format == "csv":
        return _generate_csv(data, "user_access_report")
    elif format == "excel":
        return _generate_excel(data, "user_access_report")
    return {"report": "user_access", "data": data, "total": len(data)}


@router.get("/sudo-access")
async def sudo_access_report(
    format: str = Query("json", regex="^(json|csv|excel)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Generate sudo access report."""
    result = await db.execute(
        select(AccessRequest)
        .options(selectinload(AccessRequest.servers))
        .where(
            AccessRequest.access_type.in_([AccessType.SUDO_ACCESS, AccessType.BOTH, AccessType.RENEW_SUDO]),
            AccessRequest.status == RequestStatus.PROVISIONED,
        )
    )
    requests = result.scalars().all()

    data = []
    now = datetime.now(timezone.utc)
    for req in requests:
        user_result = await db.execute(select(User).where(User.id == req.requester_id))
        user = user_result.scalar_one_or_none()
        servers = ", ".join(s.hostname or s.ip_address for s in req.servers)
        days_remaining = (req.sudo_expiry_date - now).days if req.sudo_expiry_date else 0
        data.append({
            "request_id": req.request_id,
            "user": user.display_name if user else "Unknown",
            "email": user.email if user else "Unknown",
            "servers": servers,
            "expiry_date": str(req.sudo_expiry_date) if req.sudo_expiry_date else "N/A",
            "days_remaining": max(0, days_remaining),
            "status": "Active" if days_remaining > 0 else "Expired",
        })

    if format == "csv":
        return _generate_csv(data, "sudo_access_report")
    elif format == "excel":
        return _generate_excel(data, "sudo_access_report")
    return {"report": "sudo_access", "data": data, "total": len(data)}


@router.get("/monthly-trends")
async def monthly_trends_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Get monthly request trends for charts."""
    result = await db.execute(
        select(
            func.strftime("%Y-%m", AccessRequest.created_at).label("month"),
            func.count(AccessRequest.id).label("count"),
        )
        .group_by("month")
        .order_by("month")
    )
    trends = result.all()
    return {"trends": [{"month": t.month, "count": t.count} for t in trends]}



def _generate_csv(data: list, filename: str) -> StreamingResponse:
    """Generate CSV response."""
    import csv
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
    )


def _generate_excel(data: list, filename: str) -> StreamingResponse:
    """Generate Excel response."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = filename

    if data:
        # Headers
        headers = list(data[0].keys())
        ws.append(headers)
        # Data
        for row in data:
            ws.append(list(row.values()))

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"},
    )
