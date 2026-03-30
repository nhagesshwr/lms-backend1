"""
app/routes/settings.py

Super-admin endpoint to manage SMTP settings stored in the database.
When a SmtpConfig row exists (and is_active=True), it takes priority over
the SMTP_* environment variables used in auth.py.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SmtpConfig
from app.schemas import SmtpConfigCreate, SmtpConfigUpdate, SmtpConfigResponse
from app.dependencies import require_super_admin
from app.models import Employee
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/settings", tags=["Settings"])


# ─── Helper: get active SMTP config from DB (used by auth.py too) ────────────
def get_smtp_config_from_db(db: Session) -> Optional[SmtpConfig]:
    """Return the active SmtpConfig row if present, else None."""
    return db.query(SmtpConfig).filter(SmtpConfig.is_active == True).first()


# ─── GET /settings/smtp ───────────────────────────────────────────────────────
@router.get("/smtp", response_model=SmtpConfigResponse)
def get_smtp_config(
    db: Session = Depends(get_db),
    _: Employee = Depends(require_super_admin),
):
    """Return the current SMTP configuration (super admin only)."""
    cfg = db.query(SmtpConfig).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="SMTP config not set yet")
    return cfg


# ─── PUT /settings/smtp ───────────────────────────────────────────────────────
@router.put("/smtp", response_model=SmtpConfigResponse)
def upsert_smtp_config(
    data: SmtpConfigCreate,
    db: Session = Depends(get_db),
    _: Employee = Depends(require_super_admin),
):
    """Create or fully replace the SMTP configuration (super admin only)."""
    cfg = db.query(SmtpConfig).first()
    if cfg:
        # Update existing row
        cfg.smtp_host  = data.smtp_host
        cfg.smtp_port  = data.smtp_port
        cfg.smtp_user  = data.smtp_user
        cfg.smtp_pass  = data.smtp_pass
        cfg.from_email = data.from_email
        cfg.from_name  = data.from_name
        cfg.use_tls    = data.use_tls
        cfg.is_active  = data.is_active
    else:
        cfg = SmtpConfig(
            smtp_host  = data.smtp_host,
            smtp_port  = data.smtp_port,
            smtp_user  = data.smtp_user,
            smtp_pass  = data.smtp_pass,
            from_email = data.from_email,
            from_name  = data.from_name,
            use_tls    = data.use_tls,
            is_active  = data.is_active,
        )
        db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


# ─── PATCH /settings/smtp ─────────────────────────────────────────────────────
@router.patch("/smtp", response_model=SmtpConfigResponse)
def patch_smtp_config(
    data: SmtpConfigUpdate,
    db: Session = Depends(get_db),
    _: Employee = Depends(require_super_admin),
):
    """Partially update the SMTP configuration (super admin only)."""
    cfg = db.query(SmtpConfig).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="SMTP config not set yet. Use PUT to create.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    return cfg


# ─── DELETE /settings/smtp ────────────────────────────────────────────────────
@router.delete("/smtp", status_code=204)
def delete_smtp_config(
    db: Session = Depends(get_db),
    _: Employee = Depends(require_super_admin),
):
    """Remove SMTP config so the system falls back to env vars (super admin only)."""
    cfg = db.query(SmtpConfig).first()
    if cfg:
        db.delete(cfg)
        db.commit()
    return None


# ─── POST /settings/smtp/test ─────────────────────────────────────────────────
class SmtpTestRequest(BaseModel):
    to_email: str

@router.post("/smtp/test")
def test_smtp(
    payload: SmtpTestRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_super_admin),
):
    """
    Send a test email using the currently saved SMTP configuration.
    Returns 200 with a success message, or 400 with the error detail.
    """
    cfg = db.query(SmtpConfig).filter(SmtpConfig.is_active == True).first()
    if not cfg:
        raise HTTPException(status_code=400, detail="No active SMTP config found. Please save SMTP settings first.")

    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        from_addr = cfg.from_email or cfg.smtp_user
        display_name = cfg.from_name or "Bryte LMS"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "✅ Bryte LMS — SMTP Test Email"
        msg["From"]    = f"{display_name} <{from_addr}>"
        msg["To"]      = payload.to_email

        html = f"""
        <html>
          <body style="font-family:'Segoe UI',sans-serif;background:#f8fafc;padding:40px;color:#0f172a;">
            <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;
                        padding:40px;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
              <h2 style="color:#6366f1;margin-bottom:8px;">SMTP Test Successful 🎉</h2>
              <p style="color:#64748b;">Hi there,</p>
              <p style="color:#64748b;">
                Your SMTP settings are configured correctly in <strong>Bryte LMS</strong>.<br/>
                This test was triggered by <strong>{current.name}</strong>.
              </p>
              <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;"/>
              <p style="color:#94a3b8;font-size:12px;">
                Host: {cfg.smtp_host}:{cfg.smtp_port} &nbsp;|&nbsp; User: {cfg.smtp_user}
              </p>
            </div>
          </body>
        </html>
        """
        msg.attach(MIMEText(html, "html"))

        if cfg.use_tls:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
                server.starttls()
                server.login(cfg.smtp_user, cfg.smtp_pass)
                server.sendmail(from_addr, payload.to_email, msg.as_string())
        else:
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port) as server:
                server.login(cfg.smtp_user, cfg.smtp_pass)
                server.sendmail(from_addr, payload.to_email, msg.as_string())

        return {"success": True, "message": f"Test email sent to {payload.to_email}"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SMTP error: {str(e)}")
