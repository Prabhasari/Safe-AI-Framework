# SAMPLE 24 — python_dynamic_fields_outside_init (v2)
# COMPLEXITY: medium-high
#
# WHY BASELINE FAILS:
#   The baseline only scans __init__ for self.x = ... assignments.
#   This class intentionally initializes MOST fields outside __init__,
#   in separate setup methods. The AST-based CIR traverses ALL method
#   bodies so it captures every self.x assignment site.
#
# CIR should detect: student_id, name, status, advisor, department,
#                    activated_at, score, remarks  (8 fields)
# Baseline detects:  student_id, name only  (2 fields from __init__)
#
# EXPECTED for evaluation:
#   classes=3, fields=12, methods=13, rels=3
#   Baseline will miss ~8 fields and 2 relationships → F1 drops significantly

from typing import Optional, List


class Student:
    def __init__(self, student_id: str, name: str):
        self.student_id: str = student_id
        self.name: str = name
        # All other fields are set via setup methods — baseline misses all of these

    def setup_profile(self, department: str, year: int) -> None:
        self.department: str = department      # field outside __init__
        self.year: int = year                  # field outside __init__
        self.status: str = "pending"           # field outside __init__

    def activate(self) -> None:
        self.status = "active"
        self.activated_at: str = "now"         # field outside __init__

    def assign_advisor(self, advisor: "Advisor") -> None:
        self.advisor: Advisor = advisor        # typed field outside __init__ — relationship!

    def get_student_id(self) -> str:
        return self.student_id

    def get_name(self) -> str:
        return self.name

    def get_status(self) -> str:
        return getattr(self, "status", "unknown")

    def deactivate(self) -> None:
        self.status = "inactive"


class Advisor:
    def __init__(self, advisor_id: str, name: str, department: str):
        self.advisor_id: str = advisor_id
        self.name: str = name
        self.department: str = department
        self.advisees: List[Student] = []      # List[Student] → associates edge

    def add_advisee(self, student: Student) -> None:
        self.advisees.append(student)

    def get_advisor_id(self) -> str:
        return self.advisor_id

    def get_name(self) -> str:
        return self.name

    def get_department(self) -> str:
        return self.department

    def get_advisee_count(self) -> int:
        return len(self.advisees)


class AdvisoryRecord:
    def __init__(self, record_id: str):
        self.record_id: str = record_id
        self.notes: List[str] = []

    def load_profile(self, data: dict) -> None:
        # Fields set from external data — baseline cannot detect these at all
        self.student_id: str = data.get("student_id", "")
        self.advisor_id: str = data.get("advisor_id", "")
        self.created_at: str = data.get("created_at", "")
        self.semester: str   = data.get("semester", "")

    def add_note(self, note: str) -> None:
        self.notes.append(note)

    def get_record_id(self) -> str:
        return self.record_id

    def get_notes(self) -> List[str]:
        return self.notes

    def is_complete(self) -> bool:
        return bool(getattr(self, "student_id", None))