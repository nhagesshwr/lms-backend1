from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Doubt, Lesson, Employee
from app.schemas import DoubtCreate, DoubtAnswerRequest, DoubtResponse
from app.dependencies import require_employee, require_manager
from datetime import datetime

router = APIRouter(prefix="/doubts", tags=["Course Doubts"])

@router.post("/lesson/{lesson_id}", response_model=DoubtResponse)
def ask_doubt(
    lesson_id: int,
    data: DoubtCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    doubt = Doubt(
        lesson_id=lesson_id,
        asked_by=current.id,
        question=data.question
    )
    db.add(doubt)
    db.commit()
    db.refresh(doubt)
    return doubt

@router.get("/lesson/{lesson_id}", response_model=list[dict])
def get_lesson_doubts(
    lesson_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee)
):
    doubts = db.query(Doubt).options(
        joinedload(Doubt.asker),
        joinedload(Doubt.answerer)
    ).filter(Doubt.lesson_id == lesson_id).order_by(Doubt.created_at.desc()).all()

    result = []
    for d in doubts:
        # Employees only see their own doubts unless answered (or they are manager)
        if current.role.value in ["hr_admin", "super_admin", "manager"] or d.asked_by == current.id or d.answer is not None:
            result.append({
                "id": d.id,
                "lesson_id": d.lesson_id,
                "asked_by": d.asked_by,
                "asker_name": d.asker.name if d.asker else "Unknown",
                "question": d.question,
                "answer": d.answer,
                "answered_by_name": d.answerer.name if d.answerer else None,
                "created_at": d.created_at.isoformat(),
                "answered_at": d.answered_at.isoformat() if d.answered_at else None
            })
    return result

@router.post("/{doubt_id}/answer", response_model=DoubtResponse)
def answer_doubt(
    doubt_id: int,
    data: DoubtAnswerRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_manager)
):
    doubt = db.query(Doubt).filter(Doubt.id == doubt_id).first()
    if not doubt:
        raise HTTPException(status_code=404, detail="Doubt not found")

    doubt.answer = data.answer
    doubt.answered_by = current.id
    doubt.answered_at = datetime.utcnow()
    db.commit()
    db.refresh(doubt)
    return doubt
