from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime


class DocumentTemplateBase(BaseModel):
    type: str = Field(..., description="invoice, receipt, job_sheet, barcode_label, delivery_challan, estimate")
    name: str
    paper_width: str = Field(default="80mm", description="58mm, 80mm, A4")
    html_body: str
    variables: List[str] = Field(default_factory=list, description="Available / used {{variable}} tokens")
    is_default: bool = False
    is_active: bool = True
    branch_id: Optional[str] = None


class DocumentTemplateCreate(DocumentTemplateBase):
    pass


class DocumentTemplateUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    paper_width: Optional[str] = None
    html_body: Optional[str] = None
    variables: Optional[List[str]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class DocumentTemplateResponse(DocumentTemplateBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentTemplateRenderRequest(BaseModel):
    template_id: Optional[str] = None
    html_body: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict, description="Variables to interpolate")


class DocumentTemplateRenderResponse(BaseModel):
    rendered_html: str
    paper_width: str
