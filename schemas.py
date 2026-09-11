from pydantic import BaseModel
from datetime import date, datetime

class UserCreate(BaseModel):
    name: str
    jersey_number: int
    position: str
    year: int
    email:str
    birthday: date | None = None
    is_offense: bool = False
    is_defense: bool = False
    is_special_teams: bool = False
    role: str = "player"
    
class UserResponse(BaseModel):
    id: int
    name: str
    jersey_number: int
    position: str
    year: int
    role: str
    is_offense: bool
    is_defense: bool
    is_special_teams: bool
    birthday: date | None
    is_super_admin: bool


class config:
    from_attributes = True

class UserUpdate(BaseModel):
    name: str | None = None
    jersey_number: int | None = None
    position: str | None = None
    year: int | None = None
    is_offense: bool | None = None
    is_defense: bool | None = None
    is_special_teams: bool | None = None
    birthday: date | None = None

class ClaimAccount(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class QuestionCreate(BaseModel):
    question_text: str
    question_type: str = "rating"
    category: str | None = None
    value_points: int | None = None

class AnswerOptionResponse(BaseModel):
    id: int
    question_id: int
    label: str
    value: int

    class Config:
        from_attributes = True

class QuestionResponse(BaseModel):
    id: int
    assessment_id: int
    question_text: str
    question_type: str
    category: str | None
    value_points: int | None
    options: list[AnswerOptionResponse] = []

    class Config:
        from_attributes = True

class QuestionUpdate(BaseModel):
    question_text: str | None = None
    question_type: str | None = None
    category: str | None = None
    value_points: int | None = None
    class Config:
        from_attributes = True

class AssessmentAssignmentInput(BaseModel):
    assignment_type: str
    value: str

class AssessmentCreate(BaseModel):
    title: str
    description: str | None = None
    is_public: bool = False
    assessment_type: str = "player"
    assignments: list[AssessmentAssignmentInput] = []

class AssessmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_public: bool | None = None


class AssessmentResponse(BaseModel):
    id: int
    title: str
    description: str | None
    created_by: int
    is_public: bool
    assessment_type: str
    questions: list[QuestionResponse] = []

    class Config:
        from_attributes = True

class SubmitAnswer(BaseModel):
    question_id: int
    answer_value: int | None = None
    answer_text: str | None = None
    time_taken_seconds: float | None = None

class SubmitAttempt(BaseModel):
    answers: list[SubmitAnswer]
    duration_seconds: float | None = None

class AttemptResponse(BaseModel):
    id: int
    assessment_id: int
    user_id: int
    total_score: int
    level: str
    submitted_at: datetime

    class Config:
        from_attributes = True

class ResponseCreate(BaseModel):
    question_id: int
    answer_value: int | None = None
    answer_text: str | None = None

class ResponseOut(BaseModel):
    id: int
    user_id: int
    question_id: int
    answer_value: int | None
    answer_text: str | None

    class Config:
        from_attributes = True

class AnswerOptionCreate(BaseModel):
    label: str
    value: int

class EventCreate(BaseModel):
    title: str
    description: str | None = None
    event_date: datetime
    is_public: bool = False

class EventResponse(BaseModel):
    id: int
    created_by: int
    title: str
    description: str | None
    event_date: datetime
    is_public: bool

    class Config:
        from_attributes = True

class GroupCreate(BaseModel):
    name: str
    member_ids: list[int] = []

class GroupResponse(BaseModel):
    id: int
    name: str
    created_by: int
    member_ids: list[int] = []

    class Config:
        from_attributes = True


class SurveyOptionCreate(BaseModel):
    label: str

class SurveyOptionResponse(BaseModel):
    id: int
    label: str

    class Config:
        from_attributes = True


class SurveyCreate(BaseModel):
    question: str
    survey_type: str = "multiple_choice"
    options: list[str] = []

class SurveyResponse(BaseModel):
    id: int
    question: str
    survey_type: str
    options: list[SurveyOptionResponse] = []

    class Config:
        from_attributes = True

class SurveyAnswerCreate(BaseModel):
    option_id: int | None = None
    answer_text: str | None = None

class SurveyAnswerResponse(BaseModel):
    id: int
    survey_id: int
    user_id: int
    option_id: int | None
    answer_text: str | None
    submitted_at: datetime

    class Config:
        from_attributes = True

class ModuleCreate(BaseModel):
    title: str
    content: str | None = None
    order_index: int = 0

class ModuleResponse(BaseModel):
    id: int
    course_id: int
    title: str
    content: str | None
    order_index: int
    surveys: list[SurveyResponse] = []

    class Config:
        from_attributes = True


class CourseAssignmentInput(BaseModel):
    assignment_type: str  # "user", "group", "position", "unit", "year"
    value: str

class CourseCreate(BaseModel):
    title: str
    description: str | None = None
    is_public: bool = False
    content_type: str = "programming"
    assignments: list[CourseAssignmentInput] = []

class CourseResponse(BaseModel):
    id: int
    title: str
    description: str | None
    created_by: int
    is_public: bool
    content_type: str
    modules: list[ModuleResponse] = []

    class Config:
        from_attributes = True

class CourseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_public: bool | None = None

class ModuleResponse(BaseModel):
    id: int
    course_id: int
    title: str
    content: str | None
    order_index: int
    surveys: list[SurveyResponse] = []
    attachments: list[AttachmentResponse] = []

    class Config:
        from_attributes = True

class AttachmentResponse(BaseModel):
    id: int
    module_id: int
    filename: str
    file_path: str

    class Config:
        from_attributes = True

class StaffDutyCreate(BaseModel):
    title: str
    description: str | None = None
    assigned_to: int | None = None
    status: str = "not_started"

class StaffDutyUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    assigned_to: int | None = None
    status: str | None = None

class StaffDutyResponse(BaseModel):
    id: int
    title: str
    description: str | None
    assigned_to: int | None
    created_by: int
    status: str

    class Config:
        from_attributes = True

class TrackerItemCreate(BaseModel):
    item_type: str  # "meeting" or "event"
    title: str
    description: str | None = None
    item_date: datetime | None = None

class TrackerItemResponse(BaseModel):
    id: int
    item_type: str
    title: str
    description: str | None
    item_date: datetime | None
    created_by: int

    class Config:
        from_attributes = True

class StaffUpdateCreate(BaseModel):
    note: str

class StaffUpdateResponse(BaseModel):
    id: int
    tracker_item_id: int
    user_id: int
    user_name: str
    note: str
    posted_at: datetime

    class Config:
        from_attributes = True


class ProjectBoardCreate(BaseModel):
    title: str
    description: str | None = None
    course_id: int | None = None

class ProjectBoardResponse(BaseModel):
    id: int
    title: str
    description: str | None
    course_id: int | None
    created_by: int

    class Config:
        from_attributes = True


class ProjectTaskCreate(BaseModel):
    title: str
    description: str | None = None
    assigned_to: int | None = None
    due_date: datetime | None = None
    status: str = "todo"

class ProjectTaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    assigned_to: int | None = None
    due_date: datetime | None = None
    status: str | None = None

class ProjectTaskResponse(BaseModel):
    id: int
    board_id: int
    title: str
    description: str | None
    assigned_to: int | None
    due_date: datetime | None
    status: str

    class Config:
        from_attributes = True

class AnnouncementAssignmentInput(BaseModel):
    assignment_type: str
    value: str

class AnnouncementImageResponse(BaseModel):
    id: int
    file_path: str

    class Config:
        from_attributes = True

class AnnouncementCreate(BaseModel):
    title: str
    body: str | None = None
    is_public: bool = False
    is_pinned: bool = False
    assignments: list[AnnouncementAssignmentInput] = []

class AnnouncementUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    is_public: bool | None = None
    is_pinned: bool | None = None

class AnnouncementResponse(BaseModel):
    id: int
    title: str
    body: str | None
    is_public: bool
    is_pinned: bool
    created_by: int
    created_at: datetime
    images: list[AnnouncementImageResponse] = []

    class Config:
        from_attributes = True

class PartnerCategoryCreate(BaseModel):
    name: str

class PartnerCategoryResponse(BaseModel):
    id: int
    name: str
    created_by: int

    class Config:
        from_attributes = True


class PartnerCreate(BaseModel):
    name: str
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    description: str | None = None

class PartnerUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    description: str | None = None

class PartnerResponse(BaseModel):
    id: int
    category_id: int
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    description: str | None

    class Config:
        from_attributes = True

class StickyNoteCreate(BaseModel):
    content: str | None = None
    color: str = "#fef08a"

class StickyNoteUpdate(BaseModel):
    content: str | None = None
    color: str | None = None

class StickyNoteResponse(BaseModel):
    id: int
    user_id: int
    content: str | None
    color: str
    created_at: datetime

    class Config:
        from_attributes = True

class AuditLogResponse(BaseModel):
    id: int
    actor_id: int
    action: str
    target_type: str
    target_id: int | None
    reason: str | None
    created_at: datetime

    class Config:
        from_attributes = True

class TouchpointCreate(BaseModel):
    user_id: int
    meeting_type: str
    notes: str | None = None

class TouchpointResponse(BaseModel):
    id: int
    user_id: int
    logged_by: int
    meeting_type: str
    notes: str | None
    created_at: datetime

    class Config:
        from_attributes = True

class ResumeResponse(BaseModel):
    id: int
    user_id: int
    filename: str
    file_path: str
    uploaded_at: datetime

    class Config:
        from_attributes = True

class CommunityServiceCreate(BaseModel):
    hours: float
    organization: str
    description: str | None = None
    service_date: date

class CommunityServiceResponse(BaseModel):
    id: int
    user_id: int
    hours: float
    organization: str
    description: str | None
    service_date: date
    created_at: datetime

    class Config:
        from_attributes = True


class StandaloneSurveyAssignmentInput(BaseModel):
    assignment_type: str
    value: str

class StandaloneSurveyOptionResponse(BaseModel):
    id: int
    label: str

    class Config:
        from_attributes = True

class StandaloneSurveyCreate(BaseModel):
    question: str
    survey_type: str = "multiple_choice"
    is_public: bool = False
    options: list[str] = []
    assignments: list[StandaloneSurveyAssignmentInput] = []

class StandaloneSurveyResponse(BaseModel):
    id: int
    question: str
    survey_type: str
    is_public: bool
    created_by: int
    created_at: datetime
    options: list[StandaloneSurveyOptionResponse] = []

    class Config:
        from_attributes = True

class StandaloneSurveyAnswerCreate(BaseModel):
    option_id: int | None = None
    answer_text: str | None = None

class StandaloneSurveyAnswerResponse(BaseModel):
    id: int
    survey_id: int
    user_id: int
    option_id: int | None
    answer_text: str | None
    submitted_at: datetime

    class Config:
        from_attributes = True
