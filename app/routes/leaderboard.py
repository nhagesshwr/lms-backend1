from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Enrollment, Employee, Department
from app.dependencies import require_employee

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])


def _build_leaderboard(db: Session) -> list:
    results = (
        db.query(
            Employee.id,
            Employee.name,
            Department.name.label("department"),
            func.sum(Enrollment.progress_pct).label("total_progress"),
            func.count(Enrollment.id).label("courses"),
        )
        .join(Enrollment, Employee.id == Enrollment.employee_id)
        .outerjoin(Department, Employee.department_id == Department.id)
        .filter(Employee.is_active == True)
        .group_by(Employee.id, Department.name)
        .order_by(func.sum(Enrollment.progress_pct).desc())
        .limit(50)
        .all()
    )
    return [
        {
            "rank": i + 1,
            "id": r.id,
            "name": r.name,
            "department": r.department or "General",
            "xp": int((r.total_progress or 0) * 10),
            "streak": 0,
            "courses": r.courses,
            "avatar": r.name[:2].upper() if r.name else "??",
            "change": 0,
        }
        for i, r in enumerate(results)
    ]


@router.get("/")
@router.get("")
def get_leaderboard(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee),   # authentication required
):
    return _build_leaderboard(db)


@router.get("/me")
def get_my_rank(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee),
):
    all_leaders = _build_leaderboard(db)
    for leader in all_leaders:
        if leader["id"] == current.id:
            return leader

    return {
        "rank": len(all_leaders) + 1,
        "name": current.name,
        "department": current.department.name if current.department else "General",
        "xp": 0,
        "streak": 0,
        "courses": 0,
        "avatar": current.name[:2].upper() if current.name else "??",
        "change": 0,
    }
