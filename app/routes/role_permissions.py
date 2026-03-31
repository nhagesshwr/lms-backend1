"""
Role Permission Management
--------------------------
Super admin can configure what each role (hr_admin, manager, employee) can do
per resource. Super admin itself always has full access and is never stored here.

Resources: users, courses, content, departments, enrollments,
           live_classes, assignments, certificates, reports, auto_assign
Actions:   can_view, can_create, can_update, can_delete
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import RolePermission, RoleEnum, Employee
from app.dependencies import require_super_admin, get_current_employee

router = APIRouter(prefix="/role-permissions", tags=["Role Permissions"])

# ─── Default permission matrix ────────────────────────────────────────────────
# (role, resource) → (view, create, update, delete)
DEFAULTS: dict[tuple, tuple] = {
    # ── HR Admin ──────────────────────────────────────────────────────────────
    ("hr_admin", "users"):        (True,  True,  True,  True ),
    ("hr_admin", "courses"):      (True,  True,  True,  True ),
    ("hr_admin", "content"):      (True,  True,  True,  True ),
    ("hr_admin", "departments"):  (True,  True,  True,  True ),
    ("hr_admin", "enrollments"):  (True,  True,  True,  True ),
    ("hr_admin", "live_classes"): (True,  True,  True,  True ),
    ("hr_admin", "assignments"):  (True,  True,  True,  True ),
    ("hr_admin", "certificates"): (True,  True,  True,  True ),
    ("hr_admin", "reports"):      (True,  False, False, False),
    ("hr_admin", "auto_assign"):  (True,  True,  True,  True ),
    # ── Manager ───────────────────────────────────────────────────────────────
    ("manager", "users"):        (True,  False, False, False),
    ("manager", "courses"):      (True,  False, False, False),
    ("manager", "content"):      (True,  False, False, False),
    ("manager", "departments"):  (True,  False, False, False),
    ("manager", "enrollments"):  (True,  True,  False, False),
    ("manager", "live_classes"): (True,  False, False, False),
    ("manager", "assignments"):  (True,  False, False, False),
    ("manager", "certificates"): (True,  False, False, False),
    ("manager", "reports"):      (True,  False, False, False),
    ("manager", "auto_assign"):  (False, False, False, False),
    # ── Employee ──────────────────────────────────────────────────────────────
    ("employee", "users"):        (False, False, False, False),
    ("employee", "courses"):      (True,  False, False, False),
    ("employee", "content"):      (True,  False, False, False),
    ("employee", "departments"):  (False, False, False, False),
    ("employee", "enrollments"):  (True,  False, False, False),
    ("employee", "live_classes"): (True,  False, False, False),
    ("employee", "assignments"):  (True,  False, True,  False),
    ("employee", "certificates"): (True,  False, False, False),
    ("employee", "reports"):      (False, False, False, False),
    ("employee", "auto_assign"):  (False, False, False, False),
}

ROLES_MANAGED = [RoleEnum.hr_admin, RoleEnum.manager, RoleEnum.employee]
RESOURCES = [
    "users", "courses", "content", "departments", "enrollments",
    "live_classes", "assignments", "certificates", "reports", "auto_assign",
]


def _seed_defaults(db: Session) -> None:
    """Insert default rows for any (role, resource) pair that doesn't exist yet."""
    for (role_str, resource), (v, c, u, d) in DEFAULTS.items():
        exists = db.query(RolePermission).filter(
            RolePermission.role == role_str,
            RolePermission.resource == resource,
        ).first()
        if not exists:
            db.add(RolePermission(
                role=role_str, resource=resource,
                can_view=v, can_create=c, can_update=u, can_delete=d,
            ))
    db.commit()


def _to_dict(p: RolePermission) -> dict:
    return {
        "role":       p.role,
        "resource":   p.resource,
        "can_view":   p.can_view,
        "can_create": p.can_create,
        "can_update": p.can_update,
        "can_delete": p.can_delete,
    }


# ─── GET all permissions (super admin manages; others read their own) ─────────
@router.get("/all")
def get_all_permissions(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_super_admin),
):
    _seed_defaults(db)
    rows = db.query(RolePermission).order_by(
        RolePermission.role, RolePermission.resource
    ).all()
    return [_to_dict(r) for r in rows]


@router.get("/my")
def get_my_permissions(
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    """Return this user's role permissions (used by the frontend to enforce UI gates)."""
    if current.role == RoleEnum.super_admin:
        # Super admin — synthesise full-access rows so frontend has a uniform shape
        return [
            {"role": "super_admin", "resource": r,
             "can_view": True, "can_create": True, "can_update": True, "can_delete": True}
            for r in RESOURCES
        ]
    _seed_defaults(db)
    rows = db.query(RolePermission).filter(
        RolePermission.role == current.role
    ).all()
    return [_to_dict(r) for r in rows]


# ─── Update a single permission cell ─────────────────────────────────────────
class PermissionUpdate(BaseModel):
    can_view:   Optional[bool] = None
    can_create: Optional[bool] = None
    can_update: Optional[bool] = None
    can_delete: Optional[bool] = None


@router.patch("/{role}/{resource}")
def update_permission(
    role: str,
    resource: str,
    data: PermissionUpdate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_super_admin),
):
    if role not in [r.value for r in ROLES_MANAGED]:
        raise HTTPException(status_code=400, detail=f"Cannot modify permissions for role '{role}'")
    if resource not in RESOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown resource '{resource}'")

    _seed_defaults(db)
    perm = db.query(RolePermission).filter(
        RolePermission.role == role,
        RolePermission.resource == resource,
    ).first()
    if not perm:
        raise HTTPException(status_code=404, detail="Permission row not found")

    if data.can_view   is not None: perm.can_view   = data.can_view
    if data.can_create is not None: perm.can_create = data.can_create
    if data.can_update is not None: perm.can_update = data.can_update
    if data.can_delete is not None: perm.can_delete = data.can_delete

    db.commit()
    return _to_dict(perm)


# ─── Bulk update for a whole role (e.g. "Full Access" / "View Only" presets) ──
class BulkRoleUpdate(BaseModel):
    can_view:   bool
    can_create: bool
    can_update: bool
    can_delete: bool


@router.put("/{role}/bulk")
def bulk_update_role(
    role: str,
    data: BulkRoleUpdate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_super_admin),
):
    if role not in [r.value for r in ROLES_MANAGED]:
        raise HTTPException(status_code=400, detail=f"Cannot modify permissions for role '{role}'")

    _seed_defaults(db)
    rows = db.query(RolePermission).filter(RolePermission.role == role).all()
    for perm in rows:
        perm.can_view   = data.can_view
        perm.can_create = data.can_create
        perm.can_update = data.can_update
        perm.can_delete = data.can_delete
    db.commit()
    return {"updated": len(rows), "role": role}


# ─── Reset a role (or all roles) to factory defaults ─────────────────────────
@router.post("/reset")
def reset_to_defaults(
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_super_admin),
):
    if role and role not in [r.value for r in ROLES_MANAGED]:
        raise HTTPException(status_code=400, detail=f"Unknown role '{role}'")

    query = db.query(RolePermission)
    if role:
        query = query.filter(RolePermission.role == role)
    query.delete()
    db.commit()
    _seed_defaults(db)
    return {"message": f"Permissions reset to defaults{' for ' + role if role else ' for all roles'}"}
