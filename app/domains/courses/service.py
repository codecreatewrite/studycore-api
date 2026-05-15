from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.course import Course
from app.models.concept import Concept
from app.domains.courses.schemas import CourseCreate, CourseUpdate
from fastapi import HTTPException
from typing import List


class CourseService:

    @staticmethod
    def create(db: Session, user_id: str, data: CourseCreate) -> Course:
        course = Course(
            user_id=user_id,
            title=data.title.strip(),
            description=data.description,
            exam_date=data.exam_date,
        )
        db.add(course)
        db.commit()
        db.refresh(course)
        return course

    @staticmethod
    def get_all(db: Session, user_id: str) -> List[dict]:
        rows = (
            db.query(Course, func.count(Concept.id).label("concept_count"))
            .outerjoin(Concept, Concept.course_id == Course.id)
            .filter(Course.user_id == user_id)
            .group_by(Course.id)
            .order_by(Course.created_at.desc())
            .all()
        )
        result = []
        for course, count in rows:
            result.append({
                "id": course.id,
                "title": course.title,
                "description": course.description,
                "exam_date": course.exam_date,
                "concept_count": count,
                "created_at": course.created_at,
            })
        return result

    @staticmethod
    def get_one(db: Session, user_id: str, course_id: str) -> Course:
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.user_id == user_id,
        ).first()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        return course

    @staticmethod
    def update(db: Session, user_id: str, course_id: str, data: CourseUpdate) -> Course:
        course = CourseService.get_one(db, user_id, course_id)
        if data.title is not None:
            course.title = data.title.strip()
        if data.description is not None:
            course.description = data.description
        if data.exam_date is not None:
            course.exam_date = data.exam_date
        db.commit()
        db.refresh(course)
        return course

    @staticmethod
    def delete(db: Session, user_id: str, course_id: str) -> None:
        course = CourseService.get_one(db, user_id, course_id)
        db.delete(course)
        db.commit()
