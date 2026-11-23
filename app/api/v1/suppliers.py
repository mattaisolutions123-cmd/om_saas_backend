from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.db.session import get_db
from app.models.supplier import Supplier
from app.models.procurement import PurchaseOrder
from app.schemas.supplier import (
    SupplierCreate,
    SupplierUpdate,
    SupplierResponse,
    SupplierListResponse,
)
from app.services.audit import log_audit_event

router = APIRouter(prefix="/suppliers", tags=["Suppliers & Vendors"])


@router.get("", response_model=SupplierListResponse)
async def list_suppliers(
    search: Optional[str] = Query(None, description="Search by name, phone, GSTIN"),
    supplier_type: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Supplier)
    if is_active is not None:
        query = query.where(Supplier.is_active == is_active)
    if supplier_type:
        query = query.where(Supplier.supplier_type == supplier_type)
    if branch_id:
        query = query.where(or_(Supplier.branch_id == branch_id, Supplier.branch_id == None))
    if search:
        search_fmt = f"%{search.strip()}%"
        query = query.where(
            or_(
                Supplier.name.ilike(search_fmt),
                Supplier.phone.ilike(search_fmt),
                Supplier.gstin.ilike(search_fmt),
                Supplier.contact_name.ilike(search_fmt),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Supplier.name.asc()).offset(skip).limit(limit)
    items = (await db.execute(query)).scalars().all()

    # Enrich with purchase totals
    resp_items = []
    for s in items:
        orders_res = await db.execute(
            select(
                func.count(PurchaseOrder.id),
                func.coalesce(func.sum(PurchaseOrder.grand_total), 0.0),
            ).where(PurchaseOrder.supplier_id == s.id)
        )
        orders_count, purchases_val = orders_res.first() or (0, 0.0)

        resp_items.append(
            SupplierResponse(
                id=s.id,
                branch_id=s.branch_id,
                name=s.name,
                supplier_type=s.supplier_type,
                contact_name=s.contact_name,
                phone=s.phone,
                email=s.email,
                gstin=s.gstin,
                pan=s.pan,
                credit_period_days=s.credit_period_days,
                credit_limit=s.credit_limit,
                payment_terms=s.payment_terms,
                address=s.address,
                city=s.city,
                state=s.state,
                state_code=s.state_code,
                pincode=s.pincode,
                bank_details=s.bank_details or {},
                rating=s.rating,
                tags=s.tags or [],
                notes=s.notes,
                is_active=s.is_active,
                total_orders_count=orders_count,
                total_purchases_amount=float(purchases_val),
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
        )

    return SupplierListResponse(items=resp_items, total=total)


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    payload: SupplierCreate,
    db: AsyncSession = Depends(get_db),
):
    supplier = Supplier(
        branch_id=payload.branch_id,
        name=payload.name.strip(),
        supplier_type=payload.supplier_type,
        contact_name=payload.contact_name.strip() if payload.contact_name else None,
        phone=payload.phone.strip(),
        email=payload.email.strip() if payload.email else None,
        gstin=payload.gstin.strip().upper() if payload.gstin else None,
        pan=payload.pan.strip().upper() if payload.pan else None,
        credit_period_days=payload.credit_period_days,
        credit_limit=payload.credit_limit,
        payment_terms=payload.payment_terms.strip(),
        address=payload.address.strip() if payload.address else None,
        city=payload.city.strip() if payload.city else None,
        state=payload.state.strip() if payload.state else None,
        state_code=payload.state_code.strip() if payload.state_code else None,
        pincode=payload.pincode.strip() if payload.pincode else None,
        bank_details=payload.bank_details or {},
        rating=payload.rating,
        tags=payload.tags or [],
        notes=payload.notes.strip() if payload.notes else None,
        is_active=payload.is_active,
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    await log_audit_event(
        db=db,
        action="CREATE",
        entity="supplier",
        entity_id=supplier.id,
        after_state={"name": supplier.name, "phone": supplier.phone, "gstin": supplier.gstin},
    )

    return SupplierResponse(
        id=supplier.id,
        branch_id=supplier.branch_id,
        name=supplier.name,
        supplier_type=supplier.supplier_type,
        contact_name=supplier.contact_name,
        phone=supplier.phone,
        email=supplier.email,
        gstin=supplier.gstin,
        pan=supplier.pan,
        credit_period_days=supplier.credit_period_days,
        credit_limit=supplier.credit_limit,
        payment_terms=supplier.payment_terms,
        address=supplier.address,
        city=supplier.city,
        state=supplier.state,
        state_code=supplier.state_code,
        pincode=supplier.pincode,
        bank_details=supplier.bank_details or {},
        rating=supplier.rating,
        tags=supplier.tags or [],
        notes=supplier.notes,
        is_active=supplier.is_active,
        total_orders_count=0,
        total_purchases_amount=0.0,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )


@router.get("/{id}", response_model=SupplierResponse)
async def get_supplier(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Supplier).where(Supplier.id == id))
    supplier = res.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    orders_res = await db.execute(
        select(
            func.count(PurchaseOrder.id),
            func.coalesce(func.sum(PurchaseOrder.grand_total), 0.0),
        ).where(PurchaseOrder.supplier_id == supplier.id)
    )
    orders_count, purchases_val = orders_res.first() or (0, 0.0)

    return SupplierResponse(
        id=supplier.id,
        branch_id=supplier.branch_id,
        name=supplier.name,
        supplier_type=supplier.supplier_type,
        contact_name=supplier.contact_name,
        phone=supplier.phone,
        email=supplier.email,
        gstin=supplier.gstin,
        pan=supplier.pan,
        credit_period_days=supplier.credit_period_days,
        credit_limit=supplier.credit_limit,
        payment_terms=supplier.payment_terms,
        address=supplier.address,
        city=supplier.city,
        state=supplier.state,
        state_code=supplier.state_code,
        pincode=supplier.pincode,
        bank_details=supplier.bank_details or {},
        rating=supplier.rating,
        tags=supplier.tags or [],
        notes=supplier.notes,
        is_active=supplier.is_active,
        total_orders_count=orders_count,
        total_purchases_amount=float(purchases_val),
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )


@router.put("/{id}", response_model=SupplierResponse)
async def update_supplier(
    id: str,
    payload: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Supplier).where(Supplier.id == id))
    supplier = res.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    update_data = payload.dict(exclude_unset=True)
    for field, val in update_data.items():
        setattr(supplier, field, val)

    await db.commit()
    await db.refresh(supplier)

    return SupplierResponse(
        id=supplier.id,
        branch_id=supplier.branch_id,
        name=supplier.name,
        supplier_type=supplier.supplier_type,
        contact_name=supplier.contact_name,
        phone=supplier.phone,
        email=supplier.email,
        gstin=supplier.gstin,
        pan=supplier.pan,
        credit_period_days=supplier.credit_period_days,
        credit_limit=supplier.credit_limit,
        payment_terms=supplier.payment_terms,
        address=supplier.address,
        city=supplier.city,
        state=supplier.state,
        state_code=supplier.state_code,
        pincode=supplier.pincode,
        bank_details=supplier.bank_details or {},
        rating=supplier.rating,
        tags=supplier.tags or [],
        notes=supplier.notes,
        is_active=supplier.is_active,
        total_orders_count=0,
        total_purchases_amount=0.0,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )
