import csv
import io
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.deps import get_db, require_permission
from app.models.user import User
from app.models.client import Client
from app.models.asset import Asset
from app.models.client_interaction import ClientInteraction
from app.schemas.client import (
    ClientCreate,
    ClientUpdate,
    ClientQuickCreate,
    ClientResponse,
    ClientListResponse,
    AssetCreate,
    AssetUpdate,
    AssetResponse,
    ClientInteractionCreate,
    ClientInteractionResponse,
    ClientFinancialSummary,
)
from app.models.base import generate_uuid
from app.services.client_service import (
    validate_gstin,
    extract_state_from_gstin,
    calculate_client_financial_summary,
)
from app.services.audit import log_audit_event

router = APIRouter(prefix="/clients", tags=["Clients & Assets CRM"])


# 1. List Clients (Paginated, Searchable, Filterable)
@router.get("", response_model=ClientListResponse)
async def list_clients(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by phone, name, email, or GSTIN"),
    client_type: Optional[str] = Query(None, description="Filter by individual or corporate"),
    tag: Optional[str] = Query(None, description="Filter by tag (e.g. VIP, difficult, prompt_payer)"),
    branch_id: Optional[str] = Query(None, description="Filter by branch"),
    is_active: Optional[bool] = Query(True, description="Filter active clients"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "VIEW_ONLY")),
):
    offset = (page - 1) * limit
    base_stmt = select(Client).options(selectinload(Client.assets))

    if is_active is not None:
        base_stmt = base_stmt.where(Client.is_active == is_active)
    if client_type:
        base_stmt = base_stmt.where(Client.client_type == client_type)
    if branch_id:
        base_stmt = base_stmt.where((Client.branch_id == branch_id) | (Client.branch_id == None))

    if search:
        s = f"%{search.strip()}%"
        base_stmt = base_stmt.where(
            or_(
                Client.name.ilike(s),
                Client.phone.ilike(s),
                Client.email.ilike(s),
                Client.gstin.ilike(s),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Paginate
    stmt = base_stmt.order_by(Client.created_at.desc()).offset(offset).limit(limit)
    res = await db.execute(stmt)
    items = res.scalars().all()

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    return ClientListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


# 2. Create Client (Full)
@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "LOOKUP/CREATE")),
):
    # Validate GSTIN if provided
    if payload.gstin:
        cleaned_gstin = payload.gstin.strip().upper()
        if not validate_gstin(cleaned_gstin):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Indian GSTIN format '{payload.gstin}'. Expected 15-character alphanumeric format (e.g. 27AAFCO1234F1Z5).",
            )

    # Normalize phone: remove spaces and hyphens
    normalized_phone = re_clean_phone(payload.phone)

    client = Client(
        id=generate_uuid(),
        branch_id=payload.branch_id or current_user.branch_id,
        client_type=payload.client_type,
        name=payload.name.strip(),
        phone=normalized_phone,
        email=payload.email.strip().lower() if payload.email else None,
        contacts=[c.model_dump() for c in payload.contacts],
        billing_addresses=[a.model_dump() for a in payload.billing_addresses],
        gstin=payload.gstin.strip().upper() if payload.gstin else None,
        pan=payload.pan.strip().upper() if payload.pan else None,
        credit_limit=payload.credit_limit,
        credit_period_days=payload.credit_period_days,
        discount_terms=payload.discount_terms,
        amc=payload.amc.model_dump(),
        tags=payload.tags,
        messaging_opt_in=payload.messaging_opt_in.model_dump(),
        notes=payload.notes,
        custom_fields=payload.custom_fields,
        is_active=payload.is_active,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)

    # Automatically log creation interaction
    interaction = ClientInteraction(
        id=generate_uuid(),
        client_id=client.id,
        branch_id=client.branch_id,
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role.name if current_user.role else "Staff",
        type="note",
        direction="internal",
        title="Customer Profile Created",
        details=f"Client '{client.name}' registered as {client.client_type.upper()}.",
    )
    db.add(interaction)
    await db.commit()

    await log_audit_event(
        db=db,
        action="CLIENT_CREATE",
        module="clients",
        entity="clients",
        entity_id=client.id,
        actor_id=current_user.id,
        after_state={"name": client.name, "phone": client.phone, "type": client.client_type},
    )

    # Reload with assets
    stmt = select(Client).options(selectinload(Client.assets)).where(Client.id == client.id)
    return (await db.execute(stmt)).scalar_one()


# 3. Quick Create Client (Slide-over drawer for Ticket Intake & POS Checkout)
@router.post("/quick-create", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def quick_create_client(
    payload: ClientQuickCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "LOOKUP/CREATE")),
):
    normalized_phone = re_clean_phone(payload.phone)

    # Check if client with this phone already exists
    stmt = (
        select(Client)
        .options(selectinload(Client.assets))
        .where(Client.phone == normalized_phone)
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        # If an initial asset was provided, add it to the existing client
        if payload.asset_name and payload.asset_identifier:
            asset = Asset(
                id=generate_uuid(),
                client_id=existing.id,
                branch_id=existing.branch_id,
                name=payload.asset_name.strip(),
                asset_type=payload.asset_type or "device",
                identifier=payload.asset_identifier.strip(),
                dynamic_attributes={},
                warranty_status="none",
                is_active=True,
            )
            db.add(asset)
            await db.commit()
            await db.refresh(existing)
        return existing

    # Create new client
    client = Client(
        id=generate_uuid(),
        branch_id=payload.branch_id or current_user.branch_id,
        client_type=payload.client_type,
        name=payload.name.strip(),
        phone=normalized_phone,
        email=payload.email.strip().lower() if payload.email else None,
        contacts=[],
        billing_addresses=[],
        tags=["new_customer"],
        is_active=True,
    )
    db.add(client)
    await db.flush()

    # Optional initial asset
    if payload.asset_name and payload.asset_identifier:
        asset = Asset(
            id=generate_uuid(),
            client_id=client.id,
            branch_id=client.branch_id,
            name=payload.asset_name.strip(),
            asset_type=payload.asset_type or "device",
            identifier=payload.asset_identifier.strip(),
            dynamic_attributes={},
            warranty_status="none",
            is_active=True,
        )
        db.add(asset)

    await db.commit()
    await db.refresh(client)

    stmt = select(Client).options(selectinload(Client.assets)).where(Client.id == client.id)
    return (await db.execute(stmt)).scalar_one()


# 4. Get Client Profile
@router.get("/{id}", response_model=ClientResponse)
async def get_client(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "VIEW_ONLY")),
):
    stmt = (
        select(Client)
        .options(selectinload(Client.assets))
        .where(Client.id == id)
    )
    client = (await db.execute(stmt)).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


# 5. Update Client
@router.put("/{id}", response_model=ClientResponse)
async def update_client(
    id: str,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "LOOKUP/CREATE")),
):
    stmt = select(Client).options(selectinload(Client.assets)).where(Client.id == id)
    client = (await db.execute(stmt)).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    update_dict = payload.model_dump(exclude_unset=True)

    if "gstin" in update_dict and update_dict["gstin"]:
        cleaned_gstin = update_dict["gstin"].strip().upper()
        if not validate_gstin(cleaned_gstin):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Indian GSTIN format '{update_dict['gstin']}'.",
            )
        update_dict["gstin"] = cleaned_gstin

    if "phone" in update_dict and update_dict["phone"]:
        update_dict["phone"] = re_clean_phone(update_dict["phone"])

    if "contacts" in update_dict and update_dict["contacts"] is not None:
        update_dict["contacts"] = [c.model_dump() if hasattr(c, "model_dump") else c for c in update_dict["contacts"]]

    if "billing_addresses" in update_dict and update_dict["billing_addresses"] is not None:
        update_dict["billing_addresses"] = [a.model_dump() if hasattr(a, "model_dump") else a for a in update_dict["billing_addresses"]]

    if "amc" in update_dict and update_dict["amc"] is not None:
        update_dict["amc"] = update_dict["amc"].model_dump() if hasattr(update_dict["amc"], "model_dump") else update_dict["amc"]

    if "messaging_opt_in" in update_dict and update_dict["messaging_opt_in"] is not None:
        update_dict["messaging_opt_in"] = update_dict["messaging_opt_in"].model_dump() if hasattr(update_dict["messaging_opt_in"], "model_dump") else update_dict["messaging_opt_in"]

    for k, v in update_dict.items():
        setattr(client, k, v)

    await db.commit()
    await db.refresh(client)

    await log_audit_event(
        db=db,
        action="CLIENT_UPDATE",
        module="clients",
        entity="clients",
        entity_id=client.id,
        actor_id=current_user.id,
        after_state=update_dict,
    )

    return client


# 6. Delete / Deactivate Client
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "FULL")),
):
    stmt = select(Client).where(Client.id == id)
    client = (await db.execute(stmt)).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    client.is_active = False
    await db.commit()

    await log_audit_event(
        db=db,
        action="CLIENT_DEACTIVATE",
        module="clients",
        entity="clients",
        entity_id=id,
        actor_id=current_user.id,
    )


# 7. Financial Summary & Aging Breakdown (LTV + Outstanding Aging)
@router.get("/{id}/financial-summary", response_model=ClientFinancialSummary)
async def get_client_financial_summary(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "VIEW_ONLY")),
):
    stmt = select(Client).where(Client.id == id)
    client = (await db.execute(stmt)).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    return await calculate_client_financial_summary(db, client)


# 8. Asset Registry Endpoints
@router.get("/{id}/assets", response_model=List[AssetResponse])
async def list_client_assets(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "VIEW_ONLY")),
):
    stmt = select(Asset).where(Asset.client_id == id).order_by(Asset.created_at.desc())
    return (await db.execute(stmt)).scalars().all()


@router.post("/{id}/assets", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_client_asset(
    id: str,
    payload: AssetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "LOOKUP/CREATE")),
):
    client = (await db.execute(select(Client).where(Client.id == id))).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    asset = Asset(
        id=generate_uuid(),
        client_id=id,
        branch_id=payload.branch_id or client.branch_id,
        name=payload.name.strip(),
        brand=payload.brand.strip() if payload.brand else None,
        model=payload.model.strip() if payload.model else None,
        asset_type=payload.asset_type,
        identifier=payload.identifier.strip(),
        dynamic_attributes=payload.dynamic_attributes,
        warranty_status=payload.warranty_status,
        warranty_expiry=payload.warranty_expiry,
        purchase_date=payload.purchase_date,
        notes=payload.notes,
        is_active=payload.is_active,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    # Log interaction
    interaction = ClientInteraction(
        id=generate_uuid(),
        client_id=client.id,
        branch_id=client.branch_id,
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role.name if current_user.role else "Staff",
        type="note",
        direction="internal",
        title="Asset Registered",
        details=f"Asset '{asset.name}' (ID/Serial: {asset.identifier}) added to customer registry.",
    )
    db.add(interaction)
    await db.commit()

    return asset


@router.put("/assets/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "LOOKUP/CREATE")),
):
    stmt = select(Asset).where(Asset.id == asset_id)
    asset = (await db.execute(stmt)).scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(asset, k, v)

    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "FULL")),
):
    stmt = select(Asset).where(Asset.id == asset_id)
    asset = (await db.execute(stmt)).scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    await db.delete(asset)
    await db.commit()


@router.get("/assets/lookup", response_model=List[AssetResponse])
async def lookup_asset(
    identifier: str = Query(..., description="Serial number, IMEI, VIN, or Vehicle Reg No"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "VIEW_ONLY")),
):
    s = f"%{identifier.strip()}%"
    stmt = (
        select(Asset)
        .options(selectinload(Asset.client))
        .where(Asset.identifier.ilike(s))
        .order_by(Asset.created_at.desc())
    )
    return (await db.execute(stmt)).scalars().all()


# 9. Timeline & Interaction Logs
@router.get("/{id}/interactions", response_model=List[ClientInteractionResponse])
async def list_interactions(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "VIEW_ONLY")),
):
    stmt = (
        select(ClientInteraction)
        .where(ClientInteraction.client_id == id)
        .order_by(ClientInteraction.created_at.desc())
    )
    return (await db.execute(stmt)).scalars().all()


@router.post("/{id}/interactions", response_model=ClientInteractionResponse, status_code=status.HTTP_201_CREATED)
async def log_interaction(
    id: str,
    payload: ClientInteractionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "LOOKUP/CREATE")),
):
    client = (await db.execute(select(Client).where(Client.id == id))).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    interaction = ClientInteraction(
        id=generate_uuid(),
        client_id=id,
        branch_id=client.branch_id,
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role.name if current_user.role else "Staff",
        type=payload.type,
        direction=payload.direction,
        title=payload.title,
        details=payload.details,
        extra_metadata=payload.extra_metadata,
    )
    db.add(interaction)
    await db.commit()
    await db.refresh(interaction)
    return interaction


# 10. Bulk CSV Export & Import
@router.get("/export")
async def export_clients_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("clients", "VIEW_ONLY")),
):
    stmt = select(Client).order_by(Client.name.asc())
    clients = (await db.execute(stmt)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Name", "Phone", "Email", "Type", "GSTIN", "Credit Limit",
        "Credit Period (Days)", "Tags", "Total Spent (LTV)", "Outstanding Balance", "Created At"
    ])

    for c in clients:
        writer.writerow([
            c.id, c.name, c.phone, c.email or "", c.client_type, c.gstin or "",
            c.credit_limit, c.credit_period_days, ",".join(c.tags or []),
            c.total_spent, c.outstanding_balance, c.created_at.isoformat()
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=omnisuite_clients.csv"},
    )


def re_clean_phone(phone: str) -> str:
    """Cleans phone numbers into compact standard format."""
    return re.sub(r"[^\d+]", "", phone.strip())
