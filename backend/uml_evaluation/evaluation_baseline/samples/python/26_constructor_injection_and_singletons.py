# SAMPLE 26 — python_constructor_injection_and_singletons (v2)
# COMPLEXITY: medium-high
#
# WHY BASELINE FAILS:
#   1. Module-level singleton assignments (db = DatabaseManager()) mean the
#      baseline cannot detect relationships from constructor injection —
#      it only sees self.x = y patterns inside __init__.
#   2. When __init__ receives a typed parameter and assigns it to self,
#      the baseline DOES detect the field but CANNOT detect the relationship
#      because it needs to resolve that the parameter type is a known class.
#      For nested injection chains (Service takes Repo takes DB), the
#      relationship chain breaks at the second level for baseline.
#   3. The baseline's DEPENDS_ON heuristic only works for single-depth
#      typed params. It fails when the type is imported or aliased.
#
# CIR handles this via full type resolution across the parsed file.
#
# EXPECTED: classes=4, fields=11, methods=14, rels=5
# Baseline misses most ASSOCIATES/DEPENDS_ON edges → low relationship recall

from typing import List, Optional


class DatabaseConnection:
    def __init__(self, url: str, pool_size: int):
        self.url: str = url
        self.pool_size: int = pool_size
        self.connected: bool = False
        self._connections: List[str] = []

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def get_url(self) -> str:
        return self.url


class StudentRepository:
    def __init__(self, db: DatabaseConnection):
        # CIR detects: self.db is type DatabaseConnection → ASSOCIATES edge
        # Baseline: detects field 'db' but may not resolve type to class
        self.db: DatabaseConnection = db
        self._cache: dict = {}
        self.table_name: str = "students"

    def find(self, student_id: str) -> Optional[dict]:
        return self._cache.get(student_id)

    def save(self, student_id: str, data: dict) -> None:
        self._cache[student_id] = data

    def delete(self, student_id: str) -> bool:
        return bool(self._cache.pop(student_id, None))

    def find_all(self) -> List[dict]:
        return list(self._cache.values())


class StudentService:
    def __init__(self, repository: StudentRepository):
        # CIR detects chain: Service → Repository → DatabaseConnection
        # Baseline: may detect repository field but not the chain relationship
        self.repository: StudentRepository = repository
        self.cache_enabled: bool = True
        self.max_results: int = 100

    def get_student(self, student_id: str) -> Optional[dict]:
        return self.repository.find(student_id)

    def create_student(self, student_id: str, name: str) -> dict:
        data = {"id": student_id, "name": name}
        self.repository.save(student_id, data)
        return data

    def delete_student(self, student_id: str) -> bool:
        return self.repository.delete(student_id)

    def list_students(self) -> List[dict]:
        return self.repository.find_all()


class StudentController:
    def __init__(self, service: StudentService):
        self.service: StudentService = service
        self.request_count: int = 0

    def handle_get(self, student_id: str) -> Optional[dict]:
        self.request_count += 1
        return self.service.get_student(student_id)

    def handle_create(self, student_id: str, name: str) -> dict:
        self.request_count += 1
        return self.service.create_student(student_id, name)

    def handle_delete(self, student_id: str) -> bool:
        self.request_count += 1
        return self.service.delete_student(student_id)

    def get_request_count(self) -> int:
        return self.request_count


# Module-level wiring — realistic AI-generated pattern
# CIR detects these as dependency relationships via module-level analysis
# Baseline completely misses module-level assignments
db         = DatabaseConnection("postgresql://localhost/sms", pool_size=5)
repository = StudentRepository(db)
service    = StudentService(repository)
controller = StudentController(service)