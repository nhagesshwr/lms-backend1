from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Assignment, AssignmentSubmission, Enrollment, Employee, Course
from app.schemas import (
    AssignmentCreate, AssignmentUpdate, AssignmentResponse,
    SubmissionCreate, GradeSubmissionRequest, SubmissionResponse
)
from app.dependencies import require_employee, require_hr_admin
from datetime import datetime

router = APIRouter(prefix="/assignments", tags=["Assignments"])


@router.post("/", response_model=AssignmentResponse)
@router.post("", response_model=AssignmentResponse)
def create_assignment(
    data: AssignmentCreate,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin),
):
    course = db.query(Course).filter(Course.id == data.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    assignment = Assignment(
        course_id=data.course_id,
        title=data.title,
        description=data.description,
        due_date=data.due_date,
        points=data.points,
        assignment_type=data.assignment_type,
        created_by=current.id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("/my", response_model=list[dict])
def get_my_assignments(
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee),
):
    """Get all assignments for courses the employee is enrolled in."""
    enrollments = db.query(Enrollment).filter(
        Enrollment.employee_id == current.id
    ).all()
    course_ids = [e.course_id for e in enrollments]

    if not course_ids:
        return []

    assignments = db.query(Assignment).options(
        joinedload(Assignment.course)
    ).filter(Assignment.course_id.in_(course_ids)).all()

    now = datetime.utcnow()
    result = []
    for a in assignments:
        submission = db.query(AssignmentSubmission).filter(
            AssignmentSubmission.assignment_id == a.id,
            AssignmentSubmission.employee_id == current.id,
        ).first()

        if submission:
            status = "graded" if submission.grade is not None else "submitted"
        elif a.due_date and a.due_date < now:
            status = "overdue"
        elif a.due_date and (a.due_date - now).days == 0:
            status = "due_today"
        else:
            status = "upcoming"

        result.append({
            "id": a.id,
            "title": a.title,
            "course": a.course.title if a.course else "",
            "course_id": a.course_id,
            "due": a.due_date.isoformat() if a.due_date else None,
            "points": a.points,
            "type": a.assignment_type,
            "status": status,
            "grade": submission.grade if submission else None,
            "description": a.description,
        })
    return result


@router.get("/all", response_model=list[AssignmentResponse])
def get_all_assignments(
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin),
):
    return db.query(Assignment).options(joinedload(Assignment.course)).all()


@router.get("/course/{course_id}", response_model=list[AssignmentResponse])
def get_course_assignments(
    course_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_employee),
):
    return db.query(Assignment).filter(Assignment.course_id == course_id).all()


@router.get("/{assignment_id}", response_model=AssignmentResponse)
def get_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_employee),
):
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return a


@router.put("/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(
    assignment_id: int,
    data: AssignmentUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin),
):
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if data.title:
        a.title = data.title
    if data.description:
        a.description = data.description
    if data.due_date:
        a.due_date = data.due_date
    if data.points is not None:
        a.points = data.points
    if data.assignment_type:
        a.assignment_type = data.assignment_type
    db.commit()
    db.refresh(a)
    return a


@router.delete("/{assignment_id}")
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin),
):
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(a)
    db.commit()
    return {"message": "Assignment deleted"}


@router.post("/{assignment_id}/submit", response_model=SubmissionResponse)
def submit_assignment(
    assignment_id: int,
    data: SubmissionCreate,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee),
):
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # Verify the employee is enrolled in the course that owns this assignment
    enrollment = db.query(Enrollment).filter(
        Enrollment.employee_id == current.id,
        Enrollment.course_id == a.course_id,
    ).first()
    if not enrollment:
        raise HTTPException(
            status_code=403,
            detail="You must be enrolled in this course to submit assignments",
        )

    existing = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id == assignment_id,
        AssignmentSubmission.employee_id == current.id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already submitted")

    submission = AssignmentSubmission(
        assignment_id=assignment_id,
        employee_id=current.id,
        submission_text=data.submission_text,
        status="submitted",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.post("/{assignment_id}/grade/{employee_id}", response_model=SubmissionResponse)
def grade_submission(
    assignment_id: int,
    employee_id: int,
    data: GradeSubmissionRequest,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin),
):
    submission = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id == assignment_id,
        AssignmentSubmission.employee_id == employee_id,
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    submission.grade = data.grade
    submission.feedback = data.feedback
    submission.graded_at = datetime.utcnow()
    submission.graded_by = current.id
    submission.status = "graded"
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/{assignment_id}/submissions")
def get_submissions(
    assignment_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin),
):
    return db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id == assignment_id
    ).all()
