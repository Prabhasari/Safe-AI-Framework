# SAMPLE 18 — python_deep_inheritance
# COMPLEXITY: high
# CHALLENGE: 4-level inheritance chain in Python — ABC at root, two intermediate
#             abstract classes, one concrete class at the bottom
#             Both methods must correctly capture all INHERITS edges without
#             collapsing the chain or missing intermediate classes
# EXPECTED: 1 ABC, 2 abstract classes, 2 concrete classes = 5 classes,
#           14 fields, 15 methods, 5 INHERITS edges

from abc import ABC, abstractmethod
from typing import List, Optional


class Entity(ABC):
    def __init__(self, entity_id: str):
        self.entity_id: str = entity_id

    @abstractmethod
    def get_type(self) -> str:
        pass

    def get_entity_id(self) -> str:
        return self.entity_id


class Person(Entity):
    def __init__(self, entity_id: str, name: str, email: str):
        super().__init__(entity_id)
        self.name: str = name
        self.email: str = email

    @abstractmethod
    def get_type(self) -> str:
        pass

    def get_name(self) -> str:
        return self.name

    def get_email(self) -> str:
        return self.email

    def update_email(self, email: str) -> None:
        self.email = email


class AcademicPerson(Person):
    def __init__(self, entity_id: str, name: str, email: str, department: str):
        super().__init__(entity_id, name, email)
        self.department: str = department
        self.academic_year: str = ""

    @abstractmethod
    def get_type(self) -> str:
        pass

    @abstractmethod
    def get_max_courses(self) -> int:
        pass

    def get_department(self) -> str:
        return self.department

    def set_academic_year(self, year: str) -> None:
        self.academic_year = year


class Student(AcademicPerson):
    def __init__(self, entity_id: str, name: str, email: str, department: str):
        super().__init__(entity_id, name, email, department)
        self.gpa: float = 0.0
        self.enrollment_status: str = "active"

    def get_type(self) -> str:
        return "student"

    def get_max_courses(self) -> int:
        return 6

    def get_gpa(self) -> float:
        return self.gpa

    def update_gpa(self, gpa: float) -> None:
        self.gpa = gpa

    def get_enrollment_status(self) -> str:
        return self.enrollment_status


class ResearchStudent(Student):
    def __init__(self, entity_id: str, name: str, email: str,
                 department: str, research_topic: str):
        super().__init__(entity_id, name, email, department)
        self.research_topic: str = research_topic
        self.supervisor_id: str = ""
        self.thesis_submitted: bool = False

    def get_type(self) -> str:
        return "research_student"

    def get_max_courses(self) -> int:
        return 2

    def get_research_topic(self) -> str:
        return self.research_topic

    def assign_supervisor(self, supervisor_id: str) -> None:
        self.supervisor_id = supervisor_id

    def submit_thesis(self) -> None:
        self.thesis_submitted = True

    def is_thesis_submitted(self) -> bool:
        return self.thesis_submitted