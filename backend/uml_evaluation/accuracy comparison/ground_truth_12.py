# ground_truth_12.py
# Hand-verified ground truth for 12_hospital_appointment.java

SAMPLE   = "12_hospital_appointment.java"
LANGUAGE = "java"

CLASS_GT = {
    "classes": {
        "Doctor", "Patient", "Appointment", "Notification",
        "IDoctorRepository", "IPatientRepository", "IAppointmentRepository",
        "DoctorRepository", "PatientRepository", "AppointmentRepository",
        "NotificationService", "AppointmentService",
        "AppointmentController", "DatabaseConnection"
    },
    "fields": {
        "Doctor.doctorId", "Doctor.name", "Doctor.specialization",
        "Doctor.email", "Doctor.available", "Doctor.maxAppointmentsPerDay",
        "Patient.patientId", "Patient.name", "Patient.email",
        "Patient.phone", "Patient.dateOfBirth", "Patient.medicalHistory",
        "Appointment.appointmentId", "Appointment.doctor", "Appointment.patient",
        "Appointment.scheduledDate", "Appointment.scheduledTime",
        "Appointment.status", "Appointment.notes",
        "Notification.notificationId", "Notification.recipientEmail",
        "Notification.subject", "Notification.message", "Notification.sent",
        "DoctorRepository.connection", "PatientRepository.connection",
        "AppointmentRepository.connection",
        "NotificationService.pendingNotifications",
        "AppointmentService.appointmentRepository",
        "AppointmentService.doctorRepository",
        "AppointmentService.patientRepository",
        "AppointmentService.notificationService",
        "AppointmentController.appointmentService",
        "DatabaseConnection.url", "DatabaseConnection.username",
        "DatabaseConnection.password", "DatabaseConnection.connected",
    },
    "methods": {
        "Doctor.getDoctorId", "Doctor.getName", "Doctor.getSpecialization",
        "Doctor.isAvailable", "Doctor.setAvailable",
        "Doctor.getMaxAppointmentsPerDay", "Doctor.getEmail",
        "Patient.getPatientId", "Patient.getName", "Patient.getEmail",
        "Patient.getMedicalHistory", "Patient.updateMedicalHistory",
        "Appointment.getAppointmentId", "Appointment.getDoctor", "Appointment.getPatient",
        "Appointment.getScheduledDate", "Appointment.getStatus", "Appointment.setStatus",
        "Appointment.getNotes", "Appointment.setNotes",
        "Appointment.isConfirmed", "Appointment.isCancelled",
        "Notification.getNotificationId", "Notification.getRecipientEmail",
        "Notification.isSent", "Notification.markSent",
        "IDoctorRepository.findById", "IDoctorRepository.findAll",
        "IDoctorRepository.findBySpecialization", "IDoctorRepository.findAvailable",
        "IDoctorRepository.save",
        "IPatientRepository.findById", "IPatientRepository.findAll",
        "IPatientRepository.findByEmail", "IPatientRepository.save", "IPatientRepository.delete",
        "IAppointmentRepository.findById", "IAppointmentRepository.findByDoctor",
        "IAppointmentRepository.findByPatient", "IAppointmentRepository.findByDate",
        "IAppointmentRepository.findPending", "IAppointmentRepository.save",
        "IAppointmentRepository.delete",
        "DoctorRepository.findById", "DoctorRepository.findAll",
        "DoctorRepository.findBySpecialization", "DoctorRepository.findAvailable",
        "DoctorRepository.save",
        "PatientRepository.findById", "PatientRepository.findAll",
        "PatientRepository.findByEmail", "PatientRepository.save", "PatientRepository.delete",
        "AppointmentRepository.findById", "AppointmentRepository.findByDoctor",
        "AppointmentRepository.findByPatient", "AppointmentRepository.findByDate",
        "AppointmentRepository.findPending", "AppointmentRepository.save",
        "AppointmentRepository.delete",
        "NotificationService.sendConfirmation", "NotificationService.sendCancellation",
        "NotificationService.sendReminder", "NotificationService.getPendingNotifications",
        "AppointmentService.scheduleAppointment", "AppointmentService.confirmAppointment",
        "AppointmentService.cancelAppointment", "AppointmentService.getDoctorSchedule",
        "AppointmentService.getPatientHistory", "AppointmentService.getPendingAppointments",
        "AppointmentController.handleSchedule", "AppointmentController.handleConfirm",
        "AppointmentController.handleCancel", "AppointmentController.handleGetDoctorSchedule",
        "AppointmentController.handleGetPatientHistory", "AppointmentController.handleGetPending",
        "DatabaseConnection.connect", "DatabaseConnection.disconnect",
        "DatabaseConnection.isConnected", "DatabaseConnection.getUrl",
    },
    "relationships": {
        ("implements", "DoctorRepository",      "IDoctorRepository"),
        ("implements", "PatientRepository",     "IPatientRepository"),
        ("implements", "AppointmentRepository", "IAppointmentRepository"),
        ("associates", "DoctorRepository",      "DatabaseConnection"),
        ("associates", "PatientRepository",     "DatabaseConnection"),
        ("associates", "AppointmentRepository", "DatabaseConnection"),
        ("associates", "AppointmentService",    "IAppointmentRepository"),
        ("associates", "AppointmentService",    "IDoctorRepository"),
        ("associates", "AppointmentService",    "IPatientRepository"),
        ("associates", "AppointmentService",    "NotificationService"),
        ("associates", "AppointmentController", "AppointmentService"),
        ("associates", "Appointment",           "Doctor"),
        ("associates", "Appointment",           "Patient"),
        ("depends_on", "AppointmentService",    "Appointment"),
        ("depends_on", "NotificationService",   "Appointment"),
        ("depends_on", "AppointmentController", "Appointment"),
    }
}
CLASS_VERIFIED = True

PACKAGE_GT = {
    "packages": set(),
    "members": {
        "Doctor", "Patient", "Appointment", "Notification",
        "IDoctorRepository", "IPatientRepository", "IAppointmentRepository",
        "DoctorRepository", "PatientRepository", "AppointmentRepository",
        "NotificationService", "AppointmentService",
        "AppointmentController", "DatabaseConnection"
    },
    "dependencies": {
        "DoctorRepository->IDoctorRepository",
        "PatientRepository->IPatientRepository",
        "AppointmentRepository->IAppointmentRepository",
        "AppointmentService->IAppointmentRepository",
        "AppointmentService->NotificationService",
        "AppointmentController->AppointmentService",
    }
}
PACKAGE_VERIFIED = True

SEQUENCE_GT = {
    "participants": {
        "AppointmentController", "AppointmentService",
        "NotificationService", "IAppointmentRepository",
    },
    "key_messages": {
        "AppointmentController->AppointmentService:scheduleAppointment",
        "AppointmentService->IAppointmentRepository:save",
        "AppointmentService->NotificationService:sendConfirmation",
        "AppointmentController->AppointmentService:confirmAppointment",
        "AppointmentController->AppointmentService:cancelAppointment",
        "AppointmentService->NotificationService:sendCancellation",
    }
}
SEQUENCE_VERIFIED = True

COMPONENT_GT = {
    "components": {
        "AppointmentController", "AppointmentService", "NotificationService",
        "AppointmentRepository", "DoctorRepository",
        "PatientRepository", "DatabaseConnection"
    },
    "interfaces": {
        "IAppointmentRepository", "IDoctorRepository", "IPatientRepository",
        "AppointmentService", "NotificationService",
    },
    "connections": {
        "AppointmentController->AppointmentService",
        "AppointmentService->IAppointmentRepository",
        "AppointmentService->IDoctorRepository",
        "AppointmentService->NotificationService",
        "AppointmentRepository->DatabaseConnection",
    }
}
COMPONENT_VERIFIED = True

ACTIVITY_GT = {
    "actions": {
        "handleSchedule", "scheduleAppointment",
        "findById", "save", "sendConfirmation",
        "handleConfirm", "confirmAppointment",
        "handleCancel", "cancelAppointment", "sendCancellation",
    },
    "decisions": {
        "more items",
    },
    "swimlanes": {
        "AppointmentController", "AppointmentService",
        "NotificationService", "IAppointmentRepository",
    }
}
ACTIVITY_VERIFIED = True