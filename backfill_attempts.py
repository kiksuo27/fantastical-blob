from database import SessionLocal
from sqlalchemy import func
import models

db = SessionLocal()

# Find every distinct (user, assessment) pair that has old, attempt-less responses
old_responses = (
    db.query(models.Response)
    .filter(models.Response.attempt_id.is_(None))
    .all()
)

grouped = {}
for r in old_responses:
    question = db.query(models.Question).filter(models.Question.id == r.question_id).first()
    if question is None:
        continue
    key = (r.user_id, question.assessment_id)
    grouped.setdefault(key, []).append(r)

def score_to_level(total_score):
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

created_count = 0
for (user_id, assessment_id), responses in grouped.items():
    total_score = 0
    for r in responses:
        question = db.query(models.Question).filter(models.Question.id == r.question_id).first()
        if question and question.value_points is not None and r.answer_value is not None:
            total_score += r.answer_value

    level = score_to_level(total_score)

    new_attempt = models.AssessmentAttempt(
        assessment_id=assessment_id,
        user_id=user_id,
        total_score=total_score,
        level=level
    )
    db.add(new_attempt)
    db.commit()
    db.refresh(new_attempt)

    for r in responses:
        r.attempt_id = new_attempt.id
    db.commit()

    created_count += 1
    print(f"Created attempt for user {user_id}, assessment {assessment_id}: {total_score} pts ({level})")

print(f"\nDone. Created {created_count} attempts from {len(old_responses)} old responses.")

db.close()