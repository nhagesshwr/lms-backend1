from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Employee
from app.schemas import EmployeeCreate, EmployeeResponse
from app.auth import hash_password
from app.dependencies import require_super_admin, require_manager  # ← import guards

router = APIRouter(prefix="/employees", tags=["Employees"])

# Only super admin can add employee
@router.post("/", response_model=EmployeeResponse)
def create_employee(
    employee: EmployeeCreate,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)  # ← super admin only
):
    existing = db.query(Employee).filter(Employee.email == employee.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    new_emp = Employee(
        name=employee.name,
        email=employee.email,
        hashed_password=hash_password(employee.password),
        role=employee.role,
        department_id=employee.department_id
    )
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)
    return new_emp

# Manager and above can view all employees
@router.get("/", response_model=list[EmployeeResponse])
def get_employees(
    db: Session = Depends(get_db),
    current=Depends(require_manager)  # ← manager and above
):
    return db.query(Employee).all()

# Super admin can deactivate employee
@router.delete("/{employee_id}")
def deactivate_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)  # ← super admin only
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.is_active = False
    db.commit()
    return {"message": "Employee deactivated"}
