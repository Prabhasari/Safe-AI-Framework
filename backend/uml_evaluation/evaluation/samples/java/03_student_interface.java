// SAMPLE 03 — java_student_interface
// COMPLEXITY: low-medium
// TESTS: interface detection, IMPLEMENTS edge, multiple concrete implementations
// EXPECTED: 1 interface, 2 classes, 4 fields, 8 methods, 2 IMPLEMENTS edges

interface Enrollable {
    boolean enroll(String courseId);
    boolean drop(String courseId);
    int getEnrolledCount();
}

class UndergraduateStudent implements Enrollable {
    private String studentId;
    private String name;

    public boolean enroll(String courseId) { return true; }
    public boolean drop(String courseId) { return true; }
    public int getEnrolledCount() { return 0; }
    public String getStudentId() { return studentId; }
    public String getName() { return name; }
}

class PostgraduateStudent implements Enrollable {
    private String studentId;
    private String thesisTitle;

    public boolean enroll(String courseId) { return true; }
    public boolean drop(String courseId) { return false; }
    public int getEnrolledCount() { return 0; }
    public String getThesisTitle() { return thesisTitle; }
    public void setThesisTitle(String title) { this.thesisTitle = title; }
}