# SAMPLE 10 — python_student_grade_report
# COMPLEXITY: high
# TESTS: deep association chain, Optional types, multiple List fields

from typing import List, Optional


class Course:
    def __init__(self, course_id: str, title: str, credits: int):
        self.course_id: str = course_id
        self.title: str = title
        self.credits: int = credits
        self.max_students: int = 30

    def get_course_id(self) -> str:
        return self.course_id

    def get_title(self) -> str:
        return self.title

    def get_credits(self) -> int:
        return self.credits


class Assessment:
    def __init__(self, assessment_id: str, title: str, max_score: float):
        self.assessment_id: str = assessment_id
        self.title: str = title
        self.max_score: float = max_score
        self.weight: float = 0.0

    def get_assessment_id(self) -> str:
        return self.assessment_id

    def get_title(self) -> str:
        return self.title

    def get_weight(self) -> float:
        return self.weight

    def set_weight(self, weight: float) -> None:
        self.weight = weight


class GradeRecord:
    def __init__(self, student_id: str, course: Course, assessment: Assessment):
        self.student_id: str = student_id
        self.course: Course = course
        self.assessment: Assessment = assessment
        self.score: float = 0.0
        self.submitted: bool = False

    def get_score(self) -> float:
        return self.score

    def set_score(self, score: float) -> None:
        self.score = score
        self.submitted = True

    def get_percentage(self) -> float:
        if self.assessment.max_score == 0:
            return 0.0
        return (self.score / self.assessment.max_score) * 100

    def is_submitted(self) -> bool:
        return self.submitted


class Student:
    def __init__(self, student_id: str, name: str, email: str):
        self.student_id: str = student_id
        self.name: str = name
        self.email: str = email
        self.grade_records: List[GradeRecord] = []

    def add_grade_record(self, record: GradeRecord) -> None:
        self.grade_records.append(record)

    def get_grade_records(self) -> List[GradeRecord]:
        return self.grade_records

    def calculate_gpa(self) -> float:
        if not self.grade_records:
            return 0.0
        total = sum(r.get_percentage() for r in self.grade_records)
        return round(total / len(self.grade_records), 2)

    def get_student_id(self) -> str:
        return self.student_id

    def get_name(self) -> str:
        return self.name


class GradeReportService:
    def __init__(self):
        self._students: dict = {}

    def get_report(self, student_id: str) -> Optional[Student]:
        return self._students.get(student_id)

    def record_score(self, student: Student, record: GradeRecord) -> None:
        student.add_grade_record(record)

    def get_top_students(self, min_gpa: float) -> List[Student]:
        return [s for s in self._students.values() if s.calculate_gpa() >= min_gpa]

    def get_course_average(self, course_id: str) -> float:
        records = [
            r for s in self._students.values()
            for r in s.grade_records
            if r.course.course_id == course_id
        ]
        if not records:
            return 0.0
        return sum(r.get_percentage() for r in records) / len(records)