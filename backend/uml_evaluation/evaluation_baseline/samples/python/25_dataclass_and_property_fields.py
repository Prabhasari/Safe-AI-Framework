# SAMPLE 25 — python_dataclass_and_property_fields (v2)
# COMPLEXITY: high
#
# WHY BASELINE FAILS:
#   1. @dataclass fields are declared at CLASS level (not in __init__),
#      so baseline's __init__-only scanning completely misses them.
#   2. @property decorated methods look like regular methods to regex,
#      but the AST knows they are property accessors (not counted as methods).
#   3. ClassVar and field() defaults are invisible to simple regex.
#
# CIR AST adapter detects @dataclass and extracts class-level annotations.
# Baseline only sees __init__ — dataclass has no explicit __init__,
# so baseline finds ZERO fields for dataclass classes.
#
# EXPECTED: classes=3, fields=14, methods=11, rels=4
# Baseline will score ~0% field recall on the two dataclass classes.

from dataclasses import dataclass, field
from typing import List, Optional, ClassVar


@dataclass
class CourseInfo:
    # Dataclass fields — NO __init__ written by developer
    # Baseline finds zero fields here because there is no __init__ to scan
    course_id: str
    title: str
    credits: int
    max_students: int = 30
    is_active: bool = True
    tags: List[str] = field(default_factory=list)

    # Class variable — not an instance field
    VALID_CREDITS: ClassVar[List[int]] = [1, 2, 3, 4]

    def get_course_id(self) -> str:
        return self.course_id

    def get_summary(self) -> str:
        return f"{self.course_id}: {self.title} ({self.credits} cr)"

    def is_full(self, enrolled: int) -> bool:
        return enrolled >= self.max_students


@dataclass
class EnrollmentEntry:
    # Another dataclass — baseline misses all fields
    entry_id: str
    student_id: str
    course: CourseInfo           # relationship — baseline misses because no __init__
    grade: Optional[float] = None
    passed: bool = False

    def set_grade(self, grade: float) -> None:
        self.grade = grade
        self.passed = grade >= 50.0

    def get_entry_id(self) -> str:
        return self.entry_id

    def is_graded(self) -> bool:
        return self.grade is not None


class EnrollmentRegistry:
    def __init__(self):
        self.entries: List[EnrollmentEntry] = []   # normal __init__ — baseline OK here
        self.courses: List[CourseInfo] = []

    def add_entry(self, entry: EnrollmentEntry) -> None:
        self.entries.append(entry)

    def add_course(self, course: CourseInfo) -> None:
        self.courses.append(course)

    def get_entries_for_student(self, student_id: str) -> List[EnrollmentEntry]:
        return [e for e in self.entries if e.student_id == student_id]

    def get_course(self, course_id: str) -> Optional[CourseInfo]:
        return next((c for c in self.courses if c.course_id == course_id), None)

    def get_all_courses(self) -> List[CourseInfo]:
        return self.courses