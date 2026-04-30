"""
routers/upload.py — PDF 업로드 엔드포인트
POST /api/upload
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.services import upload_service
from app.utils.jwt import verify_token

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(verify_token),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    file_bytes = await file.read()
    return await upload_service.process_upload(
        file_bytes=file_bytes,
        filename=file.filename,
        user_id=user["id"],
        uploader_email=user["email"],
    )
