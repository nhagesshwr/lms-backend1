from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models import LiveClass, LiveClassEnrollment, LiveClassAudience, Employee, Enrollment, RoleEnum
from app.schemas import LiveClassCreate, LiveClassUpdate, LiveClassResponse
from app.dependencies import get_current_employee

router = APIRouter(prefix="/live-classes", tags=["Live Classes"])

# Roles allowed to create / manage live classes
MANAGER_ROLES = {RoleEnum.super_admin, RoleEnum.hr_admin, RoleEnum.manager}


def _check_manager(current_user: Employee):
    if current_user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized to manage live classes")

def _check_creator_or_admin(current_user: Employee, db_class: LiveClass):
    _check_manager(current_user)
    if current_user.role not in [RoleEnum.super_admin, RoleEnum.hr_admin] and db_class.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only the creator can modify this live class")

def _apply_audience(db: Session, db_class: LiveClass, audience_type: str,
                    course_id: Optional[int], employee_ids: Optional[List[int]]):
    """Auto-enroll employees based on audience type right after creation."""
    # Clear existing audience entries
    db.query(LiveClassAudience).filter(LiveClassAudience.live_class_id == db_class.id).delete()

    targets: List[int] = []

    if audience_type == "all":
        targets = [emp.id for emp in db.query(Employee).filter(Employee.is_active == True).all()]
    elif audience_type == "course" and course_id:
        enrollments = db.query(Enrollment).filter(Enrollment.course_id == course_id).all()
        targets = [e.employee_id for e in enrollments]
    elif audience_type == "selected" and employee_ids:
        targets = employee_ids

    # Upsert audience rows
    existing = {a.employee_id for a in db.query(LiveClassAudience).filter(
        LiveClassAudience.live_class_id == db_class.id).all()}
    for emp_id in targets:
        if emp_id not in existing:
            db.add(LiveClassAudience(live_class_id=db_class.id, employee_id=emp_id))

    db_class.enrolled = len(targets)
    db.commit()


# ─── Create ───────────────────────────────────────────────────────────────────
@router.post("/", response_model=LiveClassResponse)
@router.post("", response_model=LiveClassResponse)
def create_live_class(
    data: LiveClassCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_employee)
):
    _check_manager(current_user)

    payload = data.model_dump(exclude={"employee_ids"})
    db_class = LiveClass(**payload, created_by=current_user.id)
    db.add(db_class)
    db.flush()   # get id before committing

    _apply_audience(db, db_class, data.audience_type, data.course_id, data.employee_ids)
    db.refresh(db_class)
    return db_class


# ─── List all ─────────────────────────────────────────────────────────────────
@router.get("/", response_model=List[LiveClassResponse])
@router.get("", response_model=List[LiveClassResponse])
def get_live_classes(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_employee)
):
    return db.query(LiveClass).order_by(LiveClass.created_at.desc()).all()


# ─── My classes (audience member) ─────────────────────────────────────────────
@router.get("/my", response_model=List[LiveClassResponse])
def get_my_live_classes(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_employee)
):
    audience_rows = db.query(LiveClassAudience).filter(
        LiveClassAudience.employee_id == current_user.id
    ).all()
    class_ids = [a.live_class_id for a in audience_rows]
    return db.query(LiveClass).filter(LiveClass.id.in_(class_ids))\
        .order_by(LiveClass.created_at.desc()).all()


# ─── Get single ───────────────────────────────────────────────────────────────
@router.get("/{class_id}", response_model=LiveClassResponse)
def get_live_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_employee)
):
    db_class = db.query(LiveClass).filter(LiveClass.id == class_id).first()
    if not db_class:
        raise HTTPException(status_code=404, detail="Live class not found")
    return db_class


# ─── Update ───────────────────────────────────────────────────────────────────
@router.put("/{class_id}", response_model=LiveClassResponse)
def update_live_class(
    class_id: int,
    data: LiveClassUpdate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_employee)
):
    db_class = db.query(LiveClass).filter(LiveClass.id == class_id).first()
    if not db_class:
        raise HTTPException(status_code=404, detail="Live class not found")
    _check_creator_or_admin(current_user, db_class)

    update_fields = data.model_dump(exclude_unset=True, exclude={"employee_ids"})
    for k, v in update_fields.items():
        setattr(db_class, k, v)
    db.flush()

    # Re-apply audience if relevant fields changed
    if data.audience_type or data.employee_ids is not None or data.course_id is not None:
        _apply_audience(
            db, db_class,
            data.audience_type or db_class.audience_type,
            data.course_id if data.course_id is not None else db_class.course_id,
            data.employee_ids
        )

    db.commit()
    db.refresh(db_class)
    return db_class


# ─── Delete ───────────────────────────────────────────────────────────────────
@router.delete("/{class_id}")
def delete_live_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_employee)
):
    db_class = db.query(LiveClass).filter(LiveClass.id == class_id).first()
    if not db_class:
        raise HTTPException(status_code=404, detail="Live class not found")
    _check_creator_or_admin(current_user, db_class)
    db.delete(db_class)
    db.commit()
    return {"message": "Deleted"}


# ─── Get audience list ────────────────────────────────────────────────────────
@router.get("/{class_id}/audience")
def get_audience(
    class_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_employee)
):
    _check_manager(current_user)
    rows = db.query(LiveClassAudience).filter(LiveClassAudience.live_class_id == class_id).all()
    return [{"employee_id": r.employee_id} for r in rows]
