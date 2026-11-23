import os
import uuid
from typing import Dict, Any, Optional
import httpx
from fastapi import HTTPException, UploadFile, status
from app.core.config import settings

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class StorageService:
    def __init__(self):
        self.token = getattr(settings, "BLOB_READ_WRITE_TOKEN", None)
        if not self.token:
            self.token = os.environ.get("BLOB_READ_WRITE_TOKEN")

    def _get_headers(self, content_type: Optional[str] = None, access: str = "private") -> Dict[str, str]:
        if not self.token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="BLOB_READ_WRITE_TOKEN is not configured on the server",
            )
        headers = {
            "authorization": f"Bearer {self.token}",
            "x-api-version": "7",
        }
        if content_type:
            headers["content-type"] = content_type
            headers["x-content-type"] = content_type
            headers["x-add-random-suffix"] = "1"
            headers["x-vercel-blob-access"] = access
        return headers

    async def upload_file(self, file: UploadFile, folder: str = "uploads") -> Dict[str, Any]:
        """
        Validates and uploads a file to Vercel Blob Storage.
        Returns metadata including the access URL.
        """
        # Validate MIME type
        content_type = file.content_type or "application/octet-stream"
        if content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type '{content_type}'. Allowed types: JPEG, PNG, WEBP, GIF, PDF.",
            )

        # Read contents and validate size
        content = await file.read()
        file_size = len(content)
        if file_size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of 10MB ({file_size / (1024*1024):.2f}MB).",
            )

        ext = ALLOWED_MIME_TYPES[content_type]
        base_name = file.filename or "upload"
        filename = f"{uuid.uuid4().hex[:12]}_{base_name}{ext if not base_name.endswith(ext) else ''}"
        pathname = f"{folder}/{filename}".replace("//", "/")

        endpoint = f"https://blob.vercel-storage.com/{pathname}"

        # Attempt upload with private store header (fall back to public if public store)
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = self._get_headers(content_type=content_type, access="private")
            resp = await client.put(endpoint, content=content, headers=headers)
            
            if resp.status_code == 400 and "public access on a private store" in resp.text:
                headers = self._get_headers(content_type=content_type, access="private")
                resp = await client.put(endpoint, content=content, headers=headers)
            elif resp.status_code == 400 and "private access on a public store" in resp.text:
                headers = self._get_headers(content_type=content_type, access="public")
                resp = await client.put(endpoint, content=content, headers=headers)

            if resp.status_code not in (200, 201):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Blob storage provider error: {resp.status_code} {resp.text}",
                )
            result = resp.json()

        return {
            "url": result.get("url"),
            "download_url": result.get("downloadUrl"),
            "pathname": result.get("pathname"),
            "content_type": content_type,
            "size_bytes": file_size,
            "filename": file.filename,
        }

    async def delete_file(self, blob_url: str) -> bool:
        """
        Deletes a blob from Vercel Blob Storage by URL.
        """
        if not blob_url:
            return False

        headers = self._get_headers()
        endpoint = "https://blob.vercel-storage.com/delete"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, json={"urls": [blob_url]}, headers=headers)
            return resp.status_code == 200


storage_service = StorageService()
