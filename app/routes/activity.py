from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from app.database import get_db
from app.models import (
    Employee, Enrollment, Certificate, QuizAttempt, Quiz,
    AssignmentSubmission, Assignment, Course, LiveClass, LiveClassAudience
)
from app.dependencies import get_current_employee

router = APIRouter(prefix="/activity", tags=["Activity"])


def _time_ago(dt: datetime) -> str:
    if not dt:
        return "—"
    # Make both timezone-aware for comparison
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    s = int(diff.total_seconds())
    if s < 60:
        return "just now"
    if s < 3600:
        m = s // 60
        return f"{m} min ago"
    if s < 86400:
        h = s // 3600
        return f"{h} hour{'s' if h > 1 else ''} ago"
    d = s // 86400
    return f"{d} day{'s' if d > 1 else ''} ago"


def _initials(name: str) -> str:
    return "".join(w[0] for w in name.split() if w)[:2].upper()


@router.get("/recent")
def get_recent_activity(
    limit: int = Query(default=20, le=100),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_employee)
):
    events = []

    # ── Enrollments ──────────────────────────────────────────────────────────
    try:
        enrollments = (
            db.query(Enrollment, Employee, Course)
            .join(Employee, Enrollment.employee_id == Employee.id)
            .join(Course, Enrollment.course_id == Course.id)
            .order_by(Enrollment.enrolled_at.desc())
            .limit(30)
            .all()
        )
        for enr, emp, course in enrollments:
            events.append({
                "id":     f"enr-{enr.id}",
                "user":   emp.name,
                "role":   emp.role.value if hasattr(emp.role, 'value') else str(emp.role),
                "action": "Enrolled in course",
                "detail": course.title,
                "type":   "start",
                "time":   _time_ago(enr.enrolled_at),
                "ts":     enr.enrolled_at.timestamp() if enr.enrolled_at else 0,
            })
    except Exception:
        pass

    # ── Completed enrollments ─────────────────────────────────────────────────
    try:
        completed = (
            db.query(Enrollment, Employee, Course)
            .join(Employee, Enrollment.employee_id == Employee.id)
            .join(Course, Enrollment.course_id == Course.id)
            .filter(Enrollment.completed == True)
            .order_by(Enrollment.completed_at.desc())
            .limit(20)
            .all()
        )
        for enr, emp, course in completed:
            events.append({
                "id":     f"cmp-{enr.id}",
                "user":   emp.name,
                "role":   emp.role.value if hasattr(emp.role, 'value') else str(emp.role),
                "action": "Completed course",
                "detail": course.title,
                "type":   "complete",
                "time":   _time_ago(enr.completed_at),
                "ts":     enr.completed_at.timestamp() if enr.completed_at else 0,
            })
    except Exception:
        pass

    # ── Certificates ──────────────────────────────────────────────────────────
    try:
        certs = (
            db.query(Certificate, Employee, Course)
            .join(Employee, Certificate.employee_id == Employee.id)
            .join(Course, Certificate.course_id == Course.id)
            .order_by(Certificate.issued_at.desc())
            .limit(20)
            .all()
        )
        for cert, emp, course in certs:
            events.append({
                "id":     f"cert-{cert.id}",
                "user":   emp.name,
                "role":   emp.role.value if hasattr(emp.role, 'value') else str(emp.role),
                "action": "Earned certificate",
                "detail": course.title,
                "type":   "cert",
                "time":   _time_ago(cert.issued_at),
                "ts":     cert.issued_at.timestamp() if cert.issued_at else 0,
            })
    except Exception:
        pass

    # ── Quiz attempts ─────────────────────────────────────────────────────────
    try:
        attempts = (
            db.query(QuizAttempt, Employee, Quiz)
            .join(Employee, QuizAttempt.employee_id == Employee.id)
            .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
            .order_by(QuizAttempt.attempted_at.desc())
            .limit(20)
            .all()
        )
        for attempt, emp, quiz in attempts:
            events.append({
                "id":     f"quiz-{attempt.id}",
                "user":   emp.name,
                "role":   emp.role.value if hasattr(emp.role, 'value') else str(emp.role),
                "action": "Took quiz",
                "detail": f"{quiz.title} — {attempt.score}%",
                "type":   "quiz",
                "time":   _time_ago(attempt.attempted_at),
                "ts":     attempt.attempted_at.timestamp() if attempt.attempted_at else 0,
            })
    except Exception:
        pass

    # ── Assignment submissions ────────────────────────────────────────────────
    try:
        submissions = (
            db.query(AssignmentSubmission, Employee, Assignment)
            .join(Employee, AssignmentSubmission.employee_id == Employee.id)
            .join(Assignment, AssignmentSubmission.assignment_id == Assignment.id)
            .order_by(AssignmentSubmission.submitted_at.desc())
            .limit(20)
            .all()
        )
        for sub, emp, assign in submissions:
            events.append({
                "id":     f"sub-{sub.id}",
                "user":   emp.name,
                "role":   emp.role.value if hasattr(emp.role, 'value') else str(emp.role),
                "action": "Submitted assignment",
                "detail": assign.title,
                "type":   "submit",
                "time":   _time_ago(sub.submitted_at),
                "ts":     sub.submitted_at.timestamp() if sub.submitted_at else 0,
            })
    except Exception:
        pass

    # ── New employees (registrations) ─────────────────────────────────────────
    try:
        new_emps = (
            db.query(Employee)
            .order_by(Employee.created_at.desc())
            .limit(10)
            .all()
        )
        for emp in new_emps:
            events.append({
                "id":     f"emp-{emp.id}",
                "user":   emp.name,
                "role":   emp.role.value if hasattr(emp.role, 'value') else str(emp.role),
                "action": "Joined the platform",
                "detail": emp.email,
                "type":   "admin",
                "time":   _time_ago(emp.created_at),
                "ts":     emp.created_at.timestamp() if emp.created_at else 0,
            })
    except Exception:
        pass

    # ── Live class creations ──────────────────────────────────────────────────
    try:
        live_classes = (
            db.query(LiveClass, Employee)
            .outerjoin(Employee, LiveClass.created_by == Employee.id)
            .order_by(LiveClass.created_at.desc())
            .limit(10)
            .all()
        )
        for cls, creator in live_classes:
            events.append({
                "id":     f"lc-{cls.id}",
                "user":   creator.name if creator else "System",
                "role":   (creator.role.value if hasattr(creator.role, 'value') else str(creator.role)) if creator else "system",
                "action": "Scheduled live class",
                "detail": cls.title,
                "type":   "admin",
                "time":   _time_ago(cls.created_at),
                "ts":     cls.created_at.timestamp() if cls.created_at else 0,
            })
    except Exception:
        pass

    # ── Sort by timestamp desc, apply type filter, limit ─────────────────────
    events.sort(key=lambda e: e["ts"], reverse=True)

    if type_filter:
        events = [e for e in events if e["type"] == type_filter]

    return events[:limit]
