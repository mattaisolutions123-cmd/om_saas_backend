from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime


# Handbook Item Schemas
class HandbookItemBase(BaseModel):
    code: str
    name: str
    parent_id: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True
    extra_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Multi-language labels, e.g. {'labels': {'hi': '...', 'mr': '...'}}, rates, etc.",
    )


class HandbookItemCreate(HandbookItemBase):
    handbook_id: Optional[str] = None


class HandbookItemUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    parent_id: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    extra_data: Optional[Dict[str, Any]] = None


class HandbookItemResponse(HandbookItemBase):
    id: str
    handbook_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HandbookItemTreeNode(HandbookItemResponse):
    children: List["HandbookItemTreeNode"] = []


# Handbook Schemas
class HandbookBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    is_hierarchical: bool = False
    is_system: bool = False
    is_active: bool = True
    branch_id: Optional[str] = None


class HandbookCreate(HandbookBase):
    pass


class HandbookUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class HandbookResponse(HandbookBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HandbookDetailResponse(HandbookResponse):
    items: List[HandbookItemResponse] = []
