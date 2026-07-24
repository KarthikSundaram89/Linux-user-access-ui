"""
Server Lookup Routes.
Handles EC2 inventory lookup and live AWS status checks.
When a user enters server IPs, this endpoint looks them up in the daily
EC2 inventory file and returns account name, region, name tag, application
name tag, OS tag. It also makes a live AWS API call to show current status.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...models.user import User
from ..dependencies.auth import get_current_user
from ...services.inventory.ec2_inventory import ec2_inventory_service
from ...services.inventory.aws_ec2_status import aws_ec2_status_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/servers", tags=["Servers"])


class ServerLookupRequest(BaseModel):
    """Request body for server lookup."""
    servers: List[str]  # List of IPs or hostnames


class ServerLookupResult(BaseModel):
    """Result for a single server lookup."""
    identifier: str
    found: bool = False
    # From EC2 inventory file
    private_ip: str = ""
    public_ip: str = ""
    instance_id: str = ""
    account_name: str = ""
    account_id: str = ""
    region: str = ""
    name_tag: str = ""
    application_tag: str = ""
    os_tag: str = ""
    instance_type: str = ""
    hostname: str = ""
    # Live AWS status
    live_status: str = ""  # running, stopped, terminated, unknown
    live_status_error: str = ""


class ServerLookupResponse(BaseModel):
    """Response for server lookup."""
    results: List[ServerLookupResult]
    total: int
    found: int
    not_found: int


@router.post("/lookup", response_model=ServerLookupResponse)
async def lookup_servers(
    request: ServerLookupRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Look up servers by IP address or hostname in the daily EC2 inventory file.
    Returns account name, region, name tag, application name tag, OS tag for each.
    Also makes a live AWS API call to show current EC2 status (running/stopped).
    Uses the account_name from inventory to determine which AWS profile to use.
    """
    if not request.servers:
        raise HTTPException(status_code=400, detail="No servers provided")

    if len(request.servers) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 servers per lookup")

    results = []
    live_status_requests = []

    for identifier in request.servers:
        identifier = identifier.strip()
        if not identifier:
            continue

        # Look up in EC2 inventory file
        server_info = ec2_inventory_service.lookup_server(identifier)

        if server_info:
            result = ServerLookupResult(
                identifier=identifier,
                found=True,
                private_ip=server_info.private_ip,
                public_ip=server_info.public_ip,
                instance_id=server_info.instance_id,
                account_name=server_info.account_name,
                account_id=server_info.account_id,
                region=server_info.region,
                name_tag=server_info.name_tag,
                application_tag=server_info.application_tag,
                os_tag=server_info.os_tag,
                instance_type=server_info.instance_type,
                hostname=server_info.hostname,
            )
            results.append(result)

            # Queue for live status check if we have instance_id
            if server_info.instance_id:
                live_status_requests.append({
                    "instance_id": server_info.instance_id,
                    "account_name": server_info.account_name,
                    "region": server_info.region,
                    "result_index": len(results) - 1,
                })
        else:
            results.append(ServerLookupResult(
                identifier=identifier,
                found=False,
            ))

    # Make live AWS API calls for found servers
    if live_status_requests:
        try:
            status_map = await aws_ec2_status_service.get_multiple_statuses(
                live_status_requests
            )

            # Map results back
            for req in live_status_requests:
                instance_id = req["instance_id"]
                idx = req["result_index"]
                if instance_id in status_map:
                    status_info = status_map[instance_id]
                    results[idx].live_status = status_info.get("state", "unknown")
                    results[idx].live_status_error = status_info.get("error", "") or ""
                else:
                    results[idx].live_status = "unknown"
                    results[idx].live_status_error = "No response from AWS"

        except Exception as e:
            logger.error(f"Live status check failed: {str(e)}")
            # Don't fail the whole request - just mark status as unknown
            for req in live_status_requests:
                idx = req["result_index"]
                results[idx].live_status = "unknown"
                results[idx].live_status_error = f"AWS API error: {str(e)}"

    found_count = sum(1 for r in results if r.found)

    return ServerLookupResponse(
        results=results,
        total=len(results),
        found=found_count,
        not_found=len(results) - found_count,
    )


@router.get("/inventory/stats")
async def get_inventory_stats(
    current_user: User = Depends(get_current_user),
):
    """Get EC2 inventory file statistics."""
    stats = ec2_inventory_service.get_inventory_stats()
    return stats


@router.get("/lookup/{identifier}")
async def lookup_single_server(
    identifier: str,
    current_user: User = Depends(get_current_user),
):
    """Look up a single server by IP or hostname."""
    server_info = ec2_inventory_service.lookup_server(identifier)

    if not server_info:
        raise HTTPException(status_code=404, detail=f"Server '{identifier}' not found in EC2 inventory")

    result = server_info.to_dict()

    # Get live status
    if server_info.instance_id:
        try:
            status = await aws_ec2_status_service.get_instance_status(
                server_info.instance_id,
                server_info.account_name,
                server_info.region,
            )
            result["live_status"] = status.get("state", "unknown")
            result["live_status_error"] = status.get("error", "")
        except Exception as e:
            result["live_status"] = "unknown"
            result["live_status_error"] = str(e)
    else:
        result["live_status"] = "no_instance_id"
        result["live_status_error"] = "No instance ID in inventory"

    return result
