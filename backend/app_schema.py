from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from core import IST, now_utc

MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"
MOBILE = r"^(\+91)?[6-9]\d{9}$"
EXAMS = ["CAT", "XAT", "CMAT", "GMAT", "MAH-CET", "NMAT", "ATMA"]


def _today() -> date:
    return now_utc().astimezone(IST).date()


class Personal(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    dob: date
    gender: Literal["Male", "Female", "Other"]
    category: Literal["General", "OBC-NCL", "SC", "ST", "EWS"]
    nationality: Literal["Indian", "NRI", "OCI", "Foreign National"]
    pwd: bool = False

    @field_validator("dob")
    @classmethod
    def age(cls, v: date):
        t = _today()
        years = t.year - v.year - ((t.month, t.day) < (v.month, v.day))
        if not 18 <= years <= 45:
            raise ValueError("Age must be between 18 and 45 years")
        return v


class Sibling(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    relation: Literal["Brother", "Sister"]
    occupation: str = Field(default="", max_length=100)


class Family(BaseModel):
    father_name: str = Field(min_length=2, max_length=100)
    father_occupation: str = Field(min_length=2, max_length=100)
    mother_name: str = Field(min_length=2, max_length=100)
    mother_occupation: str = Field(min_length=2, max_length=100)
    annual_family_income_inr: float = Field(ge=0, le=1_000_000_000)
    siblings: list[Sibling] = Field(default=[], max_length=6)


class Contact(BaseModel):
    address_line1: str = Field(min_length=5, max_length=200)
    address_line2: str = Field(default="", max_length=200)
    city: str = Field(min_length=2, max_length=60)
    state: str = Field(min_length=2, max_length=60)
    pincode: str = Field(pattern=r"^[1-9]\d{5}$")
    alternate_mobile: str = Field(default="", pattern=r"^$|^(\+91)?[6-9]\d{9}$")
    emergency_contact_name: str = Field(min_length=2, max_length=100)
    emergency_contact_mobile: str = Field(pattern=MOBILE)


class School(BaseModel):
    board: str = Field(min_length=2, max_length=100)
    school: str = Field(min_length=2, max_length=150)
    year: int = Field(ge=1990, le=2026)
    percentage: float = Field(ge=33, le=100)


class Graduation(BaseModel):
    degree: str = Field(min_length=2, max_length=60)
    discipline: str = Field(min_length=2, max_length=100)
    university: str = Field(min_length=2, max_length=150)
    status: Literal["completed", "final_year"]
    year: int = Field(ge=1995, le=2027)
    score_type: Literal["percentage", "cgpa"]
    score: float = Field(gt=0)

    @model_validator(mode="after")
    def score_range(self):
        cap = 100 if self.score_type == "percentage" else 10
        if self.score > cap:
            raise ValueError(f"graduation.score: must be at most {cap} for {self.score_type}")
        return self


class Education(BaseModel):
    class_x: School
    class_xii: School
    graduation: Graduation

    @model_validator(mode="after")
    def years(self):
        if self.class_xii.year < self.class_x.year + 2:
            raise ValueError("class_xii.year: Class XII year must be at least 2 years after Class X")
        if self.graduation.year < self.class_xii.year + 3:
            raise ValueError("graduation.year: Graduation year must be at least 3 years after Class XII")
        return self


class Experience(BaseModel):
    organization: str = Field(min_length=2, max_length=150)
    designation: str = Field(min_length=2, max_length=100)
    sector: str = Field(min_length=2, max_length=60)
    start: str = Field(pattern=MONTH)
    end: str = Field(default="", pattern=r"^$|^\d{4}-(0[1-9]|1[0-2])$")

    @model_validator(mode="after")
    def order(self):
        now = _today().strftime("%Y-%m")
        if self.start > now:
            raise ValueError("start: Start month cannot be in the future")
        if self.end and self.end < self.start:
            raise ValueError("end: End month cannot be before start month")
        return self


def months(e: Experience) -> int:
    end = e.end or _today().strftime("%Y-%m")
    (y1, m1), (y2, m2) = map(int, e.start.split("-")), map(int, end.split("-"))
    return max(0, (y2 - y1) * 12 + (m2 - m1))


class Work(BaseModel):
    has_experience: bool
    experiences: list[Experience] = Field(default=[], max_length=8)

    @model_validator(mode="after")
    def consistency(self):
        if self.has_experience and not self.experiences:
            raise ValueError("experiences: Add at least one experience or choose 'No work experience'")
        if not self.has_experience and self.experiences:
            raise ValueError("experiences: Remove experiences or choose 'I have work experience'")
        return self


class Exam(BaseModel):
    exam: Literal[tuple(EXAMS)]
    year: int = Field(ge=2024, le=2027)
    roll_number: str = Field(pattern=r"^[A-Za-z0-9\-/]{4,30}$")
    status: Literal["appeared", "awaiting_result", "registered"]
    score: Optional[float] = Field(default=None, ge=0, le=1000)
    percentile: Optional[float] = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def result(self):
        if self.status == "appeared" and self.score is None and self.percentile is None:
            raise ValueError("percentile: Enter a score or percentile for an appeared exam")
        return self


class Exams(BaseModel):
    exams: list[Exam] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def unique(self):
        keys = [(e.exam, e.year) for e in self.exams]
        if len(keys) != len(set(keys)):
            raise ValueError("exams: Each exam and year can be listed only once")
        return self


class Preferences(BaseModel):
    ranked: list[str] = Field(min_length=1, max_length=5)

    @field_validator("ranked")
    @classmethod
    def unique(cls, v: list[str]):
        if len(v) != len(set(v)):
            raise ValueError("Each programme can appear only once in your preferences")
        return v


SECTIONS = {
    "personal": ("Personal details", Personal), "family": ("Family", Family), "contact": ("Contact", Contact),
    "education": ("Education", Education), "work": ("Work experience", Work),
    "exams": ("Entrance exams", Exams), "preferences": ("Programme preferences", Preferences),
}

DECLARATION_PGDM = {
    "version": "PGDM-DECL-2026-28-v1",
    "text": ("I declare that the information furnished in my application is true and complete. I understand that "
             "admission is provisional and subject to verification of original documents, and that any false "
             "information may lead to cancellation of my candidature or admission at any stage."),
}
ESSAYS = [
    {"id": "e1", "prompt": "Describe a situation where you led a team through a difficult challenge. What did you learn?",
     "min_words": 100, "max_words": 300},
    {"id": "e2", "prompt": "Why WeSchool, and how does your chosen programme fit your career goals for the next five years?",
     "min_words": 100, "max_words": 300},
]
PIQ = [
    {"id": "strengths", "label": "Your three key strengths, with an example of each"},
    {"id": "goals", "label": "Short-term and long-term career goals"},
    {"id": "achievement", "label": "An achievement you are proud of"},
    {"id": "interests", "label": "Hobbies and extra-curricular interests"},
]
GRAD_DECL_VERSION = "GRAD-ELIG-2026-28-v1"


class GraduationEligibility(BaseModel):
    graduation_status: Literal["completed", "final_year"]
    expected_completion: str = Field(default="", pattern=r"^$|^\d{4}-(0[1-9]|1[0-2])$")
    meets_min_aggregate: bool
    has_active_backlogs: bool
    accept: bool

    @model_validator(mode="after")
    def rules(self):
        if self.graduation_status == "final_year" and not self.expected_completion:
            raise ValueError("expected_completion: Enter expected completion month for final-year candidates")
        if not self.accept:
            raise ValueError("accept: You must accept the declaration")
        return self
