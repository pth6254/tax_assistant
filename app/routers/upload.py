"""
routers/upload.py — 문서 업로드·목록·삭제 엔드포인트
POST   /api/upload
GET    /api/documents
DELETE /api/documents/{filename}
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.services import upload_service
from app.utils.jwt import verify_token
from config import MAX_UPLOAD_MB

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(verify_token),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    file_bytes = await file.read()

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


@router.delete("/documents/{filename:path}")
async def delete_document(filename: str, user: dict = Depends(verify_token)):
    return await upload_service.delete_document(filename, user["id"])
