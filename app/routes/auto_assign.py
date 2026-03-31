from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import AutoAssignRule, Course, Department, Employee, Enrollment
from app.dependencies import require_hr_admin

router = APIRouter(prefix="/auto-assign", tags=["Auto-Assign"])


class RuleCreate(BaseModel):
    course_id: int
    department_id: Optional[int] = None  # None = all departments


def _rule_dict(r: AutoAssignRule) -> dict:
    return {
        "id": r.id,
        "course_id": r.course_id,
        "course_title": r.course.title if r.course else "—",
        "course_thumbnail": r.course.thumbnail_url if r.course else None,
        "department_id": r.department_id,
        "department_name": r.department.name if r.department else "All Departments",
        "is_active": r.is_active,
        "created_at": r.created_at,
    }


@router.get("/rules")
def list_rules(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin),
):
    rules = (
        db.query(AutoAssignRule)
        .options(
            joinedload(AutoAssignRule.course),
            joinedload(AutoAssignRule.department),
        )
        .order_by(AutoAssignRule.created_at.desc())
        .all()
    )
    return [_rule_dict(r) for r in rules]


@router.post("/rules", status_code=201)
def create_rule(
    data: RuleCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin),
):
    course = db.query(Course).filter(Course.id == data.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    if data.department_id is not None:
        dept = db.query(Department).filter(Department.id == data.department_id).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")

    existing = db.query(AutoAssignRule).filter(
        AutoAssignRule.course_id == data.course_id,
        AutoAssignRule.department_id == data.department_id,
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A rule already exists for this course and department combination",
        )

    rule = AutoAssignRule(
        course_id=data.course_id,
        department_id=data.department_id,
        created_by=current.id,
        is_active=True,
    )
    db.add(rule)
    db.commit()

    # Reload with relationships
    rule = (
        db.query(AutoAssignRule)
        .options(
            joinedload(AutoAssignRule.course),
            joinedload(AutoAssignRule.department),
        )
        .filter(AutoAssignRule.id == rule.id)
        .first()
    )
    return _rule_dict(rule)


@router.patch("/rules/{rule_id}/toggle")
def toggle_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin),
):
    rule = db.query(AutoAssignRule).filter(AutoAssignRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.is_active = not rule.is_active
    db.commit()
    return {"id": rule.id, "is_active": rule.is_active}


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin),
):
    rule = db.query(AutoAssignRule).filter(AutoAssignRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"message": "Rule deleted"}
