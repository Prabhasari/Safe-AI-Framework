// SAMPLE 01 — java_student_baseline
// COMPLEXITY: low
// TESTS: basic class detection, field visibility, method signatures
// EXPECTED: 2 classes, 5 fields, 6 methods, 0 relationships

class Student {
    private String studentId;
    private String name;
    private String email;

    public String getStudentId() { return studentId; }
    public void setName(String name) { this.name = name; }
    public String getName() { return name; }
    public void setEmail(String email) { this.email = email; }
    public String getEmail() { return email; }
}

class Department {
    private String departmentId;
    private String departmentName;

    public String getDepartmentId() { return departmentId; }
    public String getDepartmentName() { return departmentName; }
    public void setDepartmentName(String name) { this.departmentName = name; }
}