from pydantic import BaseModel, EmailStr, field_validator, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.models import RoleEnum
import re

# ── Shared validation helpers ─────────────────────────────────────────────────
_HTML_RE = re.compile(r"<[^>]*>|javascript:", re.IGNORECASE)
_ALLOWED_ASSIGNMENT_TYPES = {"exercise", "quiz", "project", "assessment", "report"}
_ALLOWED_AUDIENCE_TYPES   = {"all", "course", "selected"}
_ALLOWED_CLASS_STATUSES   = {"upcoming", "live", "ended"}


def _strip_html(value: str) -> str:
    """Raise if the string contains HTML tags or JS URLs."""
    if _HTML_RE.search(value):
        raise ValueError("HTML / script content is not allowed")
    return value


def _check_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(password) > 128:
        raise ValueError("Password must be at most 128 characters")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one digit")
    return password


# ── Employee schemas ──────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be blank")
        return _strip_html(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _check_password_strength(v)


class EmployeeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str
    role: RoleEnum = RoleEnum.employee
    department_id: Optional[int] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _strip_html(v.strip())

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _check_password_strength(v)


class EmployeeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    role: Optional[RoleEnum] = None
    department_id: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _strip_html(v.strip())


class EmployeeResponse(BaseModel):
    id: int
    name: str
    email: str
    role: RoleEnum
    is_active: bool
    is_pending: bool = False
    department_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Auth schemas ──────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    role: str
    name: str
    id: int


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new(cls, v: str) -> str:
        return _check_password_strength(v)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=256)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new(cls, v: str) -> str:
        return _check_password_strength(v)


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _strip_html(v.strip())


# ── Department schemas ────────────────────────────────────────────────────────
class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _strip_html(v.strip())


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _strip_html(v.strip())


class DepartmentResponse(BaseModel):
    id: int
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


class DepartmentWithEmployees(BaseModel):
    id: int
    name: str
    created_at: datetime
    employees: List[EmployeeResponse] = []

    class Config:
        from_attributes = True


# ── Lesson schemas ────────────────────────────────────────────────────────────
class LessonCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    video_url: Optional[str] = Field(None, max_length=2000)
    pdf_url: Optional[str] = Field(None, max_length=2000)
    order: Optional[int] = Field(0, ge=0)
    duration_minutes: Optional[int] = Field(None, ge=0, le=1440)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return _strip_html(v.strip())


class LessonUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    video_url: Optional[str] = Field(None, max_length=2000)
    pdf_url: Optional[str] = Field(None, max_length=2000)
    order: Optional[int] = Field(None, ge=0)
    duration_minutes: Optional[int] = Field(None, ge=0, le=1440)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _strip_html(v.strip())


class LessonResponse(BaseModel):
    id: int
    course_id: int
    title: str
    description: Optional[str]
    video_url: Optional[str]
    pdf_url: Optional[str]
    order: int
    duration_minutes: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Course schemas ────────────────────────────────────────────────────────────
class CourseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    thumbnail_url: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=100)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return _strip_html(v.strip())


class CourseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    thumbnail_url: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=100)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _strip_html(v.strip())


class CourseResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    thumbnail_url: Optional[str]
    category: Optional[str]
    is_published: bool
    created_at: datetime
    lesson_count: Optional[int] = 0

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_count(cls, obj):
        data = cls.model_validate(obj)
        data.lesson_count = len(obj.lessons) if hasattr(obj, 'lessons') and obj.lessons else 0
        return data


class CourseWithLessons(BaseModel):
    id: int
    title: str
    description: Optional[str]
    thumbnail_url: Optional[str]
    category: Optional[str]
    is_published: bool
    created_at: datetime
    lessons: List[LessonResponse] = []

    class Config:
        from_attributes = True


# ── Enrollment schemas ────────────────────────────────────────────────────────
class EnrollRequest(BaseModel):
    course_id: int = Field(..., gt=0)


class AssignCourseRequest(BaseModel):
    employee_id: int = Field(..., gt=0)
    course_id: int = Field(..., gt=0)


class EnrollmentResponse(BaseModel):
    id: int
    employee_id: int
    course_id: int
    enrolled_at: datetime
    completed: bool
    completed_at: Optional[datetime]
    progress_pct: float
    course: Optional[CourseWithLessons] = None

    class Config:
        from_attributes = True


# ── Progress schemas ──────────────────────────────────────────────────────────
class LessonProgressUpdate(BaseModel):
    lesson_id: int = Field(..., gt=0)
    watched_seconds: Optional[int] = Field(0, ge=0)
    completed: Optional[bool] = False


class LessonProgressResponse(BaseModel):
    id: int
    enrollment_id: int
    lesson_id: int
    completed: bool
    completed_at: Optional[datetime]
    watched_seconds: int

    class Config:
        from_attributes = True


# ── Quiz schemas ──────────────────────────────────────────────────────────────
class QuizQuestionCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    options: List[str] = Field(..., min_length=2, max_length=10)
    correct_index: int = Field(..., ge=0)
    order: Optional[int] = Field(0, ge=0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return _strip_html(v.strip())

    @field_validator("correct_index")
    @classmethod
    def validate_correct_index(cls, v: int, info: Any) -> int:
        # We can't cross-validate with options here easily; backend route validates
        return v


class QuizCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    pass_score: Optional[int] = Field(70, ge=1, le=100)
    questions: List[QuizQuestionCreate] = Field(..., min_length=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return _strip_html(v.strip())


class QuizQuestionResponse(BaseModel):
    id: int
    quiz_id: int
    text: str
    options: List[str]
    correct_index: int
    order: int

    class Config:
        from_attributes = True


class QuizResponse(BaseModel):
    id: int
    lesson_id: int
    title: str
    pass_score: int
    created_at: datetime
    questions: List[QuizQuestionResponse] = []

    class Config:
        from_attributes = True


class QuizSubmitRequest(BaseModel):
    answers: Dict[int, int] = Field(..., description="question_id → selected_option_index")

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, v: Dict[int, int]) -> Dict[int, int]:
        if len(v) > 200:
            raise ValueError("Too many answers submitted")
        for qid, ans in v.items():
            if not isinstance(qid, int) or qid <= 0:
                raise ValueError(f"Invalid question id: {qid}")
            if not isinstance(ans, int) or ans < 0 or ans > 20:
                raise ValueError(f"Invalid answer index: {ans}")
        return v


class QuizAttemptResponse(BaseModel):
    id: int
    quiz_id: int
    employee_id: int
    score: int
    passed: bool
    attempted_at: datetime

    class Config:
        from_attributes = True


# ── Assignment schemas ────────────────────────────────────────────────────────
class AssignmentCreate(BaseModel):
    course_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    due_date: Optional[datetime] = None
    points: Optional[int] = Field(100, ge=0, le=10000)
    assignment_type: Optional[str] = Field("exercise", max_length=50)
    document_url: Optional[str] = Field(None, max_length=2000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return _strip_html(v.strip())

    @field_validator("assignment_type")
    @classmethod
    def validate_type(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in _ALLOWED_ASSIGNMENT_TYPES:
            raise ValueError(f"assignment_type must be one of {_ALLOWED_ASSIGNMENT_TYPES}")
        return v


class AssignmentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    due_date: Optional[datetime] = None
    points: Optional[int] = Field(None, ge=0, le=10000)
    document_url: Optional[str] = Field(None, max_length=2000)
    assignment_type: Optional[str] = Field(None, max_length=50)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _strip_html(v.strip())

    @field_validator("assignment_type")
    @classmethod
    def validate_type(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in _ALLOWED_ASSIGNMENT_TYPES:
            raise ValueError(f"assignment_type must be one of {_ALLOWED_ASSIGNMENT_TYPES}")
        return v


class AssignmentResponse(BaseModel):
    id: int
    course_id: int
    title: str
    description: Optional[str]
    due_date: Optional[datetime]
    points: int
    assignment_type: str
    document_url: Optional[str]
    created_at: datetime
    course: Optional[CourseResponse] = None

    class Config:
        from_attributes = True


class SubmissionCreate(BaseModel):
    submission_text: Optional[str] = Field(None, max_length=20000)

    @field_validator("submission_text")
    @classmethod
    def validate_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _strip_html(v)


class GradeSubmissionRequest(BaseModel):
    grade: int = Field(..., ge=0, le=100)
    feedback: Optional[str] = Field(None, max_length=2000)

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _strip_html(v)


class SubmissionResponse(BaseModel):
    id: int
    assignment_id: int
    employee_id: int
    submission_text: Optional[str]
    submitted_at: datetime
    grade: Optional[int]
    feedback: Optional[str]
    status: str

    class Config:
        from_attributes = True


# ── Certificate schemas ───────────────────────────────────────────────────────
class CertificateResponse(BaseModel):
    id: int
    employee_id: int
    course_id: int
    credential_id: str
    issued_at: datetime
    pdf_url: Optional[str]
    course: Optional[CourseResponse] = None

    class Config:
        from_attributes = True


# ── Message schemas ───────────────────────────────────────────────────────────
class MessageCreate(BaseModel):
    receiver_id: int = Field(..., gt=0)
    content: str = Field(..., min_length=1, max_length=5000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message content cannot be blank")
        return _strip_html(v)


class MessageResponse(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    content: str
    is_read: bool
    sent_at: datetime
    sender: Optional[EmployeeResponse] = None
    receiver: Optional[EmployeeResponse] = None

    class Config:
        from_attributes = True


# ── Doubt schemas ─────────────────────────────────────────────────────────────
class DoubtCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        return _strip_html(v.strip())


class DoubtAnswerRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=5000)

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: str) -> str:
        return _strip_html(v.strip())


class DoubtResponse(BaseModel):
    id: int
    lesson_id: int
    asked_by: int
    question: str
    answer: Optional[str]
    answered_by: Optional[int]
    answered_at: Optional[datetime]
    created_at: datetime
    asker: Optional[EmployeeResponse] = None
    answerer: Optional[EmployeeResponse] = None

    class Config:
        from_attributes = True


# ── Live Class schemas ────────────────────────────────────────────────────────
class LiveClassCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    instructor: Optional[str] = Field(None, max_length=100)
    course_id: Optional[int] = Field(None, gt=0)
    date: Optional[str] = Field(None, max_length=20)
    time: Optional[str] = Field(None, max_length=20)
    duration: Optional[int] = Field(60, ge=1, le=480)
    capacity: Optional[int] = Field(30, ge=1, le=10000)
    status: Optional[str] = Field("upcoming", max_length=20)
    meet_title: Optional[str] = Field(None, max_length=100)
    meet_url: Optional[str] = Field(None, max_length=2000)
    audience_type: Optional[str] = Field("all", max_length=20)
    employee_ids: Optional[List[int]] = []

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return _strip_html(v.strip())

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in _ALLOWED_CLASS_STATUSES:
            raise ValueError(f"status must be one of {_ALLOWED_CLASS_STATUSES}")
        return v

    @field_validator("audience_type")
    @classmethod
    def validate_audience(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in _ALLOWED_AUDIENCE_TYPES:
            raise ValueError(f"audience_type must be one of {_ALLOWED_AUDIENCE_TYPES}")
        return v


class LiveClassUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    instructor: Optional[str] = Field(None, max_length=100)
    course_id: Optional[int] = None
    date: Optional[str] = Field(None, max_length=20)
    time: Optional[str] = Field(None, max_length=20)
    duration: Optional[int] = Field(None, ge=1, le=480)
    capacity: Optional[int] = Field(None, ge=1, le=10000)
    status: Optional[str] = Field(None, max_length=20)
    meet_title: Optional[str] = Field(None, max_length=100)
    meet_url: Optional[str] = Field(None, max_length=2000)
    audience_type: Optional[str] = Field(None, max_length=20)
    employee_ids: Optional[List[int]] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _strip_html(v.strip())

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in _ALLOWED_CLASS_STATUSES:
            raise ValueError(f"status must be one of {_ALLOWED_CLASS_STATUSES}")
        return v

    @field_validator("audience_type")
    @classmethod
    def validate_audience(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in _ALLOWED_AUDIENCE_TYPES:
            raise ValueError(f"audience_type must be one of {_ALLOWED_AUDIENCE_TYPES}")
        return v


class LiveClassResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    instructor: Optional[str]
    course_id: Optional[int]
    date: Optional[str]
    time: Optional[str]
    duration: int
    capacity: int
    enrolled: int
    status: str
    meet_title: Optional[str]
    meet_url: Optional[str]
    audience_type: str
    created_at: datetime
    created_by: Optional[int] = None

    class Config:
        from_attributes = True


class LiveClassEnrollmentResponse(BaseModel):
    id: int
    live_class_id: int
    employee_id: int
    enrolled_at: datetime

    class Config:
        from_attributes = True


# ── SMTP Config schemas ───────────────────────────────────────────────────────
class SmtpConfigCreate(BaseModel):
    smtp_host: str = Field(..., min_length=1, max_length=253)
    smtp_port: int = Field(587, ge=1, le=65535)
    smtp_user: str = Field(..., min_length=1, max_length=254)
    smtp_pass: str = Field(..., min_length=1, max_length=256)
    from_email: Optional[str] = None
    from_name: str = Field("Bryte LMS", max_length=100)
    use_tls: bool = True
    is_active: bool = True


class SmtpConfigUpdate(BaseModel):
    smtp_host: Optional[str] = Field(None, min_length=1, max_length=253)
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_user: Optional[str] = Field(None, min_length=1, max_length=254)
    smtp_pass: Optional[str] = Field(None, min_length=1, max_length=256)
    from_email: Optional[str] = None
    from_name: Optional[str] = Field(None, max_length=100)
    use_tls: Optional[bool] = None
    is_active: Optional[bool] = None


class SmtpConfigResponse(BaseModel):
    id: int
    smtp_host: str
    smtp_port: int
    smtp_user: str
    # smtp_pass intentionally omitted from response to avoid credential leakage
    from_email: Optional[str]
    from_name: str
    use_tls: bool
    is_active: bool
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
