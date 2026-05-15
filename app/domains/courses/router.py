from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.domains.courses.service import CourseService
from app.domains.courses.schemas import CourseCreate, CourseUpdate, CourseResponse
from typing import List

router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.post("", response_model=CourseResponse, status_code=201)
def create_course(
    data: CourseCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CourseService.create(db, user.id, data)


@router.get("", response_model=List[dict])
def list_courses(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CourseService.get_all(db, user.id)


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CourseService.get_one(db, user.id, course_id)


@router.put("/{course_id}", response_model=CourseResponse)
def update_course(
    course_id: str,
    data: CourseUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CourseService.update(db, user.id, course_id, data)


@router.delete("/{course_id}", status_code=204)
def delete_course(
    course_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    CourseService.delete(db, user.id, course_id)
