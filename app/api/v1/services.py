from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.db.session import get_db
from app.models.service_catalog import ServiceCatalogItem
from app.schemas.service_catalog import (
    ServiceCatalogItemCreate,
    ServiceCatalogItemUpdate,
    ServiceCatalogItemResponse,
    ServiceCatalogListResponse,
)
from app.services.audit import log_audit_event

router = APIRouter(prefix="/services", tags=["Services Catalog"])


@router.get("", response_model=ServiceCatalogListResponse)
async def list_services(
    search: Optional[str] = Query(None, description="Search by name, SAC, or category"),
    category: Optional[str] = Query(None, description="Filter by category"),
    branch_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(ServiceCatalogItem)
    if is_active is not None:
        query = query.where(ServiceCatalogItem.is_active == is_active)
    if category:
        query = query.where(ServiceCatalogItem.category == category)
    if branch_id:
        query = query.where(or_(ServiceCatalogItem.branch_id == branch_id, ServiceCatalogItem.branch_id == None))
    if search:
        search_fmt = f"%{search.strip()}%"
        query = query.where(
            or_(
                ServiceCatalogItem.name.ilike(search_fmt),
                ServiceCatalogItem.sac_code.ilike(search_fmt),
                ServiceCatalogItem.category.ilike(search_fmt),
                ServiceCatalogItem.description.ilike(search_fmt),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(ServiceCatalogItem.name.asc()).offset(skip).limit(limit)
    items = (await db.execute(query)).scalars().all()

    return ServiceCatalogListResponse(items=items, total=total)


@router.post("", response_model=ServiceCatalogItemResponse, status_code=status.HTTP_201_CREATED)
async def create_service_item(
    payload: ServiceCatalogItemCreate,
    db: AsyncSession = Depends(get_db),
):
    item = ServiceCatalogItem(
        branch_id=payload.branch_id,
        name=payload.name.strip(),
        category=payload.category.strip(),
        sac_code=payload.sac_code.strip(),
        description=payload.description.strip() if payload.description else None,
        labor_price=payload.labor_price,
        duration_minutes=payload.duration_minutes,
        gst_rate=payload.gst_rate,
        warranty_days=payload.warranty_days,
        commission_rate=payload.commission_rate,
        is_active=payload.is_active,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    await log_audit_event(
        db=db,
        action="CREATE",
        entity="service_catalog_item",
        entity_id=item.id,
        after_state={"name": item.name, "labor_price": item.labor_price, "sac_code": item.sac_code},
    )
    return item


@router.get("/{id}", response_model=ServiceCatalogItemResponse)
async def get_service_item(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(ServiceCatalogItem).where(ServiceCatalogItem.id == id))
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Service rate card item not found")
    return item


@router.put("/{id}", response_model=ServiceCatalogItemResponse)
async def update_service_item(
    id: str,
    payload: ServiceCatalogItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(ServiceCatalogItem).where(ServiceCatalogItem.id == id))
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Service rate card item not found")

    old_vals = {"name": item.name, "labor_price": item.labor_price}
    update_data = payload.dict(exclude_unset=True)
    for field, val in update_data.items():
        setattr(item, field, val)

    await db.commit()
    await db.refresh(item)

    await log_audit_event(
        db=db,
        action="UPDATE",
        entity="service_catalog_item",
        entity_id=item.id,
        before_state=old_vals,
        after_state={"name": item.name, "labor_price": item.labor_price},
    )
    return item


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_item(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(ServiceCatalogItem).where(ServiceCatalogItem.id == id))
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Service rate card item not found")

    item.is_active = False
    await db.commit()
    return None
