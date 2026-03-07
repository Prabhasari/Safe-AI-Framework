// SAMPLE 14 — java_ambiguous_incomplete
// COMPLEXITY: medium-high
// SIMULATES: AI-generated code that is structurally incomplete — missing return
//            statements, TODO bodies, mixed raw types, unresolved references
//            This is a realistic vibe coding scenario where AI left stubs
// CHALLENGE: both methods must handle incomplete method bodies gracefully
//            AI may hallucinate missing implementations; regex must not crash
// EXPECTED: 3 classes, 9 fields, 11 methods, 2 relationships

import java.util.List;
import java.util.ArrayList;

class Student {
    private String id;
    private String name;
    private int age;
    private String status; // TODO: replace with enum

    public String getId() { return id; }
    public String getName() { return name; }
    public int getAge() { return age; }
    public void setStatus(String status) { this.status = status; }
    public String getStatus() { return status; }
    // TODO: add validation logic
}

class CourseEnrollment {
    private Student student;
    private List courses;  // raw type — AI forgot the generic parameter
    private int maxCapacity;
    private boolean isOpen;

    public void addCourse(Object course) {
        // TODO: implement
    }
    public List getCourses() { return courses; }  // raw return type
    public boolean hasCapacity() {
        // TODO: implement capacity check
        return true;
    }
    public int getMaxCapacity() { return maxCapacity; }
    public boolean isOpen() { return isOpen; }
}

class EnrollmentManager {
    private List<CourseEnrollment> enrollments;
    private String semester;

    public void processEnrollment(Student s) {
        // AI left this empty — common vibe coding pattern
    }
    public List<CourseEnrollment> getEnrollments() { return enrollments; }
    public String getSemester() { return semester; }
    public int getTotalEnrollments() {
        // TODO
        return 0;
    }
    public void closeEnrollment() { /* not yet implemented */ }
}