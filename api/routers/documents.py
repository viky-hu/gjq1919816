"""
Documents router: upload, list, delete, and trigger reprocessing.
"""

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger("documents")

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import decode_token, get_current_user, get_db, get_rag_manager, get_user_rag, security
from ..models import Document, User
from ..schemas import DocumentListResponse, DocumentResponse

FEDERATION_INTERNAL_TOKEN = os.getenv("FEDERATION_INTERNAL_TOKEN", "")


async def get_current_user_or_federation(
    authorization: str = Header(None),
    x_federation_token: str = Header(None, alias="X-Federation-Token"),
    db: Session = Depends(get_db),
) -> User:
    """Accept either JWT Bearer token or X-Federation-Token for internal sync."""
    # Try JWT first
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        payload = decode_token(token)
        if payload is not None:
            user = db.query(User).filter(User.id == int(payload["sub"])).first()
            if user is not None:
                return user

    # Fall back to federation token
    if FEDERATION_INTERNAL_TOKEN and x_federation_token and secrets.compare_digest(x_federation_token, FEDERATION_INTERNAL_TOKEN):
        user = db.query(User).first()
        if user is not None:
            return user
        raise HTTPException(status_code=404, detail="No user found for federation sync")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

UPLOAD_DIR = Path("./uploads")
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx", ".md", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".wav", ".mp3"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}
MULTIMODAL_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff"}

router = APIRouter(prefix="/api/documents", tags=["documents"])


class InsertRequest(BaseModel):
    content: str
    file_name: str = ""
    account: str = ""


class InsertFileRequest(BaseModel):
    """Request body for multimodal file content insertion."""
    file_path: str
    file_name: str = ""


class InsertBase64Request(BaseModel):
    """Request body for base64-encoded file insertion."""
    content_base64: str
    file_name: str
    mime_type: str = "application/octet-stream"


@router.post("/insert")
async def insert_document_text(
    body: InsertRequest,
    current_user: User = Depends(get_current_user_or_federation),
    db: Session = Depends(get_db),
):
    """Insert text content directly into LightRAG knowledge graph."""
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is empty")
    if len(content) < 50:
        raise HTTPException(status_code=400, detail="Content too short (min 50 chars)")

    # Resolve target user: prefer explicit account, fallback to auth user
    target_user = current_user
    if body.account:
        user = db.query(User).filter(User.username == body.account).first()
        if user:
            target_user = user

    try:
        rag = await get_user_rag(target_user.id)
        file_names = [body.file_name] if body.file_name else None
        await rag.insert_documents([content], file_names=file_names)

        # Persist document in SQLite so startup can reload after restart
        doc = Document(
            filename=body.file_name or "inline",
            file_path="",
            size_bytes=len(content.encode("utf-8")),
            char_count=len(content),
            content=content,
            status="ready",
            user_id=target_user.id,
        )
        db.add(doc)
        db.commit()

        return {"status": "ok", "chars": len(content), "user_id": target_user.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/insert-file")
async def insert_document_file(
    body: InsertFileRequest,
    current_user: User = Depends(get_current_user_or_federation),
    db: Session = Depends(get_db),
):
    """Insert a file (text, PDF, or image) into the knowledge graph with multimodal processing.

    Uses MiARAG.insert_files() which routes through ImageProcessor/PDFProcessor.
    """
    file_path = body.file_path.strip()
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path is required")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    ext = Path(file_path).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    try:
        rag = await get_user_rag(current_user.id)
        await rag.insert_files([file_path])

        # Persist document in SQLite so macro platform can count it
        file_size = os.path.getsize(file_path)
        doc = Document(
            filename=body.file_name or Path(file_path).name,
            file_path=file_path,
            size_bytes=file_size,
            char_count=0,
            content=None,
            status="ready",
            user_id=current_user.id,
        )
        db.add(doc)
        db.commit()

        return {"status": "ok", "file": file_path, "type": ext}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/insert-base64")
async def insert_document_base64(
    body: InsertBase64Request,
    current_user: User = Depends(get_current_user_or_federation),
    db: Session = Depends(get_db),
):
    """Insert a base64-encoded file (PDF, image, etc.) into the knowledge graph.

    Decodes base64 content, saves to a temp file, then processes via multimodal pipeline.
    """
    import base64

    if not body.content_base64:
        raise HTTPException(status_code=400, detail="content_base64 is required")
    if not body.file_name.strip():
        raise HTTPException(status_code=400, detail="file_name is required")

    ext = Path(body.file_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Decode and save to temp file
    try:
        file_bytes = base64.b64decode(body.content_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 content")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{current_user.id}_{body.file_name}"
    file_path = UPLOAD_DIR / safe_name
    file_path.write_bytes(file_bytes)

    # Process via multimodal pipeline
    try:
        rag = await get_user_rag(current_user.id)
        logger.info(f"Processing base64 file: {body.file_name} ({len(file_bytes)} bytes)")
        await rag.insert_files([str(file_path)])
        logger.info(f"Base64 file processed: {body.file_name}")

        # Persist document in SQLite so macro platform can count it
        doc = Document(
            filename=body.file_name,
            file_path=str(file_path),
            size_bytes=len(file_bytes),
            char_count=0,
            content=None,
            status="ready",
            user_id=current_user.id,
        )
        db.add(doc)
        db.commit()

        return {"status": "ok", "file": body.file_name, "type": ext}
    except Exception as e:
        logger.error(f"Base64 file embedding failed: {body.file_name}: {e}")
        raise HTTPException(status_code=500, detail=f"文献嵌入失败: {e}")


TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log"}

def _read_text_content(file_path: str) -> tuple[int, str | None]:
    """Try to read text content from file. Returns (char_count, content_or_none).
    Skips binary files (PDF, images, audio, docx)."""
    ext = Path(file_path).suffix.lower()
    if ext not in TEXT_EXTENSIONS:
        return 0, None
    encodings = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]
    for enc in encodings:
        try:
            content = Path(file_path).read_text(encoding=enc)
            return len(content), content
        except (UnicodeDecodeError, UnicodeError):
            continue
    return 0, None


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{current_user.id}_{file.filename}"
    file_path = UPLOAD_DIR / safe_name

    content_bytes = await file.read()
    file_path.write_bytes(content_bytes)

    char_count, content = _read_text_content(str(file_path))

    doc = Document(
        user_id=current_user.id,
        filename=file.filename or "unknown",
        file_path=str(file_path),
        size_bytes=len(content_bytes),
        char_count=char_count,
        content=content,
        status="ready" if content else "processing",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Insert into knowledge graph with multimodal support
    try:
        rag = await get_user_rag(current_user.id)
        if ext in MULTIMODAL_EXTENSIONS:
            logger.info(f"Processing multimodal file: {file.filename} (ext={ext})")
            await rag.insert_files([str(file_path)])
            logger.info(f"Multimodal file processed: {file.filename}")
        elif content:
            logger.info(f"Inserting text document: {file.filename} ({len(content)} chars)")
            await rag.insert_documents([content])
            logger.info(f"Text document inserted: {file.filename}")
        else:
            logger.warning(f"No content extracted from {file.filename}, skipping embedding")
        doc.status = "ready"
        db.commit()
    except Exception as e:
        logger.error(f"Embedding failed for {file.filename}: {e}")
        doc.status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail=f"文献嵌入失败: {e}")

    return DocumentResponse.model_validate(doc)


@router.get("/", response_model=DocumentListResponse)
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    docs = db.query(Document).filter(Document.user_id == current_user.id).order_by(Document.uploaded_at.desc()).all()
    return DocumentListResponse(
        total=len(docs),
        documents=[DocumentResponse.model_validate(d) for d in docs],
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    db.delete(doc)
    db.commit()
    return {"detail": "Document deleted"}
