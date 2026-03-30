from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Boolean, Text, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum

class RoleEnum(str, enum.Enum):
    super_admin = "super_admin"
    hr_admin = "hr_admin"
    manager = "manager"
    employee = "employee"

class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    employees = relationship("Employee", back_populates="department")

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.employee)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    is_pending = Column(Boolean, default=False)  # True = awaiting role assignment by admin
    created_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department", back_populates="employees")
    enrollments = relationship("Enrollment", back_populates="employee", foreign_keys="Enrollment.employee_id")
    sent_messages = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id")
    received_messages = relationship("Message", back_populates="receiver", foreign_keys="Message.receiver_id")
    certificates = relationship("Certificate", back_populates="employee")
    reset_tokens = relationship("PasswordResetToken", back_populates="employee")
    live_class_enrollments = relationship("LiveClassEnrollment", back_populates="employee", foreign_keys="LiveClassEnrollment.employee_id")

class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    category = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    lessons = relationship("Lesson", back_populates="course", cascade="all, delete")
    creator = relationship("Employee", foreign_keys=[created_by])
    enrollments = relationship("Enrollment", back_populates="course")
    assignments = relationship("Assignment", back_populates="course", cascade="all, delete")
    certificates = relationship("Certificate", back_populates="course")

class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    video_url = Column(String, nullable=True)
    pdf_url = Column(String, nullable=True)
    order = Column(Integer, default=0)
    duration_minutes = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", back_populates="lessons")
    quiz = relationship("Quiz", back_populates="lesson", uselist=False, cascade="all, delete")
    progress_records = relationship("LessonProgress", back_populates="lesson")
    doubts = relationship("Doubt", back_populates="lesson", cascade="all, delete")

class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    enrolled_by = Column(Integer, ForeignKey("employees.id"), nullable=True)  # admin who assigned
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    progress_pct = Column(Float, default=0.0)

    employee = relationship("Employee", back_populates="enrollments", foreign_keys=[employee_id])
    course = relationship("Course", back_populates="enrollments")
    lesson_progress = relationship("LessonProgress", back_populates="enrollment", cascade="all, delete")

class LessonProgress(Base):
    __tablename__ = "lesson_progress"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(Integer, ForeignKey("enrollments.id"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=False)
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    watched_seconds = Column(Integer, default=0)

    enrollment = relationship("Enrollment", back_populates="lesson_progress")
    lesson = relationship("Lesson", back_populates="progress_records")

class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=False, unique=True)
    title = Column(String, nullable=False)
    pass_score = Column(Integer, default=70)
    created_at = Column(DateTime, default=datetime.utcnow)

    lesson = relationship("Lesson", back_populates="quiz")
    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete")
    attempts = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete")

class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    text = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)  # list of strings
    correct_index = Column(Integer, nullable=False)
    order = Column(Integer, default=0)

    quiz = relationship("Quiz", back_populates="questions")

class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    answers = Column(JSON, nullable=False)  # {question_id: selected_index}
    score = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False)
    attempted_at = Column(DateTime, default=datetime.utcnow)

    quiz = relationship("Quiz", back_populates="attempts")

class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(DateTime, nullable=True)
    points = Column(Integer, default=100)
    assignment_type = Column(String, default="exercise")  # exercise, quiz, project, assessment, report
    document_url = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", back_populates="assignments")
    submissions = relationship("AssignmentSubmission", back_populates="assignment", cascade="all, delete")

class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    submission_text = Column(Text, nullable=True)
    file_url = Column(String, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    grade = Column(Integer, nullable=True)
    feedback = Column(Text, nullable=True)
    graded_at = Column(DateTime, nullable=True)
    graded_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    status = Column(String, default="submitted")  # submitted, graded

    assignment = relationship("Assignment", back_populates="submissions")

class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    credential_id = Column(String, unique=True, nullable=False)
    issued_at = Column(DateTime, default=datetime.utcnow)
    pdf_url = Column(String, nullable=True)

    employee = relationship("Employee", back_populates="certificates")
    course = relationship("Course", back_populates="certificates")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=datetime.utcnow)

    sender = relationship("Employee", back_populates="sent_messages", foreign_keys=[sender_id])
    receiver = relationship("Employee", back_populates="received_messages", foreign_keys=[receiver_id])

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee", back_populates="reset_tokens")

class Doubt(Base):
    __tablename__ = "doubts"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=False)
    asked_by = Column(Integer, ForeignKey("employees.id"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    answered_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    answered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    lesson = relationship("Lesson", back_populates="doubts")
    asker = relationship("Employee", foreign_keys=[asked_by])
    answerer = relationship("Employee", foreign_keys=[answered_by])

class LiveClass(Base):
    __tablename__ = "live_classes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    instructor = Column(String, nullable=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)   # course-wise targeting
    date = Column(String, nullable=True)          # e.g. "2026-03-22"
    time = Column(String, nullable=True)          # e.g. "10:00 AM"
    duration = Column(Integer, default=60)
    capacity = Column(Integer, default=30)
    enrolled = Column(Integer, default=0)
    status = Column(String, default="upcoming")   # upcoming, live, ended
    meet_title = Column(String, nullable=True)    # "Zoom", "Google Meet", "Teams", etc.
    meet_url = Column(String, nullable=True)      # full meeting link
    audience_type = Column(String, default="all") # all, course, selected
    created_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", foreign_keys=[course_id])
    creator = relationship("Employee", foreign_keys=[created_by])
    enrollments = relationship("LiveClassEnrollment", back_populates="live_class", cascade="all, delete")
    audience = relationship("LiveClassAudience", back_populates="live_class", cascade="all, delete")

class LiveClassEnrollment(Base):
    __tablename__ = "live_class_enrollments"

    id = Column(Integer, primary_key=True, index=True)
    live_class_id = Column(Integer, ForeignKey("live_classes.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    enrolled_at = Column(DateTime, default=datetime.utcnow)

    live_class = relationship("LiveClass", back_populates="enrollments")
    employee = relationship("Employee", foreign_keys=[employee_id])

class LiveClassAudience(Base):
    """Stores selected employees when audience_type='selected'"""
    __tablename__ = "live_class_audience"

    id = Column(Integer, primary_key=True, index=True)
    live_class_id = Column(Integer, ForeignKey("live_classes.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)

    live_class = relationship("LiveClass", back_populates="audience")
    employee = relationship("Employee", foreign_keys=[employee_id])


class SmtpConfig(Base):
    """Stores SMTP settings configured by super admin via the UI.
    Only one row is ever used (id=1). If present, these values override env vars."""
    __tablename__ = "smtp_config"

    id = Column(Integer, primary_key=True, index=True, default=1)
    smtp_host = Column(String, nullable=False)
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String, nullable=False)
    smtp_pass = Column(String, nullable=False)          # stored as-is (consider encrypting in prod)
    from_email = Column(String, nullable=True)          # defaults to smtp_user if blank
    from_name = Column(String, default="Bryte LMS")
    use_tls = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)