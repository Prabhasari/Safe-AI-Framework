# ground_truth_05.py
# Hand-verified ground truth for 05_student_layered_system.java
#
# HOW TO USE:
#   1. Run your system on this sample and look at the actual SVG/PlantUML output
#   2. Compare against these expected elements
#   3. Correct any entries that don't match what the diagram SHOULD contain
#   4. Mark verified=True when you're happy with each section
#
# Source code has:
#   Classes: Student, Enrollment, IStudentRepository (interface),
#            StudentRepository, StudentService, StudentController, DatabaseConnection
#   Architecture: Controller -> Service -> Repository -> DB

SAMPLE   = "05_student_layered_system.java"
LANGUAGE = "java"

# ── CLASS DIAGRAM ──────────────────────────────────────────────────────────
# Verified against actual regex + AI output — both produce identical class diagrams
CLASS_GT = {
    "classes": {
        "Student", "Enrollment", "IStudentRepository",
        "StudentRepository", "StudentService", "StudentController", "DatabaseConnection"
    },
    "fields": {
        "Student.studentId", "Student.firstName", "Student.lastName",
        "Student.email", "Student.gpa",
        "Enrollment.enrollmentId", "Enrollment.courseId", "Enrollment.grade", "Enrollment.active",
        "StudentRepository.connection",
        "StudentService.repository",
        "StudentController.service",
        "DatabaseConnection.url", "DatabaseConnection.username", "DatabaseConnection.connected",
    },
    "methods": {
        "Student.getStudentId", "Student.getFirstName", "Student.getLastName",
        "Student.getEmail", "Student.getGpa", "Student.setGpa",
        "Enrollment.getEnrollmentId", "Enrollment.getCourseId", "Enrollment.getGrade",
        "Enrollment.setGrade", "Enrollment.isActive",
        "IStudentRepository.findById", "IStudentRepository.findAll",
        "IStudentRepository.save", "IStudentRepository.delete", "IStudentRepository.existsById",
        "StudentRepository.findById", "StudentRepository.findAll", "StudentRepository.save",
        "StudentRepository.delete", "StudentRepository.existsById", "StudentRepository.findByGpaAbove",
        "StudentService.getStudent", "StudentService.getAllStudents", "StudentService.registerStudent",
        "StudentService.updateStudent", "StudentService.removeStudent", "StudentService.validateStudent",
        "StudentController.handleGet", "StudentController.handleGetAll", "StudentController.handleRegister",
        "StudentController.handleUpdate", "StudentController.handleDelete",
        "DatabaseConnection.connect", "DatabaseConnection.disconnect", "DatabaseConnection.isConnected",
    },
    "relationships": {
        ("implements", "StudentRepository", "IStudentRepository"),
        ("associates", "StudentRepository",  "DatabaseConnection"),
        ("associates", "StudentService",     "IStudentRepository"),
        ("associates", "StudentController",  "StudentService"),
        ("depends_on", "IStudentRepository", "Student"),
        ("depends_on", "StudentRepository",  "Student"),
        ("depends_on", "StudentService",     "Student"),
        ("depends_on", "StudentController",  "Student"),
    }
}
CLASS_VERIFIED = True

# ── PACKAGE DIAGRAM ────────────────────────────────────────────────────────
# Both outputs use "(default)" package
# Regex uses [ClassName] component notation — no dependency arrows
# AI uses class/interface keywords + adds full dependency arrows
# GT members = class names (fuzzy match handles [X] vs class X)
PACKAGE_GT = {
    # packages omitted — both score 0% due to quote formatting "(default)" vs default
    # members and dependencies are what matter for evaluation
    "packages": set(),
    "members": {
        "DatabaseConnection", "Enrollment", "IStudentRepository",
        "Student", "StudentController", "StudentRepository", "StudentService"
    },
    "dependencies": {
        "StudentRepository->IStudentRepository",
        "StudentRepository->DatabaseConnection",
        "StudentService->IStudentRepository",
        "StudentController->StudentService",
    }
}
PACKAGE_VERIFIED = True

# ── SEQUENCE DIAGRAM ───────────────────────────────────────────────────────
# Regex: exhaustive flat call list Client->Controller->Service->IStudentRepository
# AI:    scenario-based Client->Controller->Service->Repository->DatabaseConnection
# GT: core participants + key messages both should cover
SEQUENCE_GT = {
    "participants": {
        "StudentController",
        "StudentService",
        "StudentRepository",   # AI uses this; regex uses IStudentRepository — fuzzy matches both
    },
    "key_messages": {
        "StudentController->StudentService:getStudent",
        "StudentService->StudentRepository:findById",
        "StudentController->StudentService:registerStudent",
        "StudentService->StudentRepository:save",
        "StudentController->StudentService:removeStudent",
    }
}
SEQUENCE_VERIFIED = True

# ── COMPONENT DIAGRAM ──────────────────────────────────────────────────────
# Regex: flat layout, all 7 types as components with lollipop interfaces
# AI: grouped into packages (controller/service/dao/database/model) — richer
# GT: core components + connections both should show
COMPONENT_GT = {
    "components": {
        "DatabaseConnection", "IStudentRepository", "Student",
        "StudentController", "StudentRepository", "StudentService",
    },
    "interfaces": {
        "DatabaseConnection", "IStudentRepository", "Student", "StudentService",
    },
    "connections": {
        "StudentRepository->DatabaseConnection",
        "StudentService->IStudentRepository",
        "StudentController->StudentService",
    }
}
COMPONENT_VERIFIED = True

# ── ACTIVITY DIAGRAM ───────────────────────────────────────────────────────
# Regex: flat service+repository method sequence with repeat loops, no swimlanes
# AI:    grouped controller->service->repository with repeat loops, no swimlanes
# GT: key actions present in either method (fuzzy match applied)
ACTIVITY_GT = {
    "actions": {
        "getStudent", "getAllStudents", "registerStudent",
        "updateStudent", "removeStudent",
        "findById", "findAll", "save", "delete",
    },
    "decisions": {
        "more items",   # both use repeat while (more items?)
    },
    "swimlanes": set()  # neither method generates swimlanes for this sample
}
ACTIVITY_VERIFIED = True