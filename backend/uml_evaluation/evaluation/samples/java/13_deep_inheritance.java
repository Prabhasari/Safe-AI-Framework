// SAMPLE 13 — java_deep_inheritance (fixed)
// COMPLEXITY: high
// TESTS: 4-level inheritance chain, interface at root, INHERITS + IMPLEMENTS edges
// EXPECTED: 1 interface, 4 classes, 13 fields, 15 methods, 5+ edges

interface Identifiable {
    String getId();
    String getType();
}

class Person implements Identifiable {
    protected String personId;
    protected String name;
    protected String email;

    public String getId() { return personId; }
    public String getType() { return "person"; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}

class AcademicMember extends Person {
    protected String department;
    protected String academicYear;

    public String getType() { return "academic"; }
    public String getDepartment() { return department; }
    public String getAcademicYear() { return academicYear; }
    public int getMaxCourseLoad() { return 6; }
}

class Student extends AcademicMember {
    private double gpa;
    private String enrollmentStatus;

    public String getType() { return "student"; }
    public double getGpa() { return gpa; }
    public void setGpa(double gpa) { this.gpa = gpa; }
    public String getEnrollmentStatus() { return enrollmentStatus; }
    public void setEnrollmentStatus(String status) { this.enrollmentStatus = status; }
}

class ResearchStudent extends Student {
    private String researchTopic;
    private String supervisorId;
    private boolean thesisSubmitted;

    public String getType() { return "research_student"; }
    public int getMaxCourseLoad() { return 2; }
    public String getResearchTopic() { return researchTopic; }
    public String getSupervisorId() { return supervisorId; }
    public boolean isThesisSubmitted() { return thesisSubmitted; }
    public void submitThesis() { this.thesisSubmitted = true; }
}