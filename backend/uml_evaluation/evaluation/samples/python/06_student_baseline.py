# SAMPLE 06 — python_student_baseline
# COMPLEXITY: low
# TESTS: __init__ self-field extraction, typed annotations, basic Python class
# EXPECTED: 2 classes, 5 fields, 6 methods, 0 relationships

class Student:
    def __init__(self, student_id: str, name: str, email: str):
        self.student_id: str = student_id
        self.name: str = name
        self.email: str = email

    def get_student_id(self) -> str:
        return self.student_id

    def get_name(self) -> str:
        return self.name

    def update_email(self, email: str) -> None:
        self.email = email


class Department:
    def __init__(self, dept_id: str, dept_name: str):
        self.dept_id: str = dept_id
        self.dept_name: str = dept_name

    def get_dept_id(self) -> str:
        return self.dept_id

    def get_dept_name(self) -> str:
        return self.dept_name

    def update_name(self, name: str) -> None:
        self.dept_name = name