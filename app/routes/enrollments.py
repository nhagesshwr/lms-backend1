from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Enrollment, Course, Employee, Certificate, LessonProgress, Lesson, EnrollmentRequest
from app.schemas import (
    EnrollRequest, AssignCourseRequest, EnrollmentResponse, CertificateResponse
)
from app.dependencies import require_employee, require_hr_admin, get_current_employee
from datetime import datetime
import uuid

router = APIRouter(prefix="/enrollments", tags=["Enrollments"])


@router.post("/enroll", response_model=EnrollmentResponse)
def self_enroll(
    data: EnrollRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee)
):
    """Employee self-enrolls in a published course."""
    course = db.query(Course).filter(Course.id == data.course_id, Course.is_published == True).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found or not published")

    existing = db.query(Enrollment).filter(
        Enrollment.employee_id == current.id,
        Enrollment.course_id == data.course_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already enrolled in this course")

    enrollment = Enrollment(
        employee_id=current.id,
        course_id=data.course_id,
        enrolled_by=current.id
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


@router.post("/assign", response_model=EnrollmentResponse)
def assign_course(
    data: AssignCourseRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin)
):
    """Admin assigns a course to an employee."""
    course = db.query(Course).filter(Course.id == data.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    existing = db.query(Enrollment).filter(
        Enrollment.employee_id == data.employee_id,
        Enrollment.course_id == data.course_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Employee already enrolled in this course")

    enrollment = Enrollment(
        employee_id=data.employee_id,
        course_id=data.course_id,
        enrolled_by=current.id
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


@router.delete("/unenroll/{course_id}")
def unenroll(
    course_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee)
):
    enrollment = db.query(Enrollment).filter(
        Enrollment.employee_id == current.id,
        Enrollment.course_id == course_id
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    db.delete(enrollment)
    db.commit()
    return {"message": "Unenrolled successfully"}

@router.delete("/admin/unenroll/{employee_id}/{course_id}")
def admin_unenroll(
    employee_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin)
):
    """Super Admin or HR Admin removes a course for a particular user."""
    enrollment = db.query(Enrollment).filter(
        Enrollment.employee_id == employee_id,
        Enrollment.course_id == course_id
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="User is not enrolled in this course")
    
    db.delete(enrollment)
    db.commit()
    return {"message": "User successfully removed from course"}


@router.get("/my", response_model=list[EnrollmentResponse])
def get_my_enrollments(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee)
):
    enrollments = db.query(Enrollment).options(
        joinedload(Enrollment.course)
    ).filter(Enrollment.employee_id == current.id).all()
    return enrollments


@router.get("/course/{course_id}/employees", response_model=list[dict])
def get_enrolled_employees(
    course_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin)
):
    """Get all employees enrolled in a course (admin only)."""
    enrollments = db.query(Enrollment).options(
        joinedload(Enrollment.employee)
    ).filter(Enrollment.course_id == course_id).all()

    return [
        {
            "enrollment_id": e.id,
            "employee_id": e.employee_id,
            "employee_name": e.employee.name,
            "employee_email": e.employee.email,
            "enrolled_at": e.enrolled_at,
            "progress_pct": e.progress_pct,
            "completed": e.completed
        }
        for e in enrollments
    ]


@router.get("/employee/{employee_id}")
def get_employee_enrollments(
    employee_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin)
):
    """Get all courses enrolled for a specific employee (admin/manager view)."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    enrollments = db.query(Enrollment).options(
        joinedload(Enrollment.course)
    ).filter(Enrollment.employee_id == employee_id).all()

    return [
        {
            "enrollment_id": e.id,
            "course_id": e.course_id,
            "course_title": e.course.title if e.course else "—",
            "course_thumbnail": e.course.thumbnail_url if e.course else None,
            "course_category": e.course.category if e.course else None,
            "enrolled_at": e.enrolled_at,
            "progress_pct": e.progress_pct or 0,
            "completed": e.completed or False,
            "completed_at": e.completed_at,
        }
        for e in enrollments
    ]


@router.post("/complete-lesson")
def mark_lesson_complete(
    lesson_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee)
):
    """Mark a lesson as completed and update enrollment progress."""
    enrollment = db.query(Enrollment).filter(
        Enrollment.employee_id == current.id,
        Enrollment.course_id == course_id
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Not enrolled in this course")

    # Check if already marked
    existing = db.query(LessonProgress).filter(
        LessonProgress.enrollment_id == enrollment.id,
        LessonProgress.lesson_id == lesson_id
    ).first()

    if existing:
        existing.completed = True
        existing.completed_at = datetime.utcnow()
    else:
        prog = LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=lesson_id,
            completed=True,
            completed_at=datetime.utcnow()
        )
        db.add(prog)

    # Recalculate progress % strictly against lessons belonging to this course
    course_lessons = db.query(Lesson).filter(Lesson.course_id == course_id).all()
    lesson_ids = [l.id for l in course_lessons]
    total_lessons = len(lesson_ids)

    completed_lessons_count = 0
    if total_lessons > 0:
        completed_lessons_count = db.query(LessonProgress).filter(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.lesson_id.in_(lesson_ids),
            LessonProgress.completed == True
        ).count()
        
        enrollment.progress_pct = round((completed_lessons_count / total_lessons) * 100, 1)

    # Force completion status if progress is 100
    if enrollment.progress_pct >= 100:
        if not enrollment.completed:
            enrollment.completed = True
            enrollment.completed_at = datetime.utcnow()
    else:
        enrollment.completed = False

    db.commit()
    db.refresh(enrollment)
    return {
        "progress_pct": enrollment.progress_pct,
        "completed": enrollment.completed,
        "total": total_lessons,
        "completed_count": completed_lessons_count,
    }


@router.get("/check/{course_id}")
def check_enrollment(
    course_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee)
):
    """Check if current user is enrolled in a course."""
    enrollment = db.query(Enrollment).filter(
        Enrollment.employee_id == current.id,
        Enrollment.course_id == course_id
    ).first()
    
    progress_records = []
    has_cert = False
    progress_pct = 0.0
    is_completed = False

    if enrollment:
        # Robust progress calculation
        course_lessons = db.query(Lesson).filter(Lesson.course_id == course_id).all()
        lesson_ids = [l.id for l in course_lessons]
        total_lessons = len(lesson_ids)
        
        progress_records = db.query(LessonProgress).filter(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.lesson_id.in_(lesson_ids)
        ).all()
        
        completed_count = sum(1 for p in progress_records if p.completed)
        
        if total_lessons > 0:
            progress_pct = round((completed_count / total_lessons) * 100, 1)
        
        # Sync enrollment state if needed
        if progress_pct >= 100 and not enrollment.completed:
            enrollment.progress_pct = progress_pct
            enrollment.completed = True
            enrollment.completed_at = datetime.utcnow()
            db.commit()
        elif enrollment.progress_pct != progress_pct:
            enrollment.progress_pct = progress_pct
            db.commit()

        is_completed = enrollment.completed
        has_cert = db.query(Certificate).filter(Certificate.employee_id == current.id, Certificate.course_id == course_id).first() is not None

    return {
        "enrolled": enrollment is not None,
        "progress_pct": progress_pct,
        "completed": is_completed,
        "progress": [
            {
                "lesson_id": p.lesson_id,
                "completed": p.completed,
                "watched_seconds": p.watched_seconds or 0,
            }
            for p in progress_records
        ],
        "has_certificate": has_cert,
    }


@router.put("/video-progress")
def update_video_progress(
    lesson_id: int,
    course_id: int,
    watched_seconds: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee),
):
    """Persist the current playback position so users can resume later."""
    if watched_seconds < 0:
        watched_seconds = 0

    enrollment = db.query(Enrollment).filter(
        Enrollment.employee_id == current.id,
        Enrollment.course_id == course_id,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Not enrolled in this course")

    existing = db.query(LessonProgress).filter(
        LessonProgress.enrollment_id == enrollment.id,
        LessonProgress.lesson_id == lesson_id,
    ).first()

    if existing:
        # Only advance the saved position — never rewind (prevents seek-back data loss)
        if watched_seconds > existing.watched_seconds:
            existing.watched_seconds = watched_seconds
    else:
        db.add(LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=lesson_id,
            watched_seconds=watched_seconds,
        ))

    db.commit()
    return {"watched_seconds": watched_seconds}


# ── Enrollment Requests ───────────────────────────────────────────────────────

@router.post("/request")
def request_enrollment(
    data: EnrollRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee),
):
    """Employee requests enrollment in a course (pending admin approval)."""
    course = db.query(Course).filter(Course.id == data.course_id, Course.is_published == True).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found or not published")

    # Already enrolled?
    if db.query(Enrollment).filter(
        Enrollment.employee_id == current.id,
        Enrollment.course_id == data.course_id
    ).first():
        raise HTTPException(status_code=400, detail="Already enrolled in this course")

    # Already requested?
    existing = db.query(EnrollmentRequest).filter(
        EnrollmentRequest.employee_id == current.id,
        EnrollmentRequest.course_id == data.course_id,
    ).first()
    if existing:
        if existing.status == "pending":
            raise HTTPException(status_code=400, detail="Enrollment request already pending")
        if existing.status == "approved":
            raise HTTPException(status_code=400, detail="Already enrolled")
        # rejected — allow re-request
        existing.status = "pending"
        existing.reviewed_by = None
        existing.reviewed_at = None
        existing.created_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return {"id": existing.id, "status": "pending", "course_id": data.course_id}

    req = EnrollmentRequest(employee_id=current.id, course_id=data.course_id)
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"id": req.id, "status": "pending", "course_id": data.course_id}


@router.get("/requests/my")
def get_my_requests(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee),
):
    """Employee sees their own enrollment requests."""
    reqs = db.query(EnrollmentRequest).options(
        joinedload(EnrollmentRequest.course)
    ).filter(EnrollmentRequest.employee_id == current.id).all()
    return [
        {
            "id": r.id,
            "course_id": r.course_id,
            "course_title": r.course.title if r.course else "—",
            "status": r.status,
            "created_at": r.created_at,
            "reviewed_at": r.reviewed_at,
        }
        for r in reqs
    ]


@router.get("/requests/all")
def get_all_requests(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin),
):
    """Admin/super-admin sees all enrollment requests."""
    reqs = db.query(EnrollmentRequest).options(
        joinedload(EnrollmentRequest.employee),
        joinedload(EnrollmentRequest.course),
        joinedload(EnrollmentRequest.reviewer),
    ).order_by(EnrollmentRequest.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "employee_id": r.employee_id,
            "employee_name": r.employee.name if r.employee else "—",
            "employee_email": r.employee.email if r.employee else "—",
            "course_id": r.course_id,
            "course_title": r.course.title if r.course else "—",
            "status": r.status,
            "note": r.note,
            "created_at": r.created_at,
            "reviewed_at": r.reviewed_at,
            "reviewed_by_name": r.reviewer.name if r.reviewer else None,
        }
        for r in reqs
    ]


@router.post("/requests/{request_id}/approve")
def approve_request(
    request_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin),
):
    """Approve an enrollment request — creates the actual enrollment."""
    req = db.query(EnrollmentRequest).filter(EnrollmentRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {req.status}")

    # Create enrollment if not already enrolled
    existing = db.query(Enrollment).filter(
        Enrollment.employee_id == req.employee_id,
        Enrollment.course_id == req.course_id,
    ).first()
    if not existing:
        db.add(Enrollment(
            employee_id=req.employee_id,
            course_id=req.course_id,
            enrolled_by=current.id,
        ))

    req.status = "approved"
    req.reviewed_by = current.id
    req.reviewed_at = datetime.utcnow()
    db.commit()
    return {"message": "Approved", "request_id": request_id}


@router.post("/requests/{request_id}/reject")
def reject_request(
    request_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_hr_admin),
):
    """Reject an enrollment request."""
    req = db.query(EnrollmentRequest).filter(EnrollmentRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {req.status}")

    req.status = "rejected"
    req.reviewed_by = current.id
    req.reviewed_at = datetime.utcnow()
    db.commit()
    return {"message": "Rejected", "request_id": request_id}
