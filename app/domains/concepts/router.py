from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.domains.concepts.service import ConceptService
from app.domains.concepts.schemas import (
    ConceptCreate, ConceptUpdate, ConceptResponse, ConceptSummary
)
from typing import List, Optional
import io

router = APIRouter(prefix="/api/concepts", tags=["concepts"])


@router.post("", response_model=ConceptResponse, status_code=201)
def create_concept(
    data: ConceptCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ConceptService.create(db, user.id, data)


@router.get("/due", response_model=List[ConceptSummary])
def get_due_concepts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ConceptService.get_due(db, user.id)


@router.get("/course/{course_id}", response_model=List[ConceptSummary])
def list_concepts(
    course_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ConceptService.get_all(db, user.id, course_id)


@router.get("/{concept_id}", response_model=ConceptResponse)
def get_concept(
    concept_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ConceptService.get_one(db, user.id, concept_id)


@router.put("/{concept_id}", response_model=ConceptResponse)
def update_concept(
    concept_id: str,
    data: ConceptUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ConceptService.update(db, user.id, concept_id, data)


@router.delete("/{concept_id}", status_code=204)
def delete_concept(
    concept_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ConceptService.delete(db, user.id, concept_id)

@router.post("/extract")
async def extract_from_text(
    course_id: str = Form(...),
    text: str = Form(default=""),
    file: Optional[UploadFile] = File(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.ai_service import extract_concepts_from_text

    from app.models.course import Course
    course = db.query(Course).filter(
        Course.id == course_id,
        Course.user_id == user.id,
    ).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    content = ""
    if file and file.filename:
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        raw_bytes = await file.read()
        if len(raw_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum 10MB.")
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw_bytes))
            pages = []
            for page in reader.pages[:20]:
                pages.append(page.extract_text() or "")
            content = "\n".join(pages)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read PDF: {str(e)}")
    elif text.strip():
        content = text.strip()
    else:
        raise HTTPException(status_code=400, detail="Provide either text or a PDF file")

    if len(content.strip()) < 50:
        raise HTTPException(status_code=400, detail="Not enough text to extract concepts from")

    # FIX: unpack the tuple
    result = extract_concepts_from_text(content, course.title)
    if not result:
        raise HTTPException(
            status_code=503,
            detail="AI extraction failed. Paste your text and try again."
        )
    concepts, was_truncated = result

    return {
        "course_id": course_id,
        "extracted": concepts,
        "count": len(concepts),
        "was_truncated": was_truncated,
    }
