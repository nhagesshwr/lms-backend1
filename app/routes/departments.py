from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Department, Employee
from app.schemas import DepartmentCreate, DepartmentUpdate, DepartmentResponse, DepartmentWithEmployees
from app.dependencies import require_super_admin, require_hr_admin, require_manager

router = APIRouter(prefix="/departments", tags=["Departments"])

# HR admin and above can create department
@router.post("/", response_model=DepartmentResponse)
@router.post("", response_model=DepartmentResponse)
def create_department(
    dept: DepartmentCreate,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    existing = db.query(Department).filter(Department.name == dept.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Department already exists")
    new_dept = Department(name=dept.name)
    db.add(new_dept)
    db.commit()
    db.refresh(new_dept)
    return new_dept

# Manager and above can view all departments
@router.get("/", response_model=list[DepartmentResponse])
@router.get("", response_model=list[DepartmentResponse])
def get_departments(
    db: Session = Depends(get_db),
    current=Depends(require_manager)
):
    return db.query(Department).all()

# Get department with all its employees
@router.get("/{dept_id}", response_model=DepartmentWithEmployees)
def get_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_manager)
):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept

# HR admin and above can update department
@router.put("/{dept_id}", response_model=DepartmentResponse)
def update_department(
    dept_id: int,
    dept_update: DepartmentUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    if dept_update.name:
        dept.name = dept_update.name
    db.commit()
    db.refresh(dept)
    return dept

# HR admin and above can delete department
@router.delete("/{dept_id}")
def delete_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db.delete(dept)
    db.commit()
    return {"message": f"Department '{dept.name}' deleted"}