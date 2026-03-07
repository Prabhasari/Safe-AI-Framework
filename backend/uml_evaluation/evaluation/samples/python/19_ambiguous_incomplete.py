# SAMPLE 19 — python_ambiguous_incomplete
# COMPLEXITY: medium-high
# SIMULATES: realistic vibe coding output — AI left stubs, missing type hints,
#             pass bodies, inconsistent field initialization, dynamic attributes
# CHALLENGE: fields set outside __init__ (in other methods) are hard for regex
#            to detect; AI may hallucinate what the TODO methods should do
# EXPECTED: 3 classes, 8 fields, 11 methods, 2 relationships
#           (some fields intentionally hard to detect — expect <100% recall)

from typing import List, Optional


class Student:
    def __init__(self, student_id: str, name: str):
        self.student_id: str = student_id
        self.name: str = name
        # AI forgot to initialize these in __init__

    def set_email(self, email: str) -> None:
        self.email = email   # field defined outside __init__ — regex challenge

    def set_year(self, year: int) -> None:
        self.year = year     # same — set dynamically

    def get_student_id(self) -> str:
        return self.student_id

    def get_name(self) -> str:
        return self.name

    def to_dict(self):   # missing return type — AI omission
        pass  # TODO: implement serialization


class EnrollmentRecord:
    def __init__(self, record_id: str):
        self.record_id: str = record_id
        self.student = None      # no type hint — AI left it untyped
        self.course_ids = []     # no type hint
        self.status: str = "pending"

    def assign_student(self, student: Student) -> None:
        self.student = student

    def add_course(self, course_id: str) -> None:
        self.course_ids.append(course_id)

    def get_status(self) -> str:
        return self.status

    def activate(self) -> None:
        self.status = "active"

    def get_record_id(self) -> str:
        return self.record_id


class RegistrationSystem:
    def __init__(self):
        self.records: List[EnrollmentRecord] = []
        self.active: bool = True

    def create_record(self, student: Student) -> EnrollmentRecord:
        # TODO: add validation
        record = EnrollmentRecord(f"REC{len(self.records)}")
        record.assign_student(student)
        self.records.append(record)
        return record

    def get_all_records(self) -> List[EnrollmentRecord]:
        return self.records

    def find_record(self, record_id: str) -> Optional[EnrollmentRecord]:
        # TODO: implement properly
        pass

    def deactivate(self) -> None:
        self.active = False