from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Lesson, Course, Assignment
from app.storage import upload_file, delete_file, get_signed_url
from app.dependencies import require_hr_admin, require_employee

router = APIRouter(prefix="/lessons", tags=["Uploads"])

ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"]
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB

# Upload course thumbnail
course_thumb_router = APIRouter(prefix="/courses", tags=["Courses"])

@course_thumb_router.post("/{course_id}/upload-thumbnail")
async def upload_thumbnail(
    course_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: jpg, png, webp, gif")
    file_bytes = await file.read()
    if len(file_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image too large. Max is 5MB")
    thumbnail_url = upload_file(file_bytes, file.filename, file.content_type)
    course.thumbnail_url = thumbnail_url
    db.commit()
    db.refresh(course)
    return {"message": "Thumbnail uploaded successfully", "thumbnail_url": thumbnail_url}


ALLOWED_VIDEO_TYPES = ["video/mp4", "video/avi", "video/quicktime", "video/x-matroska"]
ALLOWED_PDF_TYPES = ["application/pdf"]
MAX_VIDEO_SIZE = 50 * 1024 * 1024   # 50MB
MAX_PDF_SIZE = 10 * 1024 * 1024     # 10MB

# Upload video
@router.post("/{lesson_id}/upload-video")
async def upload_video(
    lesson_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    if file.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Allowed: mp4, avi, mov, mkv"
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_VIDEO_SIZE:
        raise HTTPException(
            status_code=400,
            detail="Video too large. Max size is 50MB"
        )

    if lesson.video_url:
        delete_file(lesson.video_url)

    video_url = upload_file(file_bytes, file.filename, file.content_type)
    lesson.video_url = video_url
    db.commit()
    db.refresh(lesson)

    return {
        "message": "Video uploaded successfully ✅",
        "video_url": video_url,
        "lesson_id": lesson_id,
        "file_size_mb": round(len(file_bytes) / (1024 * 1024), 2)
    }

# Upload PDF
@router.post("/{lesson_id}/upload-pdf")
async def upload_pdf(
    lesson_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    if file.content_type not in ALLOWED_PDF_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF allowed"
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400,
            detail="PDF too large. Max size is 10MB"
        )

    if lesson.pdf_url:
        delete_file(lesson.pdf_url)

    pdf_url = upload_file(file_bytes, file.filename, file.content_type)
    lesson.pdf_url = pdf_url
    db.commit()
    db.refresh(lesson)

    return {
        "message": "PDF uploaded successfully ✅",
        "pdf_url": pdf_url,
        "lesson_id": lesson_id,
        "file_size_mb": round(len(file_bytes) / (1024 * 1024), 2)
    }

# Delete video
@router.delete("/{lesson_id}/video")
def delete_video(
    lesson_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not lesson.video_url:
        raise HTTPException(status_code=404, detail="No video found")
    delete_file(lesson.video_url)
    lesson.video_url = None
    db.commit()
    return {"message": "Video deleted successfully"}

# Delete PDF
@router.delete("/{lesson_id}/pdf")
def delete_pdf(
    lesson_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not lesson.pdf_url:
        raise HTTPException(status_code=404, detail="No PDF found")
    delete_file(lesson.pdf_url)
    lesson.pdf_url = None
    db.commit()
    return {"message": "PDF deleted successfully"}

from app.storage import upload_file, delete_file, get_signed_url  # ← add get_signed_url

# Get video signed URL for lesson
@router.get("/{lesson_id}/video")
def get_video(
    lesson_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_employee)  # all employees can view
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not lesson.video_url:
        raise HTTPException(status_code=404, detail="No video found for this lesson")
    
    signed_url = get_signed_url(lesson.video_url)
    return {
        "lesson_id": lesson_id,
        "lesson_title": lesson.title,
        "video_url": signed_url,
        "expires_in": "1 hour"
    }

# Get PDF signed URL for lesson
@router.get("/{lesson_id}/pdf")
def get_pdf(
    lesson_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_employee)  # all employees can view
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not lesson.pdf_url:
        raise HTTPException(status_code=404, detail="No PDF found for this lesson")

    signed_url = get_signed_url(lesson.pdf_url)
    return {
        "lesson_id": lesson_id,
        "lesson_title": lesson.title,
        "pdf_url": signed_url,
        "expires_in": "1 hour"
    }

# Get all files for a lesson
@router.get("/{lesson_id}/files")
def get_lesson_files(
    lesson_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_employee)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    return {
        "lesson_id": lesson_id,
        "lesson_title": lesson.title,
        "video_url": get_signed_url(lesson.video_url) if lesson.video_url else None,
        "pdf_url": get_signed_url(lesson.pdf_url) if lesson.pdf_url else None
    }

@router.post("/assignments/{assignment_id}/document")
async def upload_assignment_document(
    assignment_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin)
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Document too large. Max size is 20MB")

    if assignment.document_url:
        delete_file(assignment.document_url)

    doc_url = upload_file(file_bytes, file.filename, file.content_type)
    assignment.document_url = doc_url
    db.commit()
    db.refresh(assignment)

    return {
        "message": "Document uploaded successfully ✅",
        "document_url": get_signed_url(doc_url),
        "assignment_id": assignment_id
    }