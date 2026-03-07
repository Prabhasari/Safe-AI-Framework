// SAMPLE 12 — java_hospital_appointment_system
// COMPLEXITY: high
// ARCHITECTURE: 4-layer (Controller -> Service -> Repository -> DB)
// DESIGNED FOR: rich output across all 5 diagram types
// Features: multiple services collaborating, notification pattern,
//           scheduling logic, clear swimlane candidates per layer

import java.util.List;

// ── Domain Models ──────────────────────────────────────────────────────────

class Doctor {
    private String doctorId;
    private String name;
    private String specialization;
    private String email;
    private boolean available;
    private int maxAppointmentsPerDay;

    public String getDoctorId() { return doctorId; }
    public String getName() { return name; }
    public String getSpecialization() { return specialization; }
    public boolean isAvailable() { return available; }
    public void setAvailable(boolean available) { this.available = available; }
    public int getMaxAppointmentsPerDay() { return maxAppointmentsPerDay; }
    public String getEmail() { return email; }
}

class Patient {
    private String patientId;
    private String name;
    private String email;
    private String phone;
    private String dateOfBirth;
    private String medicalHistory;

    public String getPatientId() { return patientId; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public String getMedicalHistory() { return medicalHistory; }
    public void updateMedicalHistory(String entry) {
        this.medicalHistory = entry;
    }
}

class Appointment {
    private String appointmentId;
    private Doctor doctor;
    private Patient patient;
    private String scheduledDate;
    private String scheduledTime;
    private String status;
    private String notes;

    public String getAppointmentId() { return appointmentId; }
    public Doctor getDoctor() { return doctor; }
    public Patient getPatient() { return patient; }
    public String getScheduledDate() { return scheduledDate; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getNotes() { return notes; }
    public void setNotes(String notes) { this.notes = notes; }
    public boolean isConfirmed() { return "CONFIRMED".equals(status); }
    public boolean isCancelled() { return "CANCELLED".equals(status); }
}

class Notification {
    private String notificationId;
    private String recipientEmail;
    private String subject;
    private String message;
    private boolean sent;

    public String getNotificationId() { return notificationId; }
    public String getRecipientEmail() { return recipientEmail; }
    public boolean isSent() { return sent; }
    public void markSent() { this.sent = true; }
}

// ── Repository Layer ───────────────────────────────────────────────────────

interface IDoctorRepository {
    Doctor findById(String doctorId);
    List<Doctor> findAll();
    List<Doctor> findBySpecialization(String specialization);
    List<Doctor> findAvailable();
    void save(Doctor doctor);
}

interface IPatientRepository {
    Patient findById(String patientId);
    List<Patient> findAll();
    Patient findByEmail(String email);
    void save(Patient patient);
    void delete(String patientId);
}

interface IAppointmentRepository {
    Appointment findById(String appointmentId);
    List<Appointment> findByDoctor(String doctorId);
    List<Appointment> findByPatient(String patientId);
    List<Appointment> findByDate(String date);
    List<Appointment> findPending();
    void save(Appointment appointment);
    void delete(String appointmentId);
}

class DoctorRepository implements IDoctorRepository {
    private DatabaseConnection connection;

    public Doctor findById(String doctorId) { return null; }
    public List<Doctor> findAll() { return null; }
    public List<Doctor> findBySpecialization(String specialization) { return null; }
    public List<Doctor> findAvailable() { return null; }
    public void save(Doctor doctor) {}
}

class PatientRepository implements IPatientRepository {
    private DatabaseConnection connection;

    public Patient findById(String patientId) { return null; }
    public List<Patient> findAll() { return null; }
    public Patient findByEmail(String email) { return null; }
    public void save(Patient patient) {}
    public void delete(String patientId) {}
}

class AppointmentRepository implements IAppointmentRepository {
    private DatabaseConnection connection;

    public Appointment findById(String appointmentId) { return null; }
    public List<Appointment> findByDoctor(String doctorId) { return null; }
    public List<Appointment> findByPatient(String patientId) { return null; }
    public List<Appointment> findByDate(String date) { return null; }
    public List<Appointment> findPending() { return null; }
    public void save(Appointment appointment) {}
    public void delete(String appointmentId) {}
}

// ── Service Layer ──────────────────────────────────────────────────────────

class NotificationService {
    private List<Notification> pendingNotifications;

    public void sendConfirmation(Appointment appointment) {
        Notification n = new Notification();
        pendingNotifications.add(n);
        n.markSent();
    }

    public void sendCancellation(Appointment appointment) {
        Notification n = new Notification();
        pendingNotifications.add(n);
        n.markSent();
    }

    public void sendReminder(Appointment appointment) {
        Notification n = new Notification();
        pendingNotifications.add(n);
        n.markSent();
    }

    public List<Notification> getPendingNotifications() {
        return pendingNotifications;
    }
}

class AppointmentService {
    private IAppointmentRepository appointmentRepository;
    private IDoctorRepository doctorRepository;
    private IPatientRepository patientRepository;
    private NotificationService notificationService;

    public Appointment scheduleAppointment(String patientId, String doctorId, String date, String time) {
        Patient patient = patientRepository.findById(patientId);
        Doctor doctor   = doctorRepository.findById(doctorId);
        if (patient == null || doctor == null || !doctor.isAvailable()) return null;
        Appointment appointment = new Appointment();
        appointment.setStatus("PENDING");
        appointmentRepository.save(appointment);
        notificationService.sendConfirmation(appointment);
        return appointment;
    }

    public boolean confirmAppointment(String appointmentId) {
        Appointment appointment = appointmentRepository.findById(appointmentId);
        if (appointment == null) return false;
        appointment.setStatus("CONFIRMED");
        appointmentRepository.save(appointment);
        notificationService.sendConfirmation(appointment);
        return true;
    }

    public boolean cancelAppointment(String appointmentId) {
        Appointment appointment = appointmentRepository.findById(appointmentId);
        if (appointment == null || appointment.isCancelled()) return false;
        appointment.setStatus("CANCELLED");
        appointmentRepository.save(appointment);
        notificationService.sendCancellation(appointment);
        return true;
    }

    public List<Appointment> getDoctorSchedule(String doctorId) {
        return appointmentRepository.findByDoctor(doctorId);
    }

    public List<Appointment> getPatientHistory(String patientId) {
        return appointmentRepository.findByPatient(patientId);
    }

    public List<Appointment> getPendingAppointments() {
        return appointmentRepository.findPending();
    }
}

// ── Controller Layer ───────────────────────────────────────────────────────

class AppointmentController {
    private AppointmentService appointmentService;

    public Appointment handleSchedule(String patientId, String doctorId,
                                       String date, String time) {
        return appointmentService.scheduleAppointment(patientId, doctorId, date, time);
    }

    public boolean handleConfirm(String appointmentId) {
        return appointmentService.confirmAppointment(appointmentId);
    }

    public boolean handleCancel(String appointmentId) {
        return appointmentService.cancelAppointment(appointmentId);
    }

    public List<Appointment> handleGetDoctorSchedule(String doctorId) {
        return appointmentService.getDoctorSchedule(doctorId);
    }

    public List<Appointment> handleGetPatientHistory(String patientId) {
        return appointmentService.getPatientHistory(patientId);
    }

    public List<Appointment> handleGetPending() {
        return appointmentService.getPendingAppointments();
    }
}

// ── Infrastructure ─────────────────────────────────────────────────────────

class DatabaseConnection {
    private String url;
    private String username;
    private String password;
    private boolean connected;

    public boolean connect() { this.connected = true; return true; }
    public void disconnect() { this.connected = false; }
    public boolean isConnected() { return connected; }
    public String getUrl() { return url; }
}