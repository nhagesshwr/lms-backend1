from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Employee, RoleEnum
from app.auth import decode_token

security = HTTPBearer()


def get_current_employee(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Employee:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    employee = db.query(Employee).filter(
        Employee.email == payload.get("sub")
    ).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your administrator.",
        )

    # Pending users authenticated via token still can't access the app
    if employee.is_pending:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is awaiting admin approval.",
        )

    return employee


def require_super_admin(current: Employee = Depends(get_current_employee)) -> Employee:
    if current.role != RoleEnum.super_admin:
        raise HTTPException(status_code=403, detail="Super admin access required")
    return current


def require_hr_admin(current: Employee = Depends(get_current_employee)) -> Employee:
    if current.role not in [RoleEnum.hr_admin, RoleEnum.super_admin]:
        raise HTTPException(status_code=403, detail="HR admin access required")
    return current


def require_manager(current: Employee = Depends(get_current_employee)) -> Employee:
    if current.role not in [RoleEnum.manager, RoleEnum.hr_admin, RoleEnum.super_admin]:
        raise HTTPException(status_code=403, detail="Manager access required")
    return current


def require_employee(current: Employee = Depends(get_current_employee)) -> Employee:
    return current


def require_permission(resource: str, action: str):
    """
    Dependency factory for dynamic, DB-driven permission checks.
    Super admin always passes. Other roles are checked against the
    role_permissions table (seeded with defaults on first use).

    Usage:
        @router.post("/something")
        def create_something(current = Depends(require_permission("courses", "create"))):
            ...
    """
    def dependency(
        db: Session = Depends(get_db),
        current: Employee = Depends(get_current_employee),
    ) -> Employee:
        if current.role == RoleEnum.super_admin:
            return current

        from app.models import RolePermission
        perm = db.query(RolePermission).filter(
            RolePermission.role == current.role,
            RolePermission.resource == resource,
        ).first()

        if not perm:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: no permissions configured for this role.",
            )

        action_map = {
            "view":   perm.can_view,
            "create": perm.can_create,
            "update": perm.can_update,
            "delete": perm.can_delete,
        }
        allowed = action_map.get(action, False)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"You do not have {action} permission for {resource}.",
            )
        return current
    return dependency
