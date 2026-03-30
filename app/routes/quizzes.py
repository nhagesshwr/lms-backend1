from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Quiz, QuizQuestion, QuizAttempt, Lesson, Employee, Enrollment
from app.schemas import QuizCreate, QuizResponse, QuizSubmitRequest, QuizAttemptResponse
from app.dependencies import require_employee, require_hr_admin

router = APIRouter(prefix="/quizzes", tags=["Quizzes"])


@router.post("/lesson/{lesson_id}", response_model=QuizResponse)
def create_quiz(
    lesson_id: int,
    data: QuizCreate,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin),
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    existing = db.query(Quiz).filter(Quiz.lesson_id == lesson_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Quiz already exists for this lesson")

    # Validate each question's correct_index is within its options list
    for i, q in enumerate(data.questions):
        if q.correct_index >= len(q.options):
            raise HTTPException(
                status_code=400,
                detail=f"Question {i + 1}: correct_index {q.correct_index} is out of range "
                       f"(only {len(q.options)} options provided)",
            )

    quiz = Quiz(lesson_id=lesson_id, title=data.title, pass_score=data.pass_score)
    db.add(quiz)
    db.flush()

    for i, q in enumerate(data.questions):
        question = QuizQuestion(
            quiz_id=quiz.id,
            text=q.text,
            options=q.options,
            correct_index=q.correct_index,
            order=q.order if q.order is not None else i,
        )
        db.add(question)

    db.commit()
    db.refresh(quiz)
    return quiz


@router.get("/lesson/{lesson_id}", response_model=QuizResponse)
def get_quiz_by_lesson(
    lesson_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_employee),
):
    quiz = db.query(Quiz).options(
        joinedload(Quiz.questions)
    ).filter(Quiz.lesson_id == lesson_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="No quiz found for this lesson")
    return quiz


@router.post("/{quiz_id}/submit", response_model=QuizAttemptResponse)
def submit_quiz(
    quiz_id: int,
    data: QuizSubmitRequest,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee),
):
    quiz = db.query(Quiz).options(joinedload(Quiz.questions)).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    # Validate submitted question IDs belong to this quiz
    valid_question_ids = {q.id for q in quiz.questions}
    for qid in data.answers:
        if qid not in valid_question_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Question {qid} does not belong to this quiz",
            )

    # Verify the answer index is within options range for each question
    question_map = {q.id: q for q in quiz.questions}
    for qid, ans_idx in data.answers.items():
        q = question_map[qid]
        if ans_idx >= len(q.options):
            raise HTTPException(
                status_code=400,
                detail=f"Answer index {ans_idx} is out of range for question {qid}",
            )

    # Verify employee is enrolled in the course containing this lesson
    lesson = db.query(Lesson).filter(Lesson.id == quiz.lesson_id).first()
    if lesson:
        enrollment = db.query(Enrollment).filter(
            Enrollment.employee_id == current.id,
            Enrollment.course_id == lesson.course_id,
        ).first()
        if not enrollment:
            raise HTTPException(
                status_code=403,
                detail="You must be enrolled in this course to take the quiz",
            )

    correct = 0
    total = len(quiz.questions)
    for question in quiz.questions:
        submitted = data.answers.get(question.id)
        if submitted is not None and submitted == question.correct_index:
            correct += 1

    score = round((correct / total) * 100) if total > 0 else 0
    passed = score >= quiz.pass_score

    attempt = QuizAttempt(
        quiz_id=quiz_id,
        employee_id=current.id,
        answers={str(k): v for k, v in data.answers.items()},
        score=score,
        passed=passed,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


@router.get("/{quiz_id}/attempts", response_model=list[QuizAttemptResponse])
def get_my_attempts(
    quiz_id: int,
    db: Session = Depends(get_db),
    current: Employee = Depends(require_employee),
):
    return db.query(QuizAttempt).filter(
        QuizAttempt.quiz_id == quiz_id,
        QuizAttempt.employee_id == current.id,
    ).order_by(QuizAttempt.attempted_at.desc()).all()


@router.delete("/lesson/{lesson_id}")
def delete_quiz(
    lesson_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_hr_admin),
):
    quiz = db.query(Quiz).filter(Quiz.lesson_id == lesson_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    db.delete(quiz)
    db.commit()
    return {"message": "Quiz deleted"}
