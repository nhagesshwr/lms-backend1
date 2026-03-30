from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models import (
    Employee, RoleEnum, Message, Enrollment, Certificate,
    LessonProgress, PasswordResetToken, LiveClassEnrollment, LiveClassAudience
)
from app.schemas import EmployeeCreate, EmployeeUpdate, EmployeeResponse
from app.auth import hash_password
from app.dependencies import require_super_admin, require_hr_admin, require_manager, get_current_employee

router = APIRouter(prefix="/employees", tags=["Employees"])


# ── HR admin and above can add employee ───────────────────────────────────────
@router.post("/", response_model=EmployeeResponse)
@router.post("", response_model=EmployeeResponse)
def create_employee(
    employee: EmployeeCreate,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin),
):
    active_existing = db.query(Employee).filter(
        Employee.email == employee.email, Employee.is_active == True
    ).first()
    if active_existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    # Reactivate soft-deleted accounts
    inactive_existing = db.query(Employee).filter(
        Employee.email == employee.email, Employee.is_active == False
    ).first()
    if inactive_existing:
        inactive_existing.name = employee.name
        inactive_existing.hashed_password = hash_password(employee.password)
        inactive_existing.role = employee.role
        inactive_existing.department_id = employee.department_id
        inactive_existing.is_active = True
        inactive_existing.is_pending = False
        db.commit()
        db.refresh(inactive_existing)
        return inactive_existing

    new_emp = Employee(
        name=employee.name,
        email=employee.email,
        hashed_password=hash_password(employee.password),
        role=employee.role,
        department_id=employee.department_id,
    )
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)
    return new_emp


# ── Admin user list — manager+ required ───────────────────────────────────────
@router.get("/admins", response_model=list[EmployeeResponse])
def get_admin_users(
    db: Session = Depends(get_db),
    current=Depends(require_manager),   # manager, hr_admin, super_admin only
):
    """Return all super_admin and hr_admin users. Requires manager or above."""
    return db.query(Employee).filter(
        Employee.role.in_([RoleEnum.super_admin, RoleEnum.hr_admin]),
        Employee.is_active == True,
    ).all()


# ── List all active employees (manager+, paginated) ───────────────────────────
@router.get("/", response_model=list[EmployeeResponse])
@router.get("", response_model=list[EmployeeResponse])
def get_all_employees(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current=Depends(require_manager),
):
    return (
        db.query(Employee)
        .filter(Employee.is_active == True)
        .offset(skip)
        .limit(limit)
        .all()
    )


# ── Get employees by department ───────────────────────────────────────────────
@router.get("/department/{dept_id}", response_model=list[EmployeeResponse])
def get_employees_by_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_manager),
):
    employees = db.query(Employee).filter(
        Employee.department_id == dept_id,
        Employee.is_active == True,
    ).all()
    if not employees:
        raise HTTPException(status_code=404, detail="No employees found in this department")
    return employees


# ── Get single employee ───────────────────────────────────────────────────────
@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_manager),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


# ── Super admin updates employee ──────────────────────────────────────────────
@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    emp_update: EmployeeUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Prevent self-demotion from super_admin
    if emp.id == current.id and emp_update.role and emp_update.role != RoleEnum.super_admin:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    if emp_update.name:
        emp.name = emp_update.name
    if emp_update.email:
        existing = db.query(Employee).filter(
            Employee.email == emp_update.email, Employee.id != employee_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use by another user")
        emp.email = emp_update.email
    if emp_update.role:
        emp.role = emp_update.role
        emp.is_pending = False
    if emp_update.department_id is not None:
        emp.department_id = emp_update.department_id
    if emp_update.is_active is not None:
        emp.is_active = emp_update.is_active
    db.commit()
    db.refresh(emp)
    return emp


# ── HR admin or above can delete an employee ──────────────────────────────────
@router.delete("/{employee_id}")
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if emp.id == current.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    # Prevent deleting a super_admin unless caller is also super_admin
    if emp.role == RoleEnum.super_admin and current.role != RoleEnum.super_admin:
        raise HTTPException(status_code=403, detail="Only super admins can delete other super admins")

    # Cascade-delete related data
    db.query(Message).filter(
        or_(Message.sender_id == employee_id, Message.receiver_id == employee_id)
    ).delete(synchronize_session=False)

    enroll_ids = [
        e.id for e in db.query(Enrollment).filter(Enrollment.employee_id == employee_id).all()
    ]
    if enroll_ids:
        db.query(LessonProgress).filter(
            LessonProgress.enrollment_id.in_(enroll_ids)
        ).delete(synchronize_session=False)

    db.query(Enrollment).filter(Enrollment.employee_id == employee_id).delete(synchronize_session=False)
    db.query(Certificate).filter(Certificate.employee_id == employee_id).delete(synchronize_session=False)
    db.query(PasswordResetToken).filter(PasswordResetToken.employee_id == employee_id).delete(synchronize_session=False)
    db.query(LiveClassEnrollment).filter(LiveClassEnrollment.employee_id == employee_id).delete(synchronize_session=False)
    db.query(LiveClassAudience).filter(LiveClassAudience.employee_id == employee_id).delete(synchronize_session=False)

    name = emp.name
    db.delete(emp)
    db.commit()
    return {"message": f"Employee '{name}' permanently deleted"}
