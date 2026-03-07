# SAMPLE 07 — python_student_inheritance
# COMPLEXITY: low-medium
# TESTS: ABC abstract class, INHERITS edge, abstract method detection
# EXPECTED: 1 ABC, 3 classes, 9 fields, 11 methods, 3 INHERITS edges

from abc import ABC, abstractmethod


class Person(ABC):
    def __init__(self, person_id: str, name: str, email: str):
        self.person_id: str = person_id
        self.name: str = name
        self.email: str = email

    @abstractmethod
    def get_role(self) -> str:
        pass

    def get_id(self) -> str:
        return self.person_id

    def get_name(self) -> str:
        return self.name

    def update_email(self, email: str) -> None:
        self.email = email


class Student(Person):
    def __init__(self, person_id: str, name: str, email: str, gpa: float):
        super().__init__(person_id, name, email)
        self.gpa: float = gpa
        self.major: str = ""

    def get_role(self) -> str:
        return "student"

    def get_gpa(self) -> float:
        return self.gpa

    def update_gpa(self, gpa: float) -> None:
        self.gpa = gpa


class Lecturer(Person):
    def __init__(self, person_id: str, name: str, email: str, specialization: str):
        super().__init__(person_id, name, email)
        self.specialization: str = specialization
        self.years_experience: int = 0

    def get_role(self) -> str:
        return "lecturer"

    def get_specialization(self) -> str:
        return self.specialization

    def get_years_experience(self) -> int:
        return self.years_experience


class Admin(Person):
    def __init__(self, person_id: str, name: str, email: str, department: str):
        super().__init__(person_id, name, email)
        self.department: str = department
        self.access_level: int = 1

    def get_role(self) -> str:
        return "admin"

    def get_department(self) -> str:
        return self.department

    def set_access_level(self, level: int) -> None:
        self.access_level = level