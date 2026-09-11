from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Date, Text, Float
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key = True, index = True)
    jersey_number = Column(Integer, nullable = False)
    name = Column(String, nullable = False)
    position = Column(String, nullable = False)
    year = Column(Integer, nullable = False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column (String, nullable=True)
    role = Column(String, nullable=False, default="player")
    is_offense = Column(Boolean, nullable=False, default=False)
    is_defense = Column(Boolean, nullable=False, default=False)
    is_special_teams = Column(Boolean, nullable=False, default=False)
    birthday = Column(Date, nullable=True)
    deleted_at = Column(DateTime, nullable=True, default=None)
    is_super_admin = Column(Boolean, nullable=False, default=False)
    

class Assessment(Base):
    __tablename__ = "assessments"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_public = Column(Boolean, nullable=False, default=False)
    assessment_type = Column(String, nullable=False, default="player")  # "player" or "staff"
    deleted_at = Column(DateTime, nullable=True, default=None)


    questions = relationship("Question", back_populates="assessment")

class AssessmentAssignment(Base):
    __tablename__ = "assessment_assignments"
    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    assignment_type = Column(String, nullable=False)  # "user", "group", "position", "unit", "year"
    value = Column(String, nullable=False)


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"
    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_score = Column(Integer, nullable=False)
    level = Column(String, nullable=False)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    duration_seconds = Column(Float, nullable=True)


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    question_text = Column(String, nullable=False)
    question_type = Column(String, nullable=False)  # e.g., "multiple_choice", "text", etc.
    category = Column(String, nullable=True)  # e.g., "PAAS", "Mental Health", etc.
    value_points = Column(Integer, nullable=True)  # Points for the question, if applicable

    assessment = relationship("Assessment", back_populates="questions")
    options = relationship("AnswerOption", back_populates="question")


class AnswerOption(Base):
    __tablename__ = "answer_options"
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    label = Column(String, nullable=False)
    value = Column(Integer, nullable=False)

    question = relationship("Question", back_populates="options")

class Response(Base):
    __tablename__ = "responses"
    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("assessment_attempts.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_value = Column(Integer, nullable=True)
    answer_text = Column(String, nullable=True)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    time_taken_seconds = Column(Float, nullable=True)

    user = relationship("User")
    question = relationship("Question")

class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id = Column(Integer, primary_key=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    event_date = Column(DateTime, nullable=False)
    is_public = Column(Boolean, nullable=False, default=True)

    creator = relationship("User")

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)


class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_public = Column(Boolean, nullable=False, default=False)
    content_type = Column(String, nullable=False, default="programming")  # "programming" or "events"
    deleted_at = Column(DateTime, nullable=True, default=None)


    modules = relationship("Module", back_populates="course", order_by="Module.order_index")


class CourseAssignment(Base):
    __tablename__ = "course_assignments"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    assignment_type = Column(String, nullable=False)  # "user", "group", "position", "unit", "year"
    value = Column(String, nullable=False)


class Module(Base):
    __tablename__ = "modules"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False, default=0)

    course = relationship("Course", back_populates="modules")
    surveys = relationship("Survey", back_populates="module")
    attachments = relationship("Attachment")    


class Survey(Base):
    __tablename__ = "surveys"
    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=False)
    question = Column(String, nullable=False)
    survey_type = Column(String, nullable=False, default="multiple_choice")  # "multiple_choice" or "open_response"

    module = relationship("Module", back_populates="surveys")
    options = relationship("SurveyOption", back_populates="survey")


class SurveyOption(Base):
    __tablename__ = "survey_options"
    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("surveys.id"), nullable=False)
    label = Column(String, nullable=False)

    survey = relationship("Survey", back_populates="options")

class SurveyAnswer(Base):
    __tablename__ = "survey_answers"
    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("surveys.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    option_id = Column(Integer, ForeignKey("survey_options.id"), nullable=True)
    answer_text = Column(String, nullable=True)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)

class StaffDuty(Base):
    __tablename__ = "staff_duties"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False, default="not_started")  # not_started, in_progress, done

    assignee = relationship("User", foreign_keys=[assigned_to])

class StaffTrackerItem(Base):
    __tablename__ = "staff_tracker_items"
    id = Column(Integer, primary_key=True, index=True)
    item_type = Column(String, nullable=False)  # "meeting" or "event"
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    item_date = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

class StaffUpdate(Base):
    __tablename__ = "staff_updates"
    id = Column(Integer, primary_key=True, index=True)
    tracker_item_id = Column(Integer, ForeignKey("staff_tracker_items.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    note = Column(String, nullable=False)
    posted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")

class ProjectBoard(Base):
    __tablename__ = "project_boards"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)


class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id = Column(Integer, primary_key=True, index=True)
    board_id = Column(Integer, ForeignKey("project_boards.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    due_date = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="todo")  # todo, in_progress, done

    assignee = relationship("User")


class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    is_public = Column(Boolean, nullable=False, default=False)
    is_pinned = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    images = relationship("AnnouncementImage")


class AnnouncementAssignment(Base):
    __tablename__ = "announcement_assignments"
    id = Column(Integer, primary_key=True, index=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False)
    assignment_type = Column(String, nullable=False)  # "user", "group", "position", "unit", "year"
    value = Column(String, nullable=False)


class AnnouncementImage(Base):
    __tablename__ = "announcement_images"
    id = Column(Integer, primary_key=True, index=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False)
    file_path = Column(String, nullable=False)

class PartnerCategory(Base):
    __tablename__ = "partner_categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)


class Partner(Base):
    __tablename__ = "partners"
    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("partner_categories.id"), nullable=False)
    name = Column(String, nullable=False)
    contact_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    description = Column(String, nullable=True)

class StickyNote(Base):
    __tablename__ = "sticky_notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(String, nullable=True)
    color = Column(String, nullable=False, default="#fef08a")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    target_type = Column(String, nullable=False)
    target_id = Column(Integer, nullable=True)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Touchpoint(Base):
    __tablename__ = "touchpoints"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    logged_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    meeting_type = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class CommunityServiceLog(Base):
    __tablename__ = "community_service_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hours = Column(Float, nullable=False)
    organization = Column(String, nullable=False)
    description = Column(String, nullable=True)
    service_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class StandaloneSurvey(Base):
    __tablename__ = "standalone_surveys"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(String, nullable=False)
    survey_type = Column(String, nullable=False, default="multiple_choice")
    is_public = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class StandaloneSurveyOption(Base):
    __tablename__ = "standalone_survey_options"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("standalone_surveys.id"), nullable=False)
    label = Column(String, nullable=False)


class StandaloneSurveyAssignment(Base):
    __tablename__ = "standalone_survey_assignments"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("standalone_surveys.id"), nullable=False)
    assignment_type = Column(String, nullable=False)
    value = Column(String, nullable=False)


class StandaloneSurveyAnswer(Base):
    __tablename__ = "standalone_survey_answers"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("standalone_surveys.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    option_id = Column(Integer, ForeignKey("standalone_survey_options.id"), nullable=True)
    answer_text = Column(String, nullable=True)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))