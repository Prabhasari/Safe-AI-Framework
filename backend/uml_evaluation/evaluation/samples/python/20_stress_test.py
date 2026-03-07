# SAMPLE 20 — python_stress_test
# COMPLEXITY: very high
# SIMULATES: a large realistic AI-generated student management module with ALL
#             challenge types combined: deep inheritance, complex generics,
#             messy style, incomplete parts, dense relationship web
# CHALLENGE: this is the hardest sample — expect both methods to drop below 100%
#            The gap between regex and AI scores should be most visible here
# EXPECTED: 6 classes, 22+ fields, 22+ methods, 10+ relationships

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple


# ── Level 1: Root ABC ─────────────────────────────────────────────

class BaseEntity(ABC):
    def __init__(self, uid: str):
        self.uid: str = uid
        self.created_at: str = ""

    @abstractmethod
    def validate(self) -> bool:
        pass

    def get_uid(self) -> str:
        return self.uid


# ── Level 2: Person ───────────────────────────────────────────────

class Person(BaseEntity):
    def __init__(self, uid: str, name: str, contact: str):
        super().__init__(uid)
        self.name: str = name
        self.contact: str = contact
        self.metadata: Dict[str, str] = {}   # generic dict field

    def validate(self) -> bool:
        return bool(self.name and self.contact)

    def get_name(self) -> str:
        return self.name

    def add_metadata(self, key: str, value: str) -> None:
        self.metadata[key] = value


# ── Level 3: Student (inherits Person) ───────────────────────────

class Student(Person):
    def __init__(self, uid: str, name: str, contact: str, program: str):
        super().__init__(uid, name, contact)
        self.program: str = program
        self.semester_grades: Dict[str, List[float]] = {}  # nested generic
        self.enrolled_modules: List[str] = []

    def validate(self) -> bool:
        return super().validate() and bool(self.program)

    def add_grade(self, semester: str, grade: float) -> None:
        self.semester_grades.setdefault(semester, []).append(grade)

    def get_cgpa(self) -> float:
        all_grades = [g for grades in self.semester_grades.values() for g in grades]
        return sum(all_grades) / len(all_grades) if all_grades else 0.0

    def get_program(self) -> str:
        return self.program


# ── Assessment (separate class, associated with Student) ──────────

class Assessment:
    def __init__(self, assessment_id: str, title: str, total_marks: float):
        self.assessment_id: str = assessment_id
        self.title: str = title
        self.total_marks: float = total_marks
        self.submissions: Dict[str, float] = {}   # studentId -> score

    def submit(self, student_id: str, score: float) -> None:
        self.submissions[student_id] = score

    def get_score(self, student_id: str) -> Optional[float]:
        return self.submissions.get(student_id)

    def get_average(self) -> float:
        if not self.submissions:
            return 0.0
        return sum(self.submissions.values()) / len(self.submissions)

    def get_assessment_id(self) -> str:
        return self.assessment_id


# ── Module (aggregates Assessments, relates to Students) ──────────

class Module:
    def __init__(self, module_id: str, title: str, credits: int):
        self.module_id: str = module_id
        self.title: str = title
        self.credits: int = credits
        self.assessments: List[Assessment] = []
        self.enrolled_students: List[Student] = []

    def add_assessment(self, assessment: Assessment) -> None:
        self.assessments.append(assessment)

    def enroll_student(self, student: Student) -> bool:
        if student not in self.enrolled_students:
            self.enrolled_students.append(student)
            return True
        return False

    def get_module_average(self) -> float:
        avgs = [a.get_average() for a in self.assessments]
        return sum(avgs) / len(avgs) if avgs else 0.0

    def get_module_id(self) -> str:
        return self.module_id

    def get_enrolled_count(self) -> int:
        return len(self.enrolled_students)


# ── AcademicService (orchestrates everything) ─────────────────────

class AcademicService:
    def __init__(self):
        self.students: Dict[str, Student] = {}
        self.modules: Dict[str, Module] = {}
        # field set later — AI-generated pattern
        self.current_semester: str = ""

    def register_student(self, student: Student) -> None:
        if student.validate():
            self.students[student.uid] = student

    def add_module(self, module: Module) -> None:
        self.modules[module.module_id] = module

    def enroll(self, student_uid: str, module_id: str) -> bool:
        student = self.students.get(student_uid)
        module  = self.modules.get(module_id)
        if not student or not module:
            return False
        return module.enroll_student(student)

    def get_student_report(self, student_uid: str) -> Optional[Dict[str, float]]:
        student = self.students.get(student_uid)
        if not student:
            return None
        return student.semester_grades.get(self.current_semester, {})  # type: ignore

    def get_top_students(self, n: int) -> List[Tuple[str, float]]:
        ranked = sorted(
            [(uid, s.get_cgpa()) for uid, s in self.students.items()],
            key=lambda x: x[1], reverse=True
        )
        return ranked[:n]