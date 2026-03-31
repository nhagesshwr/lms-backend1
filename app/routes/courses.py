from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Course, Lesson
from app.schemas import (
    CourseCreate, CourseUpdate, CourseResponse, CourseWithLessons,
    LessonCreate, LessonUpdate, LessonResponse
)
from app.dependencies import require_hr_admin, require_employee

router = APIRouter(prefix="/courses", tags=["Courses"])

# ── Course endpoints ──────────────────────────

# HR admin creates course
@router.post("/", response_model=CourseResponse)
@router.post("", response_model=CourseResponse)
def create_course(
    course: CourseCreate,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    new_course = Course(
        title=course.title,
        description=course.description,
        thumbnail_url=course.thumbnail_url,
        category=course.category,
        created_by=current.id
    )
    db.add(new_course)
    db.commit()
    db.refresh(new_course)
    return new_course

# HR admin views all courses including unpublished
@router.get("/all", response_model=list[CourseResponse])
def get_all_courses(
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    return db.query(Course).all()

# HR admin views all courses with their lessons included
@router.get("/all/with_lessons", response_model=list[CourseWithLessons])
def get_all_courses_with_lessons(
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    return db.query(Course).all()

# Everyone views all published courses
@router.get("/", response_model=list[CourseWithLessons])
@router.get("", response_model=list[CourseWithLessons])
def get_courses(
    db: Session = Depends(get_db),
    current=Depends(require_employee)
):
    return db.query(Course).filter(Course.is_published == True).all()

# Get single course with lessons
@router.get("/{course_id}", response_model=CourseWithLessons)
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_employee)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course

# HR admin updates course
@router.put("/{course_id}", response_model=CourseResponse)
def update_course(
    course_id: int,
    course_update: CourseUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course_update.title:
        course.title = course_update.title
    if course_update.description:
        course.description = course_update.description
    if course_update.thumbnail_url:
        course.thumbnail_url = course_update.thumbnail_url
    if course_update.category:
        course.category = course_update.category
    db.commit()
    db.refresh(course)
    return course

# HR admin publishes course
@router.post("/{course_id}/publish", response_model=CourseResponse)
def publish_course(
    course_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if not course.lessons:
        raise HTTPException(status_code=400, detail="Cannot publish course with no lessons")
    course.is_published = True
    db.commit()
    db.refresh(course)
    return course

# HR admin unpublishes course
@router.post("/{course_id}/unpublish", response_model=CourseResponse)
def unpublish_course(
    course_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    course.is_published = False
    db.commit()
    db.refresh(course)
    return course

# HR admin deletes course
@router.delete("/{course_id}")
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    from sqlalchemy import text
    # Get title first without loading relationships
    row = db.execute(text("SELECT title FROM courses WHERE id = :cid"), {"cid": course_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")
    title = row[0]

    # Full cascade delete via raw SQL to avoid ORM FK issues
    db.execute(text("DELETE FROM lesson_progress WHERE enrollment_id IN (SELECT id FROM enrollments WHERE course_id = :cid)"), {"cid": course_id})
    db.execute(text("DELETE FROM enrollments WHERE course_id = :cid"), {"cid": course_id})
    db.execute(text("DELETE FROM certificates WHERE course_id = :cid"), {"cid": course_id})
    db.execute(text("DELETE FROM assignment_submissions WHERE assignment_id IN (SELECT id FROM assignments WHERE course_id = :cid)"), {"cid": course_id})
    db.execute(text("DELETE FROM assignments WHERE course_id = :cid"), {"cid": course_id})
    db.execute(text("DELETE FROM quiz_attempts WHERE quiz_id IN (SELECT q.id FROM quizzes q JOIN lessons l ON q.lesson_id = l.id WHERE l.course_id = :cid)"), {"cid": course_id})
    db.execute(text("DELETE FROM quiz_questions WHERE quiz_id IN (SELECT q.id FROM quizzes q JOIN lessons l ON q.lesson_id = l.id WHERE l.course_id = :cid)"), {"cid": course_id})
    db.execute(text("DELETE FROM quizzes WHERE lesson_id IN (SELECT id FROM lessons WHERE course_id = :cid)"), {"cid": course_id})
    db.execute(text("DELETE FROM doubts WHERE lesson_id IN (SELECT id FROM lessons WHERE course_id = :cid)"), {"cid": course_id})
    db.execute(text("DELETE FROM lesson_progress WHERE lesson_id IN (SELECT id FROM lessons WHERE course_id = :cid)"), {"cid": course_id})
    db.execute(text("DELETE FROM lessons WHERE course_id = :cid"), {"cid": course_id})
    db.execute(text("DELETE FROM courses WHERE id = :cid"), {"cid": course_id})
    db.commit()
    return {"message": f"Course '{title}' deleted"}

# ── Lesson endpoints ──────────────────────────

# HR admin adds lesson to course
@router.post("/{course_id}/lessons", response_model=LessonResponse)
def add_lesson(
    course_id: int,
    lesson: LessonCreate,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    new_lesson = Lesson(
        course_id=course_id,
        title=lesson.title,
        description=lesson.description,
        video_url=lesson.video_url,
        pdf_url=lesson.pdf_url,
        order=lesson.order,
        duration_minutes=lesson.duration_minutes
    )
    db.add(new_lesson)
    db.commit()
    db.refresh(new_lesson)
    return new_lesson

# Everyone views lessons of a course
@router.get("/{course_id}/lessons", response_model=list[LessonResponse])
def get_lessons(
    course_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_employee)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return db.query(Lesson).filter(
        Lesson.course_id == course_id
    ).order_by(Lesson.order).all()

# HR admin updates lesson
@router.put("/lessons/{lesson_id}", response_model=LessonResponse)
def update_lesson(
    lesson_id: int,
    lesson_update: LessonUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if lesson_update.title:
        lesson.title = lesson_update.title
    if lesson_update.description:
        lesson.description = lesson_update.description
    if lesson_update.video_url:
        lesson.video_url = lesson_update.video_url
    if lesson_update.pdf_url:
        lesson.pdf_url = lesson_update.pdf_url
    if lesson_update.order is not None:
        lesson.order = lesson_update.order
    if lesson_update.duration_minutes:
        lesson.duration_minutes = lesson_update.duration_minutes
    db.commit()
    db.refresh(lesson)
    return lesson

# HR admin deletes lesson
@router.delete("/lessons/{lesson_id}")
def delete_lesson(
    lesson_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    db.delete(lesson)
    db.commit()
    return {"message": f"Lesson '{lesson.title}' deleted"}