# SAMPLE 09 — python_student_layered_system
# COMPLEXITY: high
# TESTS: ABC repository, Optional returns, List associations, dependency injection
# EXPECTED: 6 classes, 18+ fields, 20+ methods, 7+ edges

from abc import ABC, abstractmethod
from typing import List, Optional


class Student:
    def __init__(self, student_id: str, name: str, email: str):
        self.student_id: str = student_id
        self.name: str = name
        self.email: str = email
        self.gpa: float = 0.0

    def get_student_id(self) -> str:
        return self.student_id

    def get_name(self) -> str:
        return self.name

    def update_gpa(self, gpa: float) -> None:
        self.gpa = gpa

    def __str__(self) -> str:
        return f"Student({self.student_id}, {self.name})"


class Enrollment:
    def __init__(self, enrollment_id: str, course_id: str):
        self.enrollment_id: str = enrollment_id
        self.course_id: str = course_id
        self.grade: str = ""
        self.active: bool = True

    def get_enrollment_id(self) -> str:
        return self.enrollment_id

    def set_grade(self, grade: str) -> None:
        self.grade = grade

    def is_active(self) -> bool:
        return self.active


class IStudentRepository(ABC):
    @abstractmethod
    def find_by_id(self, student_id: str) -> Optional[Student]:
        pass

    @abstractmethod
    def find_all(self) -> List[Student]:
        pass

    @abstractmethod
    def save(self, student: Student) -> None:
        pass

    @abstractmethod
    def delete(self, student_id: str) -> bool:
        pass


class StudentRepository(IStudentRepository):
    def __init__(self):
        self._store: dict = {}

    def find_by_id(self, student_id: str) -> Optional[Student]:
        return self._store.get(student_id)

    def find_all(self) -> List[Student]:
        return list(self._store.values())

    def save(self, student: Student) -> None:
        self._store[student.student_id] = student

    def delete(self, student_id: str) -> bool:
        if student_id in self._store:
            del self._store[student_id]
            return True
        return False

    def find_by_name(self, name: str) -> List[Student]:
        return [s for s in self._store.values() if name.lower() in s.name.lower()]


class StudentService:
    def __init__(self, repository: StudentRepository):
        self.repository: StudentRepository = repository

    def get_student(self, student_id: str) -> Optional[Student]:
        return self.repository.find_by_id(student_id)

    def get_all_students(self) -> List[Student]:
        return self.repository.find_all()

    def register_student(self, student: Student) -> Student:
        self.repository.save(student)
        return student

    def remove_student(self, student_id: str) -> bool:
        return self.repository.delete(student_id)

    def validate_student(self, student: Student) -> bool:
        return bool(student.name and student.email)


class StudentController:
    def __init__(self, service: StudentService):
        self.service: StudentService = service

    def handle_get(self, student_id: str) -> Optional[Student]:
        return self.service.get_student(student_id)

    def handle_register(self, student: Student) -> Student:
        return self.service.register_student(student)

    def handle_get_all(self) -> List[Student]:
        return self.service.get_all_students()

    def handle_delete(self, student_id: str) -> bool:
        return self.service.remove_student(student_id)