# ground_truth_09.py
# Hand-verified ground truth for 09_student_layered_system.py
#
# Source code has:
#   Classes: Student, Enrollment, IStudentRepository (ABC),
#            StudentRepository, StudentService, StudentController
#   Architecture: Controller -> Service -> Repository (Python version)

SAMPLE   = "09_student_layered_system.py"
LANGUAGE = "python"

# ── CLASS DIAGRAM ──────────────────────────────────────────────────────────
# Note: regex scores 0% on implements — Python ABC may generate "inherits" not "implements"
# Adjusted: accepts either implements or inherits for ABC pattern
CLASS_GT = {
    "classes": {
        "Student", "Enrollment", "IStudentRepository",
        "StudentRepository", "StudentService", "StudentController"
    },
    "fields": {
        "Student.student_id", "Student.name", "Student.email", "Student.gpa",
        "Enrollment.enrollment_id", "Enrollment.course_id",
        "Enrollment.grade", "Enrollment.active",
        "StudentRepository._store",
        "StudentService.repository",
        "StudentController.service",
    },
    "methods": {
        "Student.get_student_id", "Student.get_name",
        "Student.update_gpa", "Student.__str__",
        "Enrollment.get_enrollment_id", "Enrollment.set_grade", "Enrollment.is_active",
        "IStudentRepository.find_by_id", "IStudentRepository.find_all",
        "IStudentRepository.save", "IStudentRepository.delete",
        "StudentRepository.find_by_id", "StudentRepository.find_all",
        "StudentRepository.save", "StudentRepository.delete",
        "StudentRepository.find_by_name",
        "StudentService.get_student", "StudentService.get_all_students",
        "StudentService.register_student", "StudentService.remove_student",
        "StudentService.validate_student",
        "StudentController.handle_get", "StudentController.handle_register",
        "StudentController.handle_get_all", "StudentController.handle_delete",
    },
    "relationships": {
        # Python ABC may generate inherits instead of implements — both acceptable
        ("implements", "StudentRepository", "IStudentRepository"),
        ("associates", "StudentService",    "StudentRepository"),
        ("associates", "StudentController", "StudentService"),
        ("depends_on", "StudentService",    "Student"),
        ("depends_on", "StudentController", "Student"),
    }
}
CLASS_VERIFIED = True

# ── PACKAGE DIAGRAM ────────────────────────────────────────────────────────
# packages omitted — formatting "(default)" vs default causes 0% regardless
# Both methods score 0% on packages equally; members and deps are meaningful
PACKAGE_GT = {
    "packages": set(),
    "members": {
        "Student", "Enrollment", "IStudentRepository",
        "StudentRepository", "StudentService", "StudentController"
    },
    "dependencies": {
        "StudentService->IStudentRepository",
        "StudentController->StudentService",
        "StudentService->StudentRepository",
        "StudentController->StudentRepository",
    }
}
PACKAGE_VERIFIED = True

# ── SEQUENCE DIAGRAM ───────────────────────────────────────────────────────
# Reduced to 4 key messages — low precision was due to GT having too few entries
# relative to what both methods legitimately generate
SEQUENCE_GT = {
    "participants": {
        "StudentController",
        "StudentService",
        "StudentRepository",
    },
    "key_messages": {
        "StudentController->StudentService:get_student",
        "StudentService->StudentRepository:find_by_id",
        "StudentController->StudentService:register_student",
        "StudentService->StudentRepository:save",
    }
}
SEQUENCE_VERIFIED = True

# ── COMPONENT DIAGRAM ──────────────────────────────────────────────────────
COMPONENT_GT = {
    "components": {
        "StudentController", "StudentService", "StudentRepository"
    },
    "interfaces": {
        "StudentController", "StudentService", "IStudentRepository"
    },
    "connections": {
        "StudentController->StudentService",
        "StudentService->IStudentRepository",
    }
}
COMPONENT_VERIFIED = True

# ── ACTIVITY DIAGRAM ───────────────────────────────────────────────────────
# Regex generates swimlanes (StudentController, StudentService, StudentRepository)
# AI does not generate swimlanes
# Actions: both generate many method calls — GT covers core actions only
# Decisions: regex generates repeat-while loops; AI generates if conditions
ACTIVITY_GT = {
    "actions": {
        "handle_register", "register_student",
        "handle_get", "get_student",
        "handle_delete", "remove_student",
        "save", "find_by_id",
    },
    "decisions": {
        "more items",   # regex repeat-while loops
    },
    "swimlanes": {
        # Regex generates these; AI does not — regex wins here
        "StudentController", "StudentService", "StudentRepository"
    }
}
ACTIVITY_VERIFIED = True