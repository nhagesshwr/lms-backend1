from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.models import Employee, PasswordResetToken
from app.schemas import (
    EmployeeCreate, RegisterRequest, LoginRequest, TokenResponse, EmployeeResponse,
    ChangePasswordRequest, ForgotPasswordRequest, ResetPasswordRequest,
    UpdateProfileRequest
)
from app.auth import hash_password, verify_password, create_access_token, create_refresh_token, decode_refresh_token
from app.dependencies import get_current_employee, require_super_admin, require_hr_admin
from datetime import datetime, timedelta
import secrets
import os

router = APIRouter(prefix="/auth", tags=["Auth"])

_IS_PRODUCTION = os.getenv("ENV", "development").lower() == "production"


# ─── Helper: resolve SMTP settings (DB first, then env vars) ─────────────────
def _get_smtp_settings(db: "Session"):
    """Return (host, port, user, password, from_email, from_name, use_tls) tuple."""
    try:
        from app.models import SmtpConfig
        cfg = db.query(SmtpConfig).filter(SmtpConfig.is_active == True).first()
        if cfg:
            return (
                cfg.smtp_host,
                cfg.smtp_port,
                cfg.smtp_user,
                cfg.smtp_pass,
                cfg.from_email or cfg.smtp_user,
                cfg.from_name or "Bryte LMS",
                cfg.use_tls,
            )
    except Exception:
        pass

    host       = os.getenv("SMTP_HOST")
    port       = int(os.getenv("SMTP_PORT", "587"))
    user       = os.getenv("SMTP_USER")
    password   = os.getenv("SMTP_PASS")
    from_email = os.getenv("FROM_EMAIL", user)
    return host, port, user, password, from_email, "Bryte LMS", True


# ─── Notify admins of new registration ───────────────────────────────────────
def _notify_admins_new_user(new_emp: "Employee", db: "Session"):
    try:
        from app.models import Message
        admins = db.query(Employee).filter(
            Employee.role.in_(["super_admin", "hr_admin"])
        ).all()
        content = (
            f"New Employee Registered\n\n"
            f"Name: {new_emp.name}\n"
            f"Email: {new_emp.email}\n\n"
            f"They have been auto-assigned the Employee role and can log in "
            f"once you approve their role from the Employees panel."
        )
        for admin in admins:
            msg = Message(sender_id=new_emp.id, receiver_id=admin.id, content=content)
            db.add(msg)
        db.commit()
    except Exception:
        pass


# ─── Register ─────────────────────────────────────────────────────────────────
@router.post("/register", response_model=EmployeeResponse)
def register(employee: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(Employee).filter(Employee.email == employee.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    new_employee = Employee(
        name=employee.name,
        email=employee.email,
        hashed_password=hash_password(employee.password),
        role="employee",
        is_pending=True,
    )
    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)
    _notify_admins_new_user(new_employee, db)
    return new_employee


# ─── Assign Role ──────────────────────────────────────────────────────────────
class AssignRoleRequest(BaseModel):
    role: str
    department_id: Optional[int] = None


@router.put("/assign-role/{employee_id}")
def assign_role(
    employee_id: int,
    data: AssignRoleRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin),
):
    from app.models import RoleEnum, AutoAssignRule, Enrollment
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="User not found")

    valid_roles = [r.value for r in RoleEnum]
    if data.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Choices: {valid_roles}")

    # Prevent privilege escalation: only super_admin can assign super_admin role
    if data.role == "super_admin" and current.role.value != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admins can assign super_admin role")

    emp.role = data.role
    emp.is_pending = False
    if data.department_id is not None:
        emp.department_id = data.department_id
    db.commit()
    db.refresh(emp)

    # ── Auto-assign courses ───────────────────────────────────────────────────
    auto_enrolled = 0
    try:
        rules = db.query(AutoAssignRule).filter(
            AutoAssignRule.is_active == True,
        ).filter(
            (AutoAssignRule.department_id == None) |
            (AutoAssignRule.department_id == emp.department_id)
        ).all()

        for rule in rules:
            existing = db.query(Enrollment).filter(
                Enrollment.employee_id == emp.id,
                Enrollment.course_id == rule.course_id,
            ).first()
            if not existing:
                db.add(Enrollment(
                    employee_id=emp.id,
                    course_id=rule.course_id,
                    enrolled_by=current.id,
                ))
                auto_enrolled += 1

        if auto_enrolled:
            db.commit()
    except Exception:
        pass

    try:
        _send_role_assigned_email(emp.email, emp.name, data.role, db)
    except Exception:
        pass

    return {
        "id": emp.id,
        "name": emp.name,
        "email": emp.email,
        "role": emp.role,
        "is_active": emp.is_active,
        "is_pending": emp.is_pending,
        "department_id": emp.department_id,
        "created_at": emp.created_at,
        "auto_enrolled_count": auto_enrolled,
    }


def _send_role_assigned_email(to_email: str, name: str, role: str, db=None):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host, smtp_port, smtp_user, smtp_pass, from_email, from_name, use_tls = _get_smtp_settings(db)

    if not all([smtp_host, smtp_user, smtp_pass]):
        raise Exception("SMTP not configured")

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    role_labels = {
        "employee":    "Employee",
        "manager":     "Manager",
        "hr_admin":    "HR Admin",
        "super_admin": "Super Admin",
    }
    role_label = role_labels.get(role, role.replace("_", " ").title())

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Bryte LMS Account is Ready!"
    msg["From"]    = f"{from_name} <{from_email}>"
    msg["To"]      = to_email

    html = f"""
    <html>
      <body style="font-family: 'Segoe UI', sans-serif; background: #f8fafc; padding: 40px; color: #0f172a;">
        <div style="max-width: 480px; margin: 0 auto; background: #fff; border-radius: 16px; padding: 40px; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">
          <h2 style="color: #6366f1; margin-bottom: 8px;">Welcome to Bryte LMS!</h2>
          <p style="color: #64748b;">Hi {name},</p>
          <p style="color: #64748b;">Your account has been reviewed and you have been assigned the role of <strong style="color: #6366f1;">{role_label}</strong>.</p>
          <p style="color: #64748b;">You can now log in and access all features available to your role.</p>
          <a href="{frontend_url}/login" style="display: inline-block; margin: 24px 0; padding: 14px 28px; background: #6366f1; color: #fff; border-radius: 10px; text-decoration: none; font-weight: 600;">Log In to Bryte</a>
          <p style="color: #94a3b8; font-size: 13px;">If you did not register for Bryte LMS, please ignore this email.</p>
        </div>
      </body>
    </html>
    """
    msg.attach(MIMEText(html, "html"))
    if use_tls:
        with smtplib.SMTP(str(smtp_host), smtp_port) as server:
            server.starttls()
            server.login(str(smtp_user), str(smtp_pass))
            server.sendmail(str(from_email), to_email, msg.as_string())
    else:
        with smtplib.SMTP_SSL(str(smtp_host), smtp_port) as server:
            server.login(str(smtp_user), str(smtp_pass))
            server.sendmail(str(from_email), to_email, msg.as_string())


# ─── Login ────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.email == request.email).first()
    # Use constant-time comparison (bcrypt) even when employee not found to prevent timing attacks
    if not employee or not verify_password(request.password, employee.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not employee.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated. Contact your administrator.")
    if employee.is_pending:
        raise HTTPException(status_code=403, detail="Your account is awaiting admin approval. You will receive an email once your role has been assigned.")
    access_token = create_access_token({"sub": employee.email, "role": employee.role, "id": employee.id})
    refresh_token = create_refresh_token({"sub": employee.email, "id": employee.id})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": employee.role,
        "name": employee.name,
        "id": employee.id,
    }


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_refresh_token(data.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    employee = db.query(Employee).filter(Employee.email == payload.get("sub")).first()
    if not employee:
        raise HTTPException(status_code=401, detail="User not found")
    if not employee.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    if employee.is_pending:
        raise HTTPException(status_code=403, detail="Account is awaiting approval")

    new_access_token = create_access_token({"sub": employee.email, "role": employee.role, "id": employee.id})
    new_refresh_token = create_refresh_token({"sub": employee.email, "id": employee.id})
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "role": employee.role,
        "name": employee.name,
        "id": employee.id,
    }


@router.get("/me", response_model=EmployeeResponse)
def get_me(current: Employee = Depends(get_current_employee)):
    return current


@router.put("/me", response_model=EmployeeResponse)
def update_profile(
    data: UpdateProfileRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    if data.name:
        current.name = data.name
    if data.email:
        existing = db.query(Employee).filter(
            Employee.email == data.email, Employee.id != current.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use by another user")
        current.email = data.email
    db.commit()
    db.refresh(current)
    return current


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(get_current_employee),
):
    if not verify_password(data.current_password, current.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from current password")
    current.hashed_password = hash_password(data.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Always return success to prevent email enumeration
    _SAFE_RESPONSE = {"message": "If this email is registered, a reset link has been sent."}

    employee = db.query(Employee).filter(Employee.email == data.email).first()
    if not employee:
        return _SAFE_RESPONSE

    # Invalidate existing tokens
    db.query(PasswordResetToken).filter(
        PasswordResetToken.employee_id == employee.id,
        PasswordResetToken.used == False,
    ).update({"used": True})

    token = secrets.token_urlsafe(32)
    reset_token = PasswordResetToken(
        employee_id=employee.id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db.add(reset_token)
    db.commit()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    reset_link = f"{frontend_url}/reset-password?token={token}"

    try:
        _send_reset_email(employee.email, employee.name, reset_link, db)
    except Exception:
        pass

    # Only expose the link in non-production (dev convenience)
    if not _IS_PRODUCTION:
        return {**_SAFE_RESPONSE, "reset_link": reset_link}

    return _SAFE_RESPONSE


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == data.token,
        PasswordResetToken.used == False,
    ).first()

    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if token_record.expires_at < datetime.utcnow():
        token_record.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Reset token has expired")

    employee = db.query(Employee).filter(Employee.id == token_record.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee.hashed_password = hash_password(data.new_password)
    token_record.used = True
    db.commit()

    return {"message": "Password reset successfully. You can now log in."}


def _send_reset_email(to_email: str, name: str, reset_link: str, db=None):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host, smtp_port, smtp_user, smtp_pass, from_email, from_name, use_tls = _get_smtp_settings(db)

    if not all([smtp_host, smtp_user, smtp_pass]):
        raise Exception("SMTP not configured")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset Your LMS Password"
    msg["From"]    = f"{from_name} <{from_email}>"
    msg["To"]      = to_email

    html = f"""
    <html>
      <body style="font-family: 'Segoe UI', sans-serif; background: #f8fafc; padding: 40px; color: #0f172a;">
        <div style="max-width: 480px; margin: 0 auto; background: #fff; border-radius: 16px; padding: 40px; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">
          <h2 style="color: #6366f1; margin-bottom: 8px;">Password Reset</h2>
          <p style="color: #64748b;">Hi {name},</p>
          <p style="color: #64748b;">We received a request to reset your password. Click the button below to set a new password.</p>
          <a href="{reset_link}" style="display: inline-block; margin: 24px 0; padding: 14px 28px; background: #6366f1; color: #fff; border-radius: 10px; text-decoration: none; font-weight: 600;">Reset Password</a>
          <p style="color: #94a3b8; font-size: 13px;">This link expires in 1 hour. If you didn't request this, you can safely ignore it.</p>
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(html, "html"))

    if use_tls:
        with smtplib.SMTP(str(smtp_host), smtp_port) as server:
            server.starttls()
            server.login(str(smtp_user), str(smtp_pass))
            server.sendmail(str(from_email), to_email, msg.as_string())
    else:
        with smtplib.SMTP_SSL(str(smtp_host), smtp_port) as server:
            server.login(str(smtp_user), str(smtp_pass))
            server.sendmail(str(from_email), to_email, msg.as_string())
