from dotenv import load_dotenv
load_dotenv()

from storage import upload_file_to_storage, delete_file_from_storage
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi import UploadFile, File
from fastapi.staticfiles import StaticFiles
from auth import hash_password, verify_password, create_access_token, get_current_user, require_admin, require_super_admin
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from datetime import datetime, timezone, timedelta
import shutil
import os
import models
import schemas
import sentry_sdk

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=1.0,
    environment="development",
)


app = FastAPI()

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://fantastical-blob-frontend.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def read_root():
    return {"message": "Backend is alive"}

@app.post ("/users", response_model = schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    existing = db.query(models.User).filter(models.User.email == user.email, models.User.deleted_at.is_(None)).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="A user with this email already exists")

    new_user = models.User(
        name = user.name,
        jersey_number = user.jersey_number,
        position = user.position,
        year = user.year,
        email = user.email,
        birthday = user.birthday,
        is_offense = user.is_offense,
        is_defense =user.is_defense,
        is_special_teams = user.is_special_teams,
        role=user.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.get("/users", response_model = list[schemas.UserResponse])
def get_users(db: Session = Depends(get_db), current_user: models.User = Depends (require_admin)):
    return db.query(models.User).filter(models.User.deleted_at.is_(None)).all()

@app.put("/users/{user_id}", response_model = schemas.UserResponse)
def update_user(user_id: int, updated_user: schemas.UserUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if user is None:
        raise HTTPException(status_code=404, detail= "User not found")

    update_data = updated_user.model_dump(exclude_unset=True)

    if "role" in update_data and user.role == "admin" and update_data["role"] != "admin":
        if not current_user.is_super_admin:
            raise HTTPException(status_code=403, detail="Only super admins can demote another admin")

    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user

@app.put("/users/{user_id}/super-admin")
def set_super_admin(user_id: int, is_super_admin: bool, db: Session = Depends(get_db), current_user: models.User = Depends(require_super_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "admin":
        raise HTTPException(status_code=400, detail="User is not an admin")

    
    log_audit_action(db, current_user.id, f"set_super_admin_{is_super_admin}", "User", user_id)
    user.is_super_admin = is_super_admin
    db.commit()
    return {"message": f"Super admin status set to {is_super_admin}"}

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id, models.User.deleted_at.is_(None)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == "admin" and not current_user.is_super_admin:
        raise HTTPException(status_code=403, detail="Only super admins can delete another admin")

    user.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "User archived"}

@app.post("/claim-account", response_model=schemas.Token)
def claim_account(claim: schemas.ClaimAccount, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == claim.email, models.User.deleted_at.is_(None)).first()

    if user is None:
        raise HTTPException(status_code=404, detail="No account found with this email")

    if user.password_hash is not None:
        raise HTTPException(status_code=400, detail="This account has already been claimed")

    user.password_hash = hash_password(claim.password)
    db.commit()

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/login", response_model=schemas.Token)
def login(credentials: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email, models.User.deleted_at.is_(None)).first()

    if user is None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me", response_model=schemas.UserResponse)
def read_own_profile(current_user: models.User = Depends(get_current_user)):
    return current_user

# ----- Assessments -----

@app.post("/assessments", response_model=schemas.AssessmentResponse)
def create_assessment(assessment: schemas.AssessmentCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    new_assessment = models.Assessment(
        title=assessment.title,
        description=assessment.description,
        created_by=current_user.id,
        is_public=assessment.is_public,
        assessment_type=assessment.assessment_type
    )
    db.add(new_assessment)
    db.commit()
    db.refresh(new_assessment)
    return new_assessment

    for a in assessment.assignments:
        db.add(models.AssessmentAssignment(assessment_id=new_assessment.id, assignment_type=a.assignment_type, value=a.value))
    db.commit()
    db.refresh(new_assessment)
    return new_assessment

@app.put("/assessments/{assessment_id}", response_model=schemas.AssessmentResponse)
def update_assessment(assessment_id: int, updated: schemas.AssessmentUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    assessment = db.query(models.Assessment).filter(models.Assessment.id == assessment_id, models.Assessment.deleted_at.is_(None)).first()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    update_data = updated.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(assessment, key, value)

    db.commit()
    db.refresh(assessment)
    return assessment

@app.get("/assessments", response_model=list[schemas.AssessmentResponse])
def get_assessments(assessment_type: str | None = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    query = db.query(models.Assessment).filter(models.Assessment.deleted_at.is_(None))
    if assessment_type:
        query = query.filter(models.Assessment.assessment_type == assessment_type)
    all_assessments = query.all()
    return [a for a in all_assessments if user_can_see_assessment(a, current_user, db)]


@app.get("/assessments/{assessment_id}", response_model=schemas.AssessmentResponse)
def get_assessment(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    assessment = db.query(models.Assessment).filter(models.Assessment.id == assessment_id, models.Assessment.deleted_at.is_(None)).first()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if not user_can_see_assessment(assessment, current_user, db):
        raise HTTPException(status_code=403, detail="Not authorized to view this assessment")
    return assessment

@app.get("/assessments/{assessment_id}/my-latest-attempt", response_model=schemas.AttemptResponse | None)
def get_my_latest_attempt(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .filter(models.AssessmentAttempt.user_id == current_user.id)
        .order_by(models.AssessmentAttempt.submitted_at.desc())
        .first()
    )


@app.get("/assessments/{assessment_id}/users/{user_id}/latest-attempt", response_model=schemas.AttemptResponse | None)
def get_user_latest_attempt(assessment_id: int, user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    return (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .filter(models.AssessmentAttempt.user_id == user_id)
        .order_by(models.AssessmentAttempt.submitted_at.desc())
        .first()
    )


@app.get("/assessments/{assessment_id}/my-attempts", response_model=list[schemas.AttemptResponse])
def get_my_attempts_for_assessment(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .filter(models.AssessmentAttempt.user_id == current_user.id)
        .order_by(models.AssessmentAttempt.submitted_at)
        .all()
    )


@app.get("/me/attempts-across-assessments", response_model=list[schemas.AttemptResponse])
def get_my_attempts_across_assessments(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.user_id == current_user.id)
        .order_by(models.AssessmentAttempt.submitted_at)
        .all()
    )

@app.get("/assessments/{assessment_id}/users/{user_id}/attempt-detail")
def get_user_attempt_detail(assessment_id: int, user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    attempt = (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .filter(models.AssessmentAttempt.user_id == user_id)
        .order_by(models.AssessmentAttempt.submitted_at.desc())
        .first()
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="No attempt found for this player")

    responses = db.query(models.Response).filter(models.Response.attempt_id == attempt.id).all()

    questions = db.query(models.Question).filter(models.Question.assessment_id == assessment_id).all()
    question_map = {q.id: q for q in questions}

    answer_details = []
    for r in responses:
        question = question_map.get(r.question_id)
        if question is None:
            continue

        answer_label = r.answer_text
        if r.answer_value is not None:
            option = db.query(models.AnswerOption).filter(
                models.AnswerOption.question_id == r.question_id,
                models.AnswerOption.value == r.answer_value
            ).first()
            answer_label = option.label if option else str(r.answer_value)

        answer_details.append({
            "question_id": question.id,
            "question_text": question.question_text,
            "answer_label": answer_label,
            "time_taken_seconds": r.time_taken_seconds
        })

    return {
        "attempt_id": attempt.id,
        "total_score": attempt.total_score,
        "level": attempt.level,
        "duration_seconds": attempt.duration_seconds,
        "submitted_at": attempt.submitted_at,
        "answers": answer_details
    }

@app.get("/analytics/filtered-scores")
def get_filtered_scores(
    assessment_id: int,
    group_by: str,  # "position", "year", "unit"
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    latest_attempts = {}
    attempts = (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .order_by(models.AssessmentAttempt.submitted_at)
        .all()
    )
    for attempt in attempts:
        latest_attempts[attempt.user_id] = attempt  # keeps latest, since ordered ascending

    grouped = {}
    for user_id, attempt in latest_attempts.items():
        user = db.query(models.User).filter(models.User.id == user_id, models.User.deleted_at.is_(None)).first()
        if user is None:
            continue

        if group_by == "position":
            key = user.position
        elif group_by == "year":
            key = f"Year {user.year}"
        elif group_by == "unit":
            keys = []
            if user.is_offense:
                keys.append("Offense")
            if user.is_defense:
                keys.append("Defense")
            if user.is_special_teams:
                keys.append("Special Teams")
            for k in keys:
                grouped.setdefault(k, []).append(attempt.total_score)
            continue
        else:
            raise HTTPException(status_code=400, detail="Invalid group_by value")

        grouped.setdefault(key, []).append(attempt.total_score)

    return [
        {
            "group": key,
            "average_score": round(sum(scores) / len(scores), 1),
            "level": score_to_level(round(sum(scores) / len(scores))),
            "player_count": len(scores)
        }
        for key, scores in grouped.items()
    ]

@app.delete("/assessments/{assessment_id}/users/{user_id}/reset")
def reset_user_assessment_data(assessment_id: int, user_id: int, reason: str | None = None, db: Session = Depends(get_db), current_user: models.User = Depends(require_super_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    attempts = (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .filter(models.AssessmentAttempt.user_id == user_id)
        .all()
    )

    if not attempts:
        raise HTTPException(status_code=404, detail="No assessment data found for this player")

    attempt_ids = [a.id for a in attempts]

    db.query(models.Response).filter(models.Response.attempt_id.in_(attempt_ids)).delete(synchronize_session=False)
    db.query(models.AssessmentAttempt).filter(models.AssessmentAttempt.id.in_(attempt_ids)).delete(synchronize_session=False)

    log_audit_action(db, current_user.id, "reset_assessment_data", "AssessmentAttempt", user_id, reason)

    db.commit()
    return {"message": f"Reset {len(attempt_ids)} attempt(s) for this player"}

# ----- Questions -----

@app.post("/assessments/{assessment_id}/questions", response_model=schemas.QuestionResponse)
def create_question(assessment_id: int, question: schemas.QuestionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    assessment = db.query(models.Assessment).filter(models.Assessment.id == assessment_id, models.Assessment.deleted_at.is_(None)).first()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    new_question = models.Question(
        assessment_id=assessment_id,
        question_text=question.question_text,
        question_type=question.question_type,
        category=question.category,
        value_points=question.value_points
    )
    db.add(new_question)
    db.commit()
    db.refresh(new_question)
    return new_question

@app.put("/questions/{question_id}", response_model=schemas.QuestionResponse)
def update_question(question_id: int, updated_question: schemas.QuestionUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    question = db.query(models.Question).filter(models.Question.id == question_id).first()

    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    update_data = updated_question.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(question, key, value)

    db.commit()
    db.refresh(question)
    return question

@app.post("/questions/{question_id}/options", response_model=schemas.AnswerOptionResponse)
def create_answer_option(question_id: int, option: schemas.AnswerOptionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    new_option = models.AnswerOption(
        question_id=question_id,
        label=option.label,
        value=option.value
    )
    db.add(new_option)
    db.commit()
    db.refresh(new_option)
    return new_option

@app.delete("/assessments/{assessment_id}")
def delete_assessment(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    assessment = db.query(models.Assessment).filter(models.Assessment.id == assessment_id, models.Assessment.deleted_at.is_(None)).first()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    assessment.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Assessment archived"}


@app.delete("/questions/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    db.query(models.AnswerOption).filter(models.AnswerOption.question_id == question_id).delete()
    db.delete(question)
    db.commit()
    return {"message": "Question deleted"}


@app.delete("/options/{option_id}")
def delete_option(option_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    option = db.query(models.AnswerOption).filter(models.AnswerOption.id == option_id).first()
    if option is None:
        raise HTTPException(status_code=404, detail="Option not found")

    db.delete(option)
    db.commit()
    return {"message": "Option deleted"}

# ----- Responses -----

@app.post("/assessments/{assessment_id}/submit", response_model=schemas.AttemptResponse)
def submit_attempt(assessment_id: int, submission: schemas.SubmitAttempt, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    assessment = db.query(models.Assessment).filter(models.Assessment.id == assessment_id, models.Assessment.deleted_at.is_(None)).first()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if not user_can_see_assessment(assessment, current_user, db):
        raise HTTPException(status_code=403, detail="Not authorized to take this assessment")

    question_ids = [q.id for q in db.query(models.Question).filter(models.Question.assessment_id == assessment_id).all()]

    total_score = 0
    for answer in submission.answers:
        if answer.question_id not in question_ids:
            continue
        question = db.query(models.Question).filter(models.Question.id == answer.question_id).first()
        if question.value_points is not None and answer.answer_value is not None:
            total_score += answer.answer_value

    level = score_to_level(total_score)

    new_attempt = models.AssessmentAttempt(
        assessment_id=assessment_id,
        user_id=current_user.id,
        total_score=total_score,
        level=level,
        duration_seconds=submission.duration_seconds
    )
    db.add(new_attempt)
    db.commit()
    db.refresh(new_attempt)

    for answer in submission.answers:
        if answer.question_id not in question_ids:
            continue
        db.add(models.Response(
            attempt_id=new_attempt.id,
            user_id=current_user.id,
            question_id=answer.question_id,
            answer_value=answer.answer_value,
            answer_text=answer.answer_text,
            time_taken_seconds=answer.time_taken_seconds
        ))
    db.commit()

    return new_attempt


# ----- Proficiency scoring -----

def calculate_proficiency(user_id: int, db: Session):
    responses = (
        db.query(models.Response)
        .join(models.Question)
        .filter(models.Response.user_id == user_id)
        .filter(models.Question.value_points.isnot(None))
        .all()
    )

    total_score = sum(r.answer_value or 0 for r in responses)

    if total_score >= 18:
        level = "Highly Advanced"
    elif total_score >= 16:
        level = "Advanced"
    elif total_score >= 13:
        level = "Intermediate"
    elif total_score >= 10:
        level = "Novice"
    else:
        level = "Not enough data"

    return {"user_id": user_id, "total_score": total_score, "level": level}


@app.get("/me/proficiency")
def get_my_proficiency(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return calculate_proficiency(current_user.id, db)


@app.get("/users/{user_id}/proficiency")
def get_user_proficiency(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return calculate_proficiency(user_id, db)


# ----- Team-wide analytics -----

@app.get("/analytics/team-average")
def get_team_average(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    latest_attempts = {}
    attempts = (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .order_by(models.AssessmentAttempt.submitted_at)
        .all()
    )
    for attempt in attempts:
        latest_attempts[attempt.user_id] = attempt

    scores = [a.total_score for a in latest_attempts.values()]
    if not scores:
        return {"average_score": 0, "level": "Not enough data", "player_count": 0}

    average = round(sum(scores) / len(scores), 1)
    return {"average_score": average, "level": score_to_level(round(average)), "player_count": len(scores)}


@app.get("/analytics/by-category")
def get_category_averages(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    results = (
        db.query(
            models.Question.category,
            func.avg(models.Response.answer_value).label("average"),
            func.count(models.Response.id).label("response_count")
        )
        .join(models.Response, models.Response.question_id == models.Question.id)
        .join(models.AssessmentAttempt, models.Response.attempt_id == models.AssessmentAttempt.id)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .filter(models.Question.category.isnot(None))
        .filter(models.Response.answer_value.isnot(None))
        .group_by(models.Question.category)
        .all()
    )

    return [
        {"category": row.category, "average_score": round(row.average, 1), "response_count": row.response_count}
        for row in results
    ]

@app.get("/analytics/by-position")
def get_position_averages(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    latest_attempts = {}
    attempts = (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .order_by(models.AssessmentAttempt.submitted_at)
        .all()
    )
    for attempt in attempts:
        latest_attempts[attempt.user_id] = attempt

    position_scores = {}
    for user_id, attempt in latest_attempts.items():
        user = db.query(models.User).filter(models.User.id == user_id, models.User.deleted_at.is_(None)).first()
        if user is None:
            continue
        position_scores.setdefault(user.position, []).append(attempt.total_score)

    return [
        {"position": position, "average_score": round(sum(scores) / len(scores), 1), "player_count": len(scores)}
        for position, scores in position_scores.items()
    ]

@app.get("/analytics/by-position/{position}")
def get_position_detail(position: str, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    players = db.query(models.User).filter(models.User.role == "player", models.User.position == position, models.User.deleted_at.is_(None)).all()

    player_scores = []
    for player in players:
        result = calculate_proficiency(player.id, db)
        player_scores.append({
            "id": player.id,
            "name": player.name,
            "jersey_number": player.jersey_number,
            "total_score": result["total_score"],
            "level": result["level"]
        })

    return {"position": position, "players": player_scores}

@app.get("/users/{user_id}/category-breakdown")
def get_user_category_breakdown(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    results = (
        db.query(
            models.Question.category,
            func.avg(models.Response.answer_value).label("average")
        )
        .join(models.Response, models.Response.question_id == models.Question.id)
        .filter(models.Response.user_id == user_id)
        .filter(models.Question.category.isnot(None))
        .filter(models.Response.answer_value.isnot(None))
        .group_by(models.Question.category)
        .all()
    )

    return [
        {"category": row.category, "average_score": round(row.average, 1)}
        for row in results
    ]

@app.get("/me/category-breakdown")
def get_my_category_breakdown(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    results = (
        db.query(
            models.Question.category,
            func.avg(models.Response.answer_value).label("average")
        )
        .join(models.Response, models.Response.question_id == models.Question.id)
        .filter(models.Response.user_id == current_user.id)
        .filter(models.Question.category.isnot(None))
        .filter(models.Response.answer_value.isnot(None))
        .group_by(models.Question.category)
        .all()
    )

    return [
        {"category": row.category, "average_score": round(row.average, 1)}
        for row in results
    ]

@app.get("/analytics/trend")
def get_trend(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    attempts = (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .order_by(models.AssessmentAttempt.submitted_at)
        .all()
    )

    by_date = {}
    for a in attempts:
        date_key = a.submitted_at.strftime("%Y-%m-%d")
        by_date.setdefault(date_key, []).append(a.total_score)

    return [
        {"date": date, "average_score": round(sum(scores) / len(scores), 1)}
        for date, scores in sorted(by_date.items())
    ]

@app.get("/analytics/durations")
def get_durations(assessment_id: int, group_by: str | None = None, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    latest_attempts = {}
    attempts = (
        db.query(models.AssessmentAttempt)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .filter(models.AssessmentAttempt.duration_seconds.isnot(None))
        .order_by(models.AssessmentAttempt.submitted_at)
        .all()
    )
    for a in attempts:
        latest_attempts[a.user_id] = a

    if not group_by:
        results = []
        for user_id, attempt in latest_attempts.items():
            user = db.query(models.User).filter(models.User.id == user_id, models.User.deleted_at.is_(None)).first()
            if user is None:
                continue
            results.append({"user_id": user_id, "user_name": user.name, "duration_seconds": attempt.duration_seconds})
        return results

    grouped = {}
    for user_id, attempt in latest_attempts.items():
        user = db.query(models.User).filter(models.User.id == user_id, models.User.deleted_at.is_(None)).first()
        if user is None:
            continue

        if group_by == "position":
            keys = [user.position]
        elif group_by == "unit":
            keys = []
            if user.is_offense:
                keys.append("Offense")
            if user.is_defense:
                keys.append("Defense")
            if user.is_special_teams:
                keys.append("Special Teams")
        else:
            raise HTTPException(status_code=400, detail="Invalid group_by value")

        for key in keys:
            grouped.setdefault(key, []).append(attempt.duration_seconds)

    return [
        {"group": key, "average_seconds": round(sum(durations) / len(durations), 1), "player_count": len(durations)}
        for key, durations in grouped.items()
    ]


@app.get("/analytics/category-timing")
def get_category_timing(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    results = (
        db.query(
            models.Question.category,
            func.avg(models.Response.time_taken_seconds).label("average")
        )
        .join(models.Response, models.Response.question_id == models.Question.id)
        .join(models.AssessmentAttempt, models.Response.attempt_id == models.AssessmentAttempt.id)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .filter(models.Question.category.isnot(None))
        .filter(models.Response.time_taken_seconds.isnot(None))
        .group_by(models.Question.category)
        .all()
    )

    return [
        {"category": row.category, "average_seconds": round(row.average, 1)}
        for row in results
    ]


@app.get("/analytics/rapid-responses")
def get_rapid_responses(assessment_id: int, threshold: float = 1.5, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    responses = (
        db.query(models.Response, models.Question)
        .join(models.Question, models.Response.question_id == models.Question.id)
        .join(models.AssessmentAttempt, models.Response.attempt_id == models.AssessmentAttempt.id)
        .filter(models.AssessmentAttempt.assessment_id == assessment_id)
        .filter(models.Response.time_taken_seconds.isnot(None))
        .all()
    )

    stats = {}
    for response, question in responses:
        key = question.id
        if key not in stats:
            stats[key] = {"question_id": question.id, "question_text": question.question_text, "rapid_count": 0, "total_count": 0}
        stats[key]["total_count"] += 1
        if response.time_taken_seconds <= threshold:
            stats[key]["rapid_count"] += 1

    return [
        {**v, "rapid_rate": round(v["rapid_count"] / v["total_count"] * 100, 1)}
        for v in stats.values()
        if v["rapid_count"] > 0
    ]

# ----- Calendar Events -----

@app.post("/events", response_model=schemas.EventResponse)
def create_event(event: schemas.EventCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    is_public = event.is_public if current_user.role == "admin" else False

    new_event = models.CalendarEvent(
        created_by=current_user.id,
        title=event.title,
        description=event.description,
        event_date=event.event_date,
        is_public=is_public
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return new_event


@app.get("/events", response_model=list[schemas.EventResponse])
def get_events(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.CalendarEvent)
        .filter(
            (models.CalendarEvent.created_by == current_user.id) |
            (models.CalendarEvent.is_public == True)
        )
        .order_by(models.CalendarEvent.event_date)
        .all()
    )


@app.get("/events/today", response_model=list[schemas.EventResponse])
def get_todays_events(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    today_start = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time())
    today_end = datetime.combine(datetime.now(timezone.utc).date(), datetime.max.time())

    return (
        db.query(models.CalendarEvent)
        .filter(
            (models.CalendarEvent.created_by == current_user.id) |
            (models.CalendarEvent.is_public == True)
        )
        .filter(models.CalendarEvent.event_date >= today_start)
        .filter(models.CalendarEvent.event_date <= today_end)
        .order_by(models.CalendarEvent.event_date)
        .all()
    )


@app.delete("/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    event = db.query(models.CalendarEvent).filter(models.CalendarEvent.id == event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this event")

    db.delete(event)
    db.commit()
    return {"message": "Event deleted"}


# ----- Visibility logic -----

def user_can_see_assessment(assessment: models.Assessment, user: models.User, db: Session) -> bool:
    if assessment.assessment_type == "staff" and user.role != "admin":
        return False
    if assessment.assessment_type == "player" and user.role == "admin":
        return True  # admins can view/manage player assessments
    if assessment.is_public:
        return True
    if user.role == "admin":
        return True

    assignments = db.query(models.AssessmentAssignment).filter(models.AssessmentAssignment.assessment_id == assessment.id).all()

    for a in assignments:
        if a.assignment_type == "user" and str(user.id) == a.value:
            return True
        if a.assignment_type == "position" and user.position == a.value:
            return True
        if a.assignment_type == "unit" and getattr(user, f"is_{a.value}", False):
            return True
        if a.assignment_type == "year" and str(user.year) == a.value:
            return True
        if a.assignment_type == "group":
            is_member = (
                db.query(models.GroupMembership)
                .filter(models.GroupMembership.group_id == int(a.value))
                .filter(models.GroupMembership.user_id == user.id)
                .first()
            )
            if is_member:
                return True

    return False


def score_to_level(total_score: int) -> str:
    if total_score >= 18:
        return "Highly Advanced"
    elif total_score >= 16:
        return "Advanced"
    elif total_score >= 13:
        return "Intermediate"
    elif total_score >= 10:
        return "Novice"
    else:
        return "Not enough data"

def user_can_see_course(course: models.Course, user: models.User, db: Session) -> bool:
    if course.is_public:
        return True
    if user.role == "admin":
        return True

    assignments = db.query(models.CourseAssignment).filter(models.CourseAssignment.course_id == course.id).all()

    for a in assignments:
        if a.assignment_type == "user" and str(user.id) == a.value:
            return True
        if a.assignment_type == "position" and user.position == a.value:
            return True
        if a.assignment_type == "unit" and getattr(user, f"is_{a.value}", False):
            return True
        if a.assignment_type == "year" and str(user.year) == a.value:
            return True
        if a.assignment_type == "group":
            is_member = (
                db.query(models.GroupMembership)
                .filter(models.GroupMembership.group_id == int(a.value))
                .filter(models.GroupMembership.user_id == user.id)
                .first()
            )
            if is_member:
                return True

    return False


def user_can_see_announcement(announcement: models.Announcement, user: models.User, db: Session) -> bool:
    if announcement.is_public:
        return True
    if user.role == "admin":
        return True

    assignments = db.query(models.AnnouncementAssignment).filter(models.AnnouncementAssignment.announcement_id == announcement.id).all()

    for a in assignments:
        if a.assignment_type == "user" and str(user.id) == a.value:
            return True
        if a.assignment_type == "position" and user.position == a.value:
            return True
        if a.assignment_type == "unit" and getattr(user, f"is_{a.value}", False):
            return True
        if a.assignment_type == "year" and str(user.year) == a.value:
            return True
        if a.assignment_type == "group":
            is_member = (
                db.query(models.GroupMembership)
                .filter(models.GroupMembership.group_id == int(a.value))
                .filter(models.GroupMembership.user_id == user.id)
                .first()
            )
            if is_member:
                return True

    return False

def log_audit_action(db: Session, actor_id: int, action: str, target_type: str, target_id: int | None = None, reason: str | None = None):
    entry = models.AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason
    )
    db.add(entry)
    db.commit()

def user_can_see_standalone_survey(survey: models.StandaloneSurvey, user: models.User, db: Session) -> bool:
    if survey.is_public:
        return True
    if user.role == "admin":
        return True

    assignments = db.query(models.StandaloneSurveyAssignment).filter(models.StandaloneSurveyAssignment.survey_id == survey.id).all()

    for a in assignments:
        if a.assignment_type == "user" and str(user.id) == a.value:
            return True
        if a.assignment_type == "position" and user.position == a.value:
            return True
        if a.assignment_type == "unit" and getattr(user, f"is_{a.value}", False):
            return True
        if a.assignment_type == "year" and str(user.year) == a.value:
            return True
        if a.assignment_type == "group":
            is_member = (
                db.query(models.GroupMembership)
                .filter(models.GroupMembership.group_id == int(a.value))
                .filter(models.GroupMembership.user_id == user.id)
                .first()
            )
            if is_member:
                return True

    return False

# ----- Groups -----

@app.post("/groups", response_model=schemas.GroupResponse)
def create_group(group: schemas.GroupCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    new_group = models.Group(name=group.name, created_by=current_user.id)
    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    for member_id in group.member_ids:
        db.add(models.GroupMembership(group_id=new_group.id, user_id=member_id))
    db.commit()

    member_ids = [m.user_id for m in db.query(models.GroupMembership).filter(models.GroupMembership.group_id == new_group.id).all()]
    return schemas.GroupResponse(id=new_group.id, name=new_group.name, created_by=new_group.created_by, member_ids=member_ids)


@app.get("/groups", response_model=list[schemas.GroupResponse])
def get_groups(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    groups = db.query(models.Group).all()
    results = []
    for g in groups:
        member_ids = [m.user_id for m in db.query(models.GroupMembership).filter(models.GroupMembership.group_id == g.id).all()]
        results.append(schemas.GroupResponse(id=g.id, name=g.name, created_by=g.created_by, member_ids=member_ids))
    return results

@app.get("/groups/{group_id}", response_model=schemas.GroupResponse)
def get_group(group_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    member_ids = [m.user_id for m in db.query(models.GroupMembership).filter(models.GroupMembership.group_id == group_id).all()]
    return schemas.GroupResponse(id=group.id, name=group.name, created_by=group.created_by, member_ids=member_ids)


@app.put("/groups/{group_id}/members", response_model=schemas.GroupResponse)
def update_group_members(group_id: int, member_ids: list[int], db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    db.query(models.GroupMembership).filter(models.GroupMembership.group_id == group_id).delete()
    for user_id in member_ids:
        db.add(models.GroupMembership(group_id=group_id, user_id=user_id))
    db.commit()

    return schemas.GroupResponse(id=group.id, name=group.name, created_by=group.created_by, member_ids=member_ids)


@app.delete("/groups/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    db.query(models.GroupMembership).filter(models.GroupMembership.group_id == group_id).delete()
    db.delete(group)
    db.commit()
    return {"message": "Group deleted"}

# ----- Courses -----

@app.post("/courses", response_model=schemas.CourseResponse)
def create_course(course: schemas.CourseCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    new_course = models.Course(
        title=course.title,
        description=course.description,
        created_by=current_user.id,
        is_public=course.is_public,
        content_type=course.content_type
    )
    db.add(new_course)
    db.commit()
    db.refresh(new_course)

    for a in course.assignments:
        db.add(models.CourseAssignment(course_id=new_course.id, assignment_type=a.assignment_type, value=a.value))
    db.commit()
    db.refresh(new_course)
    return new_course

@app.put("/courses/{course_id}", response_model=schemas.CourseResponse)
def update_course(course_id: int, updated_course: schemas.CourseUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    course = db.query(models.Course).filter(models.Course.id == course_id, models.Course.deleted_at.is_(None)).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    update_data = updated_course.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(course, key, value)

    db.commit()
    db.refresh(course)
    return course

@app.get("/courses", response_model=list[schemas.CourseResponse])
def get_courses(content_type: str | None = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    query = db.query(models.Course).filter(models.Course.deleted_at.is_(None))
    if content_type:
        query = query.filter(models.Course.content_type == content_type)
    all_courses = query.all()
    return [c for c in all_courses if user_can_see_course(c, current_user, db)]


@app.get("/courses/{course_id}", response_model=schemas.CourseResponse)
def get_course(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    course = db.query(models.Course).filter(models.Course.id == course_id, models.Course.deleted_at.is_(None)).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if not user_can_see_course(course, current_user, db):
        raise HTTPException(status_code=403, detail="Not authorized to view this course")
    return course


@app.delete("/courses/{course_id}")
def delete_course(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    course = db.query(models.Course).filter(models.Course.id == course_id, models.Course.deleted_at.is_(None)).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    course.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Course archived"}


# ----- Modules -----

@app.post("/courses/{course_id}/modules", response_model=schemas.ModuleResponse)
def create_module(course_id: int, module: schemas.ModuleCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    course = db.query(models.Course).filter(models.Course.id == course_id, models.Course.deleted_at.is_(None)).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    new_module = models.Module(
        course_id=course_id,
        title=module.title,
        content=module.content,
        order_index=module.order_index
    )
    db.add(new_module)
    db.commit()
    db.refresh(new_module)
    return new_module


# ----- Surveys -----

@app.post("/modules/{module_id}/surveys", response_model=schemas.SurveyResponse)
def create_survey(module_id: int, survey: schemas.SurveyCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    module = db.query(models.Module).filter(models.Module.id == module_id).first()
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")

    new_survey = models.Survey(module_id=module_id, question=survey.question, survey_type=survey.survey_type)
    db.add(new_survey)
    db.commit()
    db.refresh(new_survey)

    for label in survey.options:
        db.add(models.SurveyOption(survey_id=new_survey.id, label=label))
    db.commit()
    db.refresh(new_survey)
    return new_survey

@app.post("/surveys/{survey_id}/answer", response_model=schemas.SurveyAnswerResponse)
def submit_survey_answer(survey_id: int, answer: schemas.SurveyAnswerCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    survey = db.query(models.Survey).filter(models.Survey.id == survey_id).first()
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")

    existing = (
        db.query(models.SurveyAnswer)
        .filter(models.SurveyAnswer.survey_id == survey_id)
        .filter(models.SurveyAnswer.user_id == current_user.id)
        .first()
    )

    if existing:
        existing.option_id = answer.option_id
        existing.answer_text = answer.answer_text
        db.commit()
        db.refresh(existing)
        return existing

    new_answer = models.SurveyAnswer(
        survey_id=survey_id,
        user_id=current_user.id,
        option_id=answer.option_id,
        answer_text=answer.answer_text
    )
    db.add(new_answer)
    db.commit()
    db.refresh(new_answer)
    return new_answer


@app.get("/surveys/{survey_id}/my-answer", response_model=schemas.SurveyAnswerResponse | None)
def get_my_survey_answer(survey_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.SurveyAnswer)
        .filter(models.SurveyAnswer.survey_id == survey_id)
        .filter(models.SurveyAnswer.user_id == current_user.id)
        .first()
    )

@app.get("/surveys/{survey_id}/responses")
def get_survey_responses(survey_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    survey = db.query(models.Survey).filter(models.Survey.id == survey_id).first()
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")

    answers = db.query(models.SurveyAnswer).filter(models.SurveyAnswer.survey_id == survey_id).all()

    results = []
    for a in answers:
        user = db.query(models.User).filter(models.User.id == a.user_id, models.User.deleted_at.is_(None)).first()
        option_label = None
        if a.option_id:
            option = db.query(models.SurveyOption).filter(models.SurveyOption.id == a.option_id).first()
            option_label = option.label if option else None

        results.append({
            "user_id": a.user_id,
            "user_name": user.name if user else "Unknown",
            "answer": option_label if option_label else a.answer_text,
            "submitted_at": a.submitted_at
        })

    return results

@app.delete("/surveys/{survey_id}")
def delete_survey(survey_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    survey = db.query(models.Survey).filter(models.Survey.id == survey_id).first()
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")

    db.query(models.SurveyOption).filter(models.SurveyOption.survey_id == survey_id).delete()
    db.delete(survey)
    db.commit()
    return {"message": "Survey deleted"}

# ------ File attachments for modules ------

@app.post("/modules/{module_id}/attachments", response_model=schemas.AttachmentResponse)
def upload_attachment(module_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    module = db.query(models.Module).filter(models.Module.id == module_id).first()
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")

    key = f"attachments/module_{module_id}/{file.filename}"
    file_url = upload_file_to_storage(file.file, key)

    new_attachment = models.Attachment(
        module_id=module_id,
        filename=file.filename,
        file_path=file_url,
        uploaded_by=current_user.id
    )
    db.add(new_attachment)
    db.commit()
    db.refresh(new_attachment)
    return new_attachment


@app.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    attachment = db.query(models.Attachment).filter(models.Attachment.id == attachment_id).first()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    key = attachment.file_path.replace(f"{os.getenv('R2_PUBLIC_URL')}/", "")
    delete_file_from_storage(key)

    db.delete(attachment)
    db.commit()
    return {"message": "Attachment deleted"}

# ------ module detail route for fron end to fetch single module with its attachments ------

@app.get("/modules/{module_id}", response_model=schemas.ModuleResponse)
def get_module(module_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    module = db.query(models.Module).filter(models.Module.id == module_id).first()
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")
    return module

# ----- Staff Duties -----

@app.post("/staff-duties", response_model=schemas.StaffDutyResponse)
def create_staff_duty(duty: schemas.StaffDutyCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    new_duty = models.StaffDuty(
        title=duty.title,
        description=duty.description,
        assigned_to=duty.assigned_to,
        created_by=current_user.id,
        status=duty.status
    )
    db.add(new_duty)
    db.commit()
    db.refresh(new_duty)
    return new_duty


@app.get("/staff-duties", response_model=list[schemas.StaffDutyResponse])
def get_staff_duties(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    return db.query(models.StaffDuty).all()


@app.put("/staff-duties/{duty_id}", response_model=schemas.StaffDutyResponse)
def update_staff_duty(duty_id: int, updated_duty: schemas.StaffDutyUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    duty = db.query(models.StaffDuty).filter(models.StaffDuty.id == duty_id).first()
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")

    update_data = updated_duty.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(duty, key, value)

    db.commit()
    db.refresh(duty)
    return duty

@app.get("/staff-duties/mine", response_model=list[schemas.StaffDutyResponse])
def get_my_duties(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    return (
        db.query(models.StaffDuty)
        .filter(models.StaffDuty.assigned_to == current_user.id)
        .filter(models.StaffDuty.status != "done")
        .all()
    )

@app.delete("/staff-duties/{duty_id}")
def delete_staff_duty(duty_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    duty = db.query(models.StaffDuty).filter(models.StaffDuty.id == duty_id).first()
    if duty is None:
        raise HTTPException(status_code=404, detail="Duty not found")

    db.delete(duty)
    db.commit()
    return {"message": "Duty deleted"}

# ----- Staff Tracker -----

@app.post("/tracker-items", response_model=schemas.TrackerItemResponse)
def create_tracker_item(item: schemas.TrackerItemCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    new_item = models.StaffTrackerItem(
        item_type=item.item_type,
        title=item.title,
        description=item.description,
        item_date=item.item_date,
        created_by=current_user.id
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


@app.get("/tracker-items", response_model=list[schemas.TrackerItemResponse])
def get_tracker_items(item_type: str | None = None, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    query = db.query(models.StaffTrackerItem)
    if item_type:
        query = query.filter(models.StaffTrackerItem.item_type == item_type)
    return query.order_by(models.StaffTrackerItem.item_date).all()


@app.get("/tracker-items/{item_id}", response_model=schemas.TrackerItemResponse)
def get_tracker_item(item_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    item = db.query(models.StaffTrackerItem).filter(models.StaffTrackerItem.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.delete("/tracker-items/{item_id}")
def delete_tracker_item(item_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    item = db.query(models.StaffTrackerItem).filter(models.StaffTrackerItem.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"message": "Item deleted"}


@app.post("/tracker-items/{item_id}/updates", response_model=schemas.StaffUpdateResponse)
def create_staff_update(item_id: int, update: schemas.StaffUpdateCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    item = db.query(models.StaffTrackerItem).filter(models.StaffTrackerItem.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    new_update = models.StaffUpdate(tracker_item_id=item_id, user_id=current_user.id, note=update.note)
    db.add(new_update)
    db.commit()
    db.refresh(new_update)

    return schemas.StaffUpdateResponse(
        id=new_update.id,
        tracker_item_id=new_update.tracker_item_id,
        user_id=new_update.user_id,
        user_name=current_user.name,
        note=new_update.note,
        posted_at=new_update.posted_at
    )


@app.get("/tracker-items/{item_id}/updates", response_model=list[schemas.StaffUpdateResponse])
def get_staff_updates(item_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    updates = (
        db.query(models.StaffUpdate)
        .filter(models.StaffUpdate.tracker_item_id == item_id)
        .order_by(models.StaffUpdate.posted_at.desc())
        .all()
    )
    return [
        schemas.StaffUpdateResponse(
            id=u.id,
            tracker_item_id=u.tracker_item_id,
            user_id=u.user_id,
            user_name=u.user.name,
            note=u.note,
            posted_at=u.posted_at
        )
        for u in updates
    ]

# ----- Project Boards -----

@app.post("/project-boards", response_model=schemas.ProjectBoardResponse)
def create_board(board: schemas.ProjectBoardCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    new_board = models.ProjectBoard(
        title=board.title,
        description=board.description,
        course_id=board.course_id,
        created_by=current_user.id
    )
    db.add(new_board)
    db.commit()
    db.refresh(new_board)
    return new_board


@app.get("/project-boards", response_model=list[schemas.ProjectBoardResponse])
def get_boards(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    return db.query(models.ProjectBoard).all()


@app.get("/project-boards/{board_id}", response_model=schemas.ProjectBoardResponse)
def get_board(board_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    board = db.query(models.ProjectBoard).filter(models.ProjectBoard.id == board_id).first()
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


@app.delete("/project-boards/{board_id}")
def delete_board(board_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    board = db.query(models.ProjectBoard).filter(models.ProjectBoard.id == board_id).first()
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    db.delete(board)
    db.commit()
    return {"message": "Board deleted"}


# ----- Project Tasks -----

@app.post("/project-boards/{board_id}/tasks", response_model=schemas.ProjectTaskResponse)
def create_task(board_id: int, task: schemas.ProjectTaskCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    board = db.query(models.ProjectBoard).filter(models.ProjectBoard.id == board_id).first()
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")

    new_task = models.ProjectTask(
        board_id=board_id,
        title=task.title,
        description=task.description,
        assigned_to=task.assigned_to,
        due_date=task.due_date,
        status=task.status
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task


@app.get("/project-boards/{board_id}/tasks", response_model=list[schemas.ProjectTaskResponse])
def get_tasks(board_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    return (
        db.query(models.ProjectTask)
        .filter(models.ProjectTask.board_id == board_id)
        .order_by(models.ProjectTask.due_date)
        .all()
    )


@app.put("/tasks/{task_id}", response_model=schemas.ProjectTaskResponse)
def update_task(task_id: int, updated_task: schemas.ProjectTaskUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    task = db.query(models.ProjectTask).filter(models.ProjectTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = updated_task.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return task


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    task = db.query(models.ProjectTask).filter(models.ProjectTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}


# ----- Announcements -----

@app.post("/announcements", response_model=schemas.AnnouncementResponse)
def create_announcement(announcement: schemas.AnnouncementCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    new_announcement = models.Announcement(
        title=announcement.title,
        body=announcement.body,
        is_public=announcement.is_public,
        is_pinned=announcement.is_pinned,
        created_by=current_user.id
    )
    db.add(new_announcement)
    db.commit()
    db.refresh(new_announcement)

    for a in announcement.assignments:
        db.add(models.AnnouncementAssignment(announcement_id=new_announcement.id, assignment_type=a.assignment_type, value=a.value))
    db.commit()
    db.refresh(new_announcement)
    return new_announcement


@app.get("/announcements", response_model=list[schemas.AnnouncementResponse])
def get_announcements(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    all_announcements = db.query(models.Announcement).order_by(models.Announcement.is_pinned.desc(), models.Announcement.created_at.desc()).all()
    return [a for a in all_announcements if user_can_see_announcement(a, current_user, db)]


@app.get("/announcements/{announcement_id}", response_model=schemas.AnnouncementResponse)
def get_announcement(announcement_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    announcement = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if announcement is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    if not user_can_see_announcement(announcement, current_user, db):
        raise HTTPException(status_code=403, detail="Not authorized to view this announcement")
    return announcement


@app.put("/announcements/{announcement_id}", response_model=schemas.AnnouncementResponse)
def update_announcement(announcement_id: int, updated: schemas.AnnouncementUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    announcement = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if announcement is None:
        raise HTTPException(status_code=404, detail="Announcement not found")

    update_data = updated.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(announcement, key, value)

    db.commit()
    db.refresh(announcement)
    return announcement


@app.delete("/announcements/{announcement_id}")
def delete_announcement(announcement_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    announcement = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if announcement is None:
        raise HTTPException(status_code=404, detail="Announcement not found")

    db.query(models.AnnouncementAssignment).filter(models.AnnouncementAssignment.announcement_id == announcement_id).delete()
    db.query(models.AnnouncementImage).filter(models.AnnouncementImage.announcement_id == announcement_id).delete()
    db.delete(announcement)
    db.commit()
    return {"message": "Announcement deleted"}


@app.post("/announcements/{announcement_id}/images", response_model=schemas.AnnouncementImageResponse)
def upload_announcement_image(announcement_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    announcement = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if announcement is None:
        raise HTTPException(status_code=404, detail="Announcement not found")

    key = f"announcements/announcement_{announcement_id}/{file.filename}"
    file_url = upload_file_to_storage(file.file, key)

    new_image = models.AnnouncementImage(announcement_id=announcement_id, file_path=file_url)
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    return new_image


@app.delete("/announcement-images/{image_id}")
def delete_announcement_image(image_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    image = db.query(models.AnnouncementImage).filter(models.AnnouncementImage.id == image_id).first()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    key = image.file_path.replace(f"{os.getenv('R2_PUBLIC_URL')}/", "")
    delete_file_from_storage(key)

    db.delete(image)
    db.commit()
    return {"message": "Image deleted"}


# -------- Toolbar Search Function --------

@app.get("/search")
def search(q: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if len(q.strip()) < 2:
        return []

    query = f"%{q.strip()}%"
    results = []

    matching_courses = db.query(models.Course).filter(models.Course.title.ilike(query), models.Course.deleted_at.is_(None)).all()
    for c in matching_courses:
        if user_can_see_course(c, current_user, db):
            results.append({"type": "Course", "title": c.title, "path": f"/programming/{c.id}"})

    matching_assessments = db.query(models.Assessment).filter(models.Assessment.title.ilike(query), models.Assessment.deleted_at.is_(None)).all()
    for a in matching_assessments:
        if user_can_see_assessment(a, current_user, db):
            base = "/staff/assessment" if a.assessment_type == "staff" else "/assessment"
            results.append({"type": "Assessment", "title": a.title, "path": f"{base}/{a.id}"})

    matching_announcements = db.query(models.Announcement).filter(models.Announcement.title.ilike(query)).all()
    for an in matching_announcements:
        if user_can_see_announcement(an, current_user, db):
            landing = "/dashboard" if current_user.role == "admin" else "/home"
            results.append({"type": "Announcement", "title": an.title, "path": landing})

    if current_user.role == "admin":
        matching_users = db.query(models.User).filter(models.User.name.ilike(query), models.User.deleted_at.is_(None)).all()
        for u in matching_users:
            if u.role == "admin":
                results.append({"type": "Staff", "title": u.name, "path": "/staff/roster"})
            else:
                results.append({"type": "Player", "title": u.name, "path": f"/roster/{u.id}"})

        matching_groups = db.query(models.Group).filter(models.Group.name.ilike(query)).all()
        for g in matching_groups:
            results.append({"type": "Group", "title": g.name, "path": f"/groups/{g.id}"})

        matching_duties = db.query(models.StaffDuty).filter(models.StaffDuty.title.ilike(query)).all()
        for d in matching_duties:
            results.append({"type": "Staff Duty", "title": d.title, "path": "/staff/duties"})

        matching_boards = db.query(models.ProjectBoard).filter(models.ProjectBoard.title.ilike(query)).all()
        for b in matching_boards:
            results.append({"type": "Project Board", "title": b.title, "path": f"/project-boards/{b.id}"})

    return results[:20]

# ----- Partner Categories -----

@app.post("/partner-categories", response_model=schemas.PartnerCategoryResponse)
def create_partner_category(category: schemas.PartnerCategoryCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    new_category = models.PartnerCategory(name=category.name, created_by=current_user.id)
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    return new_category


@app.get("/partner-categories", response_model=list[schemas.PartnerCategoryResponse])
def get_partner_categories(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.PartnerCategory).all()


@app.delete("/partner-categories/{category_id}")
def delete_partner_category(category_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    category = db.query(models.PartnerCategory).filter(models.PartnerCategory.id == category_id).first()
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    db.query(models.Partner).filter(models.Partner.category_id == category_id).delete()
    db.delete(category)
    db.commit()
    return {"message": "Category deleted"}


# ----- Partners -----

@app.post("/partner-categories/{category_id}/partners", response_model=schemas.PartnerResponse)
def create_partner(category_id: int, partner: schemas.PartnerCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    category = db.query(models.PartnerCategory).filter(models.PartnerCategory.id == category_id).first()
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    new_partner = models.Partner(
        category_id=category_id,
        name=partner.name,
        phone=partner.phone,
        email=partner.email,
        description=partner.description,
        contact_name=partner.contact_name
    )
    db.add(new_partner)
    db.commit()
    db.refresh(new_partner)
    return new_partner


@app.get("/partner-categories/{category_id}/partners", response_model=list[schemas.PartnerResponse])
def get_partners(category_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Partner).filter(models.Partner.category_id == category_id).all()


@app.get("/partners/{partner_id}", response_model=schemas.PartnerResponse)
def get_partner(partner_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    partner = db.query(models.Partner).filter(models.Partner.id == partner_id).first()
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    return partner


@app.put("/partners/{partner_id}", response_model=schemas.PartnerResponse)
def update_partner(partner_id: int, updated: schemas.PartnerUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    partner = db.query(models.Partner).filter(models.Partner.id == partner_id).first()
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")

    update_data = updated.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(partner, key, value)

    db.commit()
    db.refresh(partner)
    return partner


@app.delete("/partners/{partner_id}")
def delete_partner(partner_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    partner = db.query(models.Partner).filter(models.Partner.id == partner_id).first()
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")

    db.delete(partner)
    db.commit()
    return {"message": "Partner deleted"}

# ----- Archive / Restore -----

@app.get("/archive/users")
def get_archived_users(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    users = db.query(models.User).filter(models.User.deleted_at.is_not(None)).all()
    return [
        {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "deleted_at": u.deleted_at}
        for u in users
    ]


@app.post("/archive/users/{user_id}/restore")
def restore_user(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.deleted_at = None
    db.commit()
    return {"message": "User restored"}

@app.delete("/archive/users/{user_id}/permanent")
def permanently_delete_user(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == "admin" and not current_user.is_super_admin:
        raise HTTPException(status_code=403, detail="Only super admins can permanently delete an admin")

    log_audit_action(db, current_user.id, "permanent_delete_user", "User", user_id)
    db.delete(user)
    db.commit()
    return {"message": "User permanently deleted"}



@app.get("/archive/courses")
def get_archived_courses(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    courses = db.query(models.Course).filter(models.Course.deleted_at.is_not(None)).all()
    return [
        {"id": c.id, "title": c.title, "deleted_at": c.deleted_at}
        for c in courses
    ]


@app.post("/archive/courses/{course_id}/restore")
def restore_course(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    course.deleted_at = None
    db.commit()
    return {"message": "Course restored"}



@app.delete("/archive/courses/{course_id}/permanent")
def permanently_delete_course(course_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    module_ids = [m.id for m in db.query(models.Module).filter(models.Module.course_id == course_id).all()]
    for mid in module_ids:
        survey_ids = [s.id for s in db.query(models.Survey).filter(models.Survey.module_id == mid).all()]
        for sid in survey_ids:
            db.query(models.SurveyOption).filter(models.SurveyOption.survey_id == sid).delete()
        db.query(models.Survey).filter(models.Survey.module_id == mid).delete()
        db.query(models.Attachment).filter(models.Attachment.module_id == mid).delete()
    db.query(models.Module).filter(models.Module.course_id == course_id).delete()
    db.query(models.CourseAssignment).filter(models.CourseAssignment.course_id == course_id).delete()

    log_audit_action(db, current_user.id, "permanent_delete_course", "Course", course_id)
    db.delete(course)
    db.commit()
    return {"message": "Course permanently deleted"}


@app.get("/archive/assessments")
def get_archived_assessments(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    assessments = db.query(models.Assessment).filter(models.Assessment.deleted_at.is_not(None)).all()
    return [
        {"id": a.id, "title": a.title, "deleted_at": a.deleted_at}
        for a in assessments
    ]


@app.post("/archive/assessments/{assessment_id}/restore")
def restore_assessment(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    assessment = db.query(models.Assessment).filter(models.Assessment.id == assessment_id).first()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    assessment.deleted_at = None
    db.commit()
    return {"message": "Assessment restored"}


    return {"message": "User permanently deleted"}


@app.delete("/archive/assessments/{assessment_id}/permanent")
def permanently_delete_assessment(assessment_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    assessment = db.query(models.Assessment).filter(models.Assessment.id == assessment_id).first()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    question_ids = [q.id for q in db.query(models.Question).filter(models.Question.assessment_id == assessment_id).all()]
    for qid in question_ids:
        db.query(models.AnswerOption).filter(models.AnswerOption.question_id == qid).delete()
    db.query(models.Question).filter(models.Question.assessment_id == assessment_id).delete()
    db.query(models.AssessmentAssignment).filter(models.AssessmentAssignment.assessment_id == assessment_id).delete()

    log_audit_action(db, current_user.id, "permanent_delete_assessment", "Assessment", assessment_id)
    db.delete(assessment)
    db.commit()
    return {"message": "Assessment permanently deleted"}

@app.get("/audit-log", response_model=list[schemas.AuditLogResponse])
def get_audit_log(db: Session = Depends(get_db), current_user: models.User = Depends(require_super_admin)):
    return db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(200).all()

# ----- Sticky Notes -----

@app.post("/sticky-notes", response_model=schemas.StickyNoteResponse)
def create_sticky_note(note: schemas.StickyNoteCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    new_note = models.StickyNote(user_id=current_user.id, content=note.content, color=note.color)
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return new_note


@app.get("/sticky-notes", response_model=list[schemas.StickyNoteResponse])
def get_my_sticky_notes(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.StickyNote)
        .filter(models.StickyNote.user_id == current_user.id)
        .order_by(models.StickyNote.created_at)
        .all()
    )


@app.put("/sticky-notes/{note_id}", response_model=schemas.StickyNoteResponse)
def update_sticky_note(note_id: int, updated: schemas.StickyNoteUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    note = db.query(models.StickyNote).filter(models.StickyNote.id == note_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this note")

    update_data = updated.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(note, key, value)

    db.commit()
    db.refresh(note)
    return note


@app.delete("/sticky-notes/{note_id}")
def delete_sticky_note(note_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    note = db.query(models.StickyNote).filter(models.StickyNote.id == note_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this note")

    db.delete(note)
    db.commit()
    return {"message": "Note deleted"}

# ----- Touchpoints -----

@app.post("/touchpoints", response_model=schemas.TouchpointResponse)
def create_touchpoint(touchpoint: schemas.TouchpointCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == touchpoint.user_id, models.User.deleted_at.is_(None)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Player not found")

    new_touchpoint = models.Touchpoint(
        user_id=touchpoint.user_id,
        logged_by=current_user.id,
        meeting_type=touchpoint.meeting_type,
        notes=touchpoint.notes
    )
    db.add(new_touchpoint)
    db.commit()
    db.refresh(new_touchpoint)
    return new_touchpoint


@app.get("/touchpoints", response_model=list[schemas.TouchpointResponse])
def get_touchpoints(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    return db.query(models.Touchpoint).order_by(models.Touchpoint.created_at.desc()).all()


@app.delete("/touchpoints/{touchpoint_id}")
def delete_touchpoint(touchpoint_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    touchpoint = db.query(models.Touchpoint).filter(models.Touchpoint.id == touchpoint_id).first()
    if touchpoint is None:
        raise HTTPException(status_code=404, detail="Touchpoint not found")
    db.delete(touchpoint)
    db.commit()
    return {"message": "Touchpoint deleted"}


@app.get("/analytics/touchpoint-frequency")
def get_touchpoint_frequency(
    group_by: str,
    period: str,
    date: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    target_date = datetime.strptime(date, "%Y-%m-%d")

    if period == "day":
        start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
    elif period == "month":
        start = datetime(target_date.year, target_date.month, 1, tzinfo=timezone.utc)
        if target_date.month == 12:
            end = datetime(target_date.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(target_date.year, target_date.month + 1, 1, tzinfo=timezone.utc)
    elif period == "year":
        start = datetime(target_date.year, 1, 1, tzinfo=timezone.utc)
        end = datetime(target_date.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        raise HTTPException(status_code=400, detail="Invalid period value")

    touchpoints = (
        db.query(models.Touchpoint)
        .filter(models.Touchpoint.created_at >= start)
        .filter(models.Touchpoint.created_at < end)
        .all()
    )

    grouped = {}
    for tp in touchpoints:
        user = db.query(models.User).filter(models.User.id == tp.user_id, models.User.deleted_at.is_(None)).first()
        if user is None:
            continue

        if group_by == "person":
            keys = [user.name]
        elif group_by == "position":
            keys = [user.position]
        elif group_by == "unit":
            keys = []
            if user.is_offense:
                keys.append("Offense")
            if user.is_defense:
                keys.append("Defense")
            if user.is_special_teams:
                keys.append("Special Teams")
        else:
            raise HTTPException(status_code=400, detail="Invalid group_by value")

        for key in keys:
            grouped[key] = grouped.get(key, 0) + 1

    return [{"group": key, "frequency": count} for key, count in grouped.items()]

# ----- Resumes -----

@app.post("/resumes", response_model=schemas.ResumeResponse)
def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    key = f"resumes/user_{current_user.id}/{file.filename}"
    file_url = upload_file_to_storage(file.file, key)

    new_resume = models.Resume(
        user_id=current_user.id,
        filename=file.filename,
        file_path=file_url
    )
    db.add(new_resume)
    db.commit()
    db.refresh(new_resume)
    return new_resume

@app.get("/users/{user_id}/resumes", response_model=list[schemas.ResumeResponse])
def get_user_resumes(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to view this resume")

    return (
        db.query(models.Resume)
        .filter(models.Resume.user_id == user_id)
        .order_by(models.Resume.uploaded_at.desc())
        .all()
    )


@app.delete("/resumes/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    resume = db.query(models.Resume).filter(models.Resume.id == resume_id).first()
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")

    if resume.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this resume")

    key = resume.file_path.replace(f"{os.getenv('R2_PUBLIC_URL')}/", "")
    delete_file_from_storage(key)

    db.delete(resume)
    db.commit()
    return {"message": "Resume deleted"}

# ----- Community Service -----

@app.post("/community-service", response_model=schemas.CommunityServiceResponse)
def create_community_service_log(log: schemas.CommunityServiceCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    new_log = models.CommunityServiceLog(
        user_id=current_user.id,
        hours=log.hours,
        organization=log.organization,
        description=log.description,
        service_date=log.service_date
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return new_log


@app.get("/community-service/mine", response_model=list[schemas.CommunityServiceResponse])
def get_my_community_service(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.CommunityServiceLog)
        .filter(models.CommunityServiceLog.user_id == current_user.id)
        .order_by(models.CommunityServiceLog.service_date.desc())
        .all()
    )


@app.delete("/community-service/{log_id}")
def delete_community_service_log(log_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    log = db.query(models.CommunityServiceLog).filter(models.CommunityServiceLog.id == log_id).first()
    if log is None:
        raise HTTPException(status_code=404, detail="Log not found")
    if log.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this log")

    db.delete(log)
    db.commit()
    return {"message": "Log deleted"}


@app.get("/community-service/totals")
def get_community_service_totals(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    results = (
        db.query(
            models.CommunityServiceLog.user_id,
            func.sum(models.CommunityServiceLog.hours).label("total_hours")
        )
        .group_by(models.CommunityServiceLog.user_id)
        .all()
    )

    output = []
    for user_id, total_hours in results:
        user = db.query(models.User).filter(models.User.id == user_id, models.User.deleted_at.is_(None)).first()
        if user is None:
            continue
        output.append({"user_id": user_id, "user_name": user.name, "total_hours": round(total_hours, 1)})

    return sorted(output, key=lambda x: x["total_hours"], reverse=True)


@app.get("/community-service/users/{user_id}", response_model=list[schemas.CommunityServiceResponse])
def get_user_community_service(user_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    return (
        db.query(models.CommunityServiceLog)
        .filter(models.CommunityServiceLog.user_id == user_id)
        .order_by(models.CommunityServiceLog.service_date.desc())
        .all()
    )

# ----- Standalone Surveys -----

@app.post("/standalone-surveys", response_model=schemas.StandaloneSurveyResponse)
def create_standalone_survey(survey: schemas.StandaloneSurveyCreate, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    new_survey = models.StandaloneSurvey(
        question=survey.question,
        survey_type=survey.survey_type,
        is_public=survey.is_public,
        created_by=current_user.id
    )
    db.add(new_survey)
    db.commit()
    db.refresh(new_survey)

    for label in survey.options:
        db.add(models.StandaloneSurveyOption(survey_id=new_survey.id, label=label))

    for a in survey.assignments:
        db.add(models.StandaloneSurveyAssignment(survey_id=new_survey.id, assignment_type=a.assignment_type, value=a.value))

    db.commit()
    db.refresh(new_survey)
    return new_survey


@app.get("/standalone-surveys", response_model=list[schemas.StandaloneSurveyResponse])
def get_standalone_surveys(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    all_surveys = db.query(models.StandaloneSurvey).order_by(models.StandaloneSurvey.created_at.desc()).all()
    return [s for s in all_surveys if user_can_see_standalone_survey(s, current_user, db)]


@app.delete("/standalone-surveys/{survey_id}")
def delete_standalone_survey(survey_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    survey = db.query(models.StandaloneSurvey).filter(models.StandaloneSurvey.id == survey_id).first()
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")

    db.query(models.StandaloneSurveyAnswer).filter(models.StandaloneSurveyAnswer.survey_id == survey_id).delete()
    db.query(models.StandaloneSurveyOption).filter(models.StandaloneSurveyOption.survey_id == survey_id).delete()
    db.query(models.StandaloneSurveyAssignment).filter(models.StandaloneSurveyAssignment.survey_id == survey_id).delete()
    db.delete(survey)
    db.commit()
    return {"message": "Survey deleted"}


@app.post("/standalone-surveys/{survey_id}/answer", response_model=schemas.StandaloneSurveyAnswerResponse)
def submit_standalone_survey_answer(survey_id: int, answer: schemas.StandaloneSurveyAnswerCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    survey = db.query(models.StandaloneSurvey).filter(models.StandaloneSurvey.id == survey_id).first()
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")

    existing = (
        db.query(models.StandaloneSurveyAnswer)
        .filter(models.StandaloneSurveyAnswer.survey_id == survey_id)
        .filter(models.StandaloneSurveyAnswer.user_id == current_user.id)
        .first()
    )

    if existing:
        existing.option_id = answer.option_id
        existing.answer_text = answer.answer_text
        db.commit()
        db.refresh(existing)
        return existing

    new_answer = models.StandaloneSurveyAnswer(
        survey_id=survey_id,
        user_id=current_user.id,
        option_id=answer.option_id,
        answer_text=answer.answer_text
    )
    db.add(new_answer)
    db.commit()
    db.refresh(new_answer)
    return new_answer


@app.get("/standalone-surveys/{survey_id}/my-answer", response_model=schemas.StandaloneSurveyAnswerResponse | None)
def get_my_standalone_survey_answer(survey_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.StandaloneSurveyAnswer)
        .filter(models.StandaloneSurveyAnswer.survey_id == survey_id)
        .filter(models.StandaloneSurveyAnswer.user_id == current_user.id)
        .first()
    )


@app.get("/standalone-surveys/{survey_id}/responses")
def get_standalone_survey_responses(survey_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_admin)):
    survey = db.query(models.StandaloneSurvey).filter(models.StandaloneSurvey.id == survey_id).first()
    if survey is None:
        raise HTTPException(status_code=404, detail="Survey not found")

    answers = db.query(models.StandaloneSurveyAnswer).filter(models.StandaloneSurveyAnswer.survey_id == survey_id).all()

    results = []
    for a in answers:
        user = db.query(models.User).filter(models.User.id == a.user_id, models.User.deleted_at.is_(None)).first()
        option_label = None
        if a.option_id:
            option = db.query(models.StandaloneSurveyOption).filter(models.StandaloneSurveyOption.id == a.option_id).first()
            option_label = option.label if option else None

        results.append({
            "user_id": a.user_id,
            "user_name": user.name if user else "Unknown",
            "answer": option_label if option_label else a.answer_text,
            "submitted_at": a.submitted_at
        })

    return results