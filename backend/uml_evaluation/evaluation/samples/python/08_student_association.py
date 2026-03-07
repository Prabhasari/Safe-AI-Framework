# SAMPLE 08 — python_student_association
# COMPLEXITY: medium
# TESTS: List[T] field multiplicity, ASSOCIATES edge, DEPENDS_ON via method param
# EXPECTED: 2 classes, 6 fields, 7 methods, 1 ASSOCIATES + 1 DEPENDS_ON edge

from typing import List


class Course:
    def __init__(self, course_id: str, title: str, credits: int):
        self.course_id: str = course_id
        self.title: str = title
        self.credits: int = credits

    def get_course_id(self) -> str:
        return self.course_id

    def get_title(self) -> str:
        return self.title

    def get_credits(self) -> int:
        return self.credits


class Student:
    def __init__(self, student_id: str, name: str, gpa: float):
        self.student_id: str = student_id
        self.name: str = name
        self.gpa: float = gpa
        self.enrolled_courses: List[Course] = []

    def enroll(self, course: Course) -> None:
        self.enrolled_courses.append(course)

    def drop(self, course: Course) -> bool:
        if course in self.enrolled_courses:
            self.enrolled_courses.remove(course)
            return True
        return False

    def get_courses(self) -> List[Course]:
        return self.enrolled_courses