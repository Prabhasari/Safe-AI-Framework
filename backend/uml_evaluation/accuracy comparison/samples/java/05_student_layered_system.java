// SAMPLE 05 — java_student_layered_system
// COMPLEXITY: high
// TESTS: 4-layer architecture, interface + implementation, full relationship chain
// EXPECTED: 7 classes/interfaces, 18+ fields, 22+ methods, 8+ edges

import java.util.List;

class Student {
    private String studentId;
    private String firstName;
    private String lastName;
    private String email;
    private double gpa;

    public String getStudentId() { return studentId; }
    public String getFirstName() { return firstName; }
    public String getLastName() { return lastName; }
    public String getEmail() { return email; }
    public double getGpa() { return gpa; }
    public void setGpa(double gpa) { this.gpa = gpa; }
}

class Enrollment {
    private String enrollmentId;
    private String courseId;
    private String grade;
    private boolean active;

    public String getEnrollmentId() { return enrollmentId; }
    public String getCourseId() { return courseId; }
    public String getGrade() { return grade; }
    public void setGrade(String grade) { this.grade = grade; }
    public boolean isActive() { return active; }
}

interface IStudentRepository {
    Student findById(String id);
    List<Student> findAll();
    void save(Student student);
    void delete(String id);
    boolean existsById(String id);
}

class StudentRepository implements IStudentRepository {
    private DatabaseConnection connection;

    public Student findById(String id) { return null; }
    public List<Student> findAll() { return null; }
    public void save(Student student) {}
    public void delete(String id) {}
    public boolean existsById(String id) { return false; }
    public List<Student> findByGpaAbove(double minGpa) { return null; }
}

class StudentService {
    private IStudentRepository repository;

    public Student getStudent(String id) { return repository.findById(id); }
    public List<Student> getAllStudents() { return repository.findAll(); }
    public Student registerStudent(Student student) {
        repository.save(student);
        return student;
    }
    public void updateStudent(Student student) { repository.save(student); }
    public void removeStudent(String id) { repository.delete(id); }
    public boolean validateStudent(Student student) { return student != null; }
}

class StudentController {
    private StudentService service;

    public Student handleGet(String id) { return service.getStudent(id); }
    public List<Student> handleGetAll() { return service.getAllStudents(); }
    public Student handleRegister(Student s) { return service.registerStudent(s); }
    public void handleUpdate(Student s) { service.updateStudent(s); }
    public void handleDelete(String id) { service.removeStudent(id); }
}

class DatabaseConnection {
    private String url;
    private String username;
    private boolean connected;

    public boolean connect() { return true; }
    public void disconnect() {}
    public boolean isConnected() { return connected; }
}