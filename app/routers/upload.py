"""Authenticated user document upload, download, review, and deletion."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Response
from pydantic import BaseModel, ConfigDict, Field
from datetime import date
from urllib.parse import quote

from app.services import upload_service
from app.services import document_review_service
from app.services.document.extractors import SUPPORTED_EXTENSIONS, extension
from app.core.security import verify_token
from config import MAX_UPLOAD_MB

router = APIRouter(prefix="/api", tags=["upload"])


class ReviewedAmount(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: int = Field(ge=0, strict=True)
    page: int = Field(ge=1, strict=True)
    note: str = Field(default='', max_length=300)


class ReviewedDate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: date
    page: int = Field(ge=1, strict=True)
    note: str = Field(default='', max_length=300)


class DocumentReviewUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fields: dict[str, ReviewedAmount] = Field(max_length=40)
    dates: list[ReviewedDate] = Field(default_factory=list, max_length=20)


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(verify_token),
):
    if not file.filename or extension(file.filename) not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="PDF, DOCX, HWPX, PPTX, HTML 파일만 업로드 가능합니다.")

    file_bytes = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)

    if len(file_bytes) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기가 제한을 초과했습니다. (최대 {MAX_UPLOAD_MB}MB)",
        )

    return await upload_service.process_upload(
        file_bytes=file_bytes,
        filename=file.filename,
        user_id=user["id"],
        uploader_email=user["email"],
    )


@router.get("/documents")
async def list_documents(user: dict = Depends(verify_token)):
    return await upload_service.list_documents(user["id"])


@router.get('/documents/{filename:path}/file')
async def original_file(filename: str, user: dict = Depends(verify_token)):
    row = await document_review_service.file_row(user['id'], filename)
    is_pdf = extension(filename) == '.pdf'
    disposition = 'inline' if is_pdf else 'attachment'
    return Response(bytes(row['content']), media_type='application/pdf' if is_pdf else 'application/octet-stream', headers={
        'Content-Disposition': f"{disposition}; filename*=UTF-8''{quote(filename, safe='')}",
        'Cache-Control': 'private, no-store',
        'X-Content-Type-Options': 'nosniff',
    })


@router.get('/documents/{filename:path}/review')
async def get_review(filename: str, user: dict = Depends(verify_token)):
    return await document_review_service.review(user['id'], filename)


@router.put('/documents/{filename:path}/review')
async def save_review(filename: str, payload: DocumentReviewUpdate,
                      user: dict = Depends(verify_token)):
    return await document_review_service.save_review(
        user['id'], filename, {key: value.model_dump() for key, value in payload.fields.items()},
        [item.model_dump(mode='json') for item in payload.dates])


@router.delete("/documents/{filename:path}")
async def delete_document(filename: str, user: dict = Depends(verify_token)):
    return await upload_service.delete_document(filename, user["id"])
