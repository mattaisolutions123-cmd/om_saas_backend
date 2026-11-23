from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.services.audit import AuditService
from app.services.storage import storage_service

router = APIRouter(prefix="/uploads", tags=["Uploads & Media"])


class DeleteUploadRequest(BaseModel):
    url: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    folder: str = Form(default="general"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticated file upload endpoint.
    Uploads directly to Vercel Blob Storage and returns the public access URL.
    """
    result = await storage_service.upload_file(file=file, folder=folder)

    # Log to audit trail
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    await AuditService.log_event(
        db=db,
        action="FILE_UPLOAD",
        entity="Media",
        entity_id=result.get("pathname"),
        actor=current_user,
        ip_address=client_ip,
        user_agent=user_agent,
        after_state={"filename": result.get("filename"), "size_bytes": result.get("size_bytes"), "url": result.get("url")},
    )

    return result


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_file(
    request: Request,
    body: DeleteUploadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticated file deletion endpoint.
    Deletes the blob from storage and logs the audit event.
    """
    success = await storage_service.delete_file(body.url)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete file from blob storage",
        )

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    await AuditService.log_event(
        db=db,
        action="FILE_DELETE",
        entity="Media",
        entity_id=body.url,
        actor=current_user,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return {"message": "File deleted successfully", "url": body.url}
