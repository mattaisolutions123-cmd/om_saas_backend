import re
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.deps import get_db, require_permission
from app.models.user import User
from app.models.template import DocumentTemplate
from app.schemas.template import (
    DocumentTemplateCreate,
    DocumentTemplateUpdate,
    DocumentTemplateResponse,
    DocumentTemplateRenderRequest,
    DocumentTemplateRenderResponse,
)
from app.models.base import generate_uuid

router = APIRouter(prefix="/settings/document-templates", tags=["Settings - Templates"])


@router.get("", response_model=List[DocumentTemplateResponse])
async def list_templates(
    template_type: Optional[str] = Query(None, description="Filter by type: invoice, receipt, job_sheet, barcode_label, delivery_challan, estimate"),
    branch_id: Optional[str] = Query(None, description="Filter by branch"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = select(DocumentTemplate).order_by(DocumentTemplate.created_at.asc())
    if template_type:
        stmt = stmt.where(DocumentTemplate.type == template_type)
    if branch_id is not None:
        stmt = stmt.where((DocumentTemplate.branch_id == branch_id) | (DocumentTemplate.branch_id == None))

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=DocumentTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: DocumentTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    # Auto-extract {{variable}} tokens from html_body if variables list is empty
    variables = payload.variables
    if not variables:
        found = re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", payload.html_body)
        variables = list(dict.fromkeys(found))

    tmpl = DocumentTemplate(
        id=generate_uuid(),
        branch_id=payload.branch_id,
        type=payload.type,
        name=payload.name,
        paper_width=payload.paper_width,
        html_body=payload.html_body,
        variables=variables,
        is_default=payload.is_default,
        is_active=payload.is_active,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.get("/{id}", response_model=DocumentTemplateResponse)
async def get_template(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = select(DocumentTemplate).where(DocumentTemplate.id == id)
    tmpl = (await db.execute(stmt)).scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return tmpl


@router.put("/{id}", response_model=DocumentTemplateResponse)
async def update_template(
    id: str,
    payload: DocumentTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(DocumentTemplate).where(DocumentTemplate.id == id)
    tmpl = (await db.execute(stmt)).scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "html_body" in update_data and not update_data.get("variables"):
        found = re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", update_data["html_body"])
        update_data["variables"] = list(dict.fromkeys(found))

    for k, v in update_data.items():
        setattr(tmpl, k, v)

    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(DocumentTemplate).where(DocumentTemplate.id == id)
    tmpl = (await db.execute(stmt)).scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    await db.delete(tmpl)
    await db.commit()


@router.post("/render-preview", response_model=DocumentTemplateRenderResponse)
async def render_preview(
    payload: DocumentTemplateRenderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    raw_html = payload.html_body
    paper_width = "80mm"

    if payload.template_id:
        stmt = select(DocumentTemplate).where(DocumentTemplate.id == payload.template_id)
        tmpl = (await db.execute(stmt)).scalar_one_or_none()
        if tmpl:
            raw_html = tmpl.html_body
            paper_width = tmpl.paper_width

    if not raw_html:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No html_body or template_id provided")

    # Sample standard mock variables if not supplied
    default_context = {
        "company_name": "OmniSuite Enterprise Repairs",
        "branch_name": "Flagship Hub - Mumbai",
        "branch_phone": "+91 98765 43210",
        "branch_address": "Shop 4, Linking Road, Bandra West, Mumbai 400050",
        "branch_gstin": "27AABCO1234F1Z5",
        "state_code": "27 (Maharashtra)",
        "ticket_number": "TKT-8902",
        "invoice_number": "INV-2026-0842",
        "invoice_date": "19 Nov 2026",
        "created_at": "19 Nov 2026, 11:30 AM",
        "customer_name": "Aarav Sharma",
        "customer_phone": "+91 98201 12345",
        "brand_model": "Apple iPhone 14 Pro",
        "defect_name": "Cracked OLED Screen + Battery Service",
        "appliance_type": "Three Phase Induction Motor",
        "power_rating_hp": "7.5",
        "voltage_phase": "415V 3-Phase",
        "copper_weight_kg": "4.2",
        "copper_wire_swg": "21 SWG",
        "vehicle_reg_no": "MH 02 CD 1234",
        "odometer_reading_km": "45,210",
        "fuel_type": "Petrol",
        "fuel_level": "1/2 Tank",
        "service_advisor_notes": "Squeaking brake pads & regular 10K service",
        "imei_serial_no": "358920192837461",
        "device_passcode": "7294",
        "service_mode": "Split AC Deep Cleaning",
        "spec_measurement_units": "1.5 Ton",
        "refrigerant_or_fabric_type": "R32 Eco Gas",
        "scheduled_visit_date": "21 Nov 2026",
        "special_instructions": "Customer requested evening slot after 5 PM",
        "items_rows": "<tr><td style='border: 1px solid #cbd5e1; padding: 6px;'>Replacement Super Retina OLED</td><td style='border: 1px solid #cbd5e1; padding: 6px; text-align: right;'>1</td><td style='border: 1px solid #cbd5e1; padding: 6px; text-align: right;'>4,500.00</td><td style='border: 1px solid #cbd5e1; padding: 6px; text-align: right;'>4,500.00</td></tr><tr><td style='border: 1px solid #cbd5e1; padding: 6px;'>Bench Labor & Diagnostics</td><td style='border: 1px solid #cbd5e1; padding: 6px; text-align: right;'>1</td><td style='border: 1px solid #cbd5e1; padding: 6px; text-align: right;'>1,200.00</td><td style='border: 1px solid #cbd5e1; padding: 6px; text-align: right;'>1,200.00</td></tr>",
        "subtotal": "5,700.00",
        "tax_amount": "1,026.00",
        "total_amount": "6,726.00",
        "paid_amount": "2,000.00",
        "balance_due": "4,726.00",
    }

    merged = {**default_context, **payload.context}

    def replace_token(match):
        token = match.group(1).strip()
        return str(merged.get(token, f"[{token}]"))

    rendered = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replace_token, raw_html)

    return DocumentTemplateRenderResponse(
        rendered_html=rendered,
        paper_width=paper_width,
    )
