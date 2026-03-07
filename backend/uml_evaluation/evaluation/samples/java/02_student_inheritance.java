// SAMPLE 02 — java_student_inheritance
// COMPLEXITY: low
// TESTS: abstract class, INHERITS edge, abstract method flags
// EXPECTED: 3 classes (1 abstract), 7 fields, 9 methods, 2 INHERITS edges

abstract class Person {
    protected String id;
    protected String name;
    protected String email;

    public abstract String getRole();
    public String getId() { return id; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}

class Student extends Person {
    private double gpa;
    private String major;

    public String getRole() { return "student"; }
    public double getGpa() { return gpa; }
    public void setGpa(double gpa) { this.gpa = gpa; }
    public String getMajor() { return major; }
}

class Lecturer extends Person {
    private String specialization;
    private int yearsExperience;

    public String getRole() { return "lecturer"; }
    public String getSpecialization() { return specialization; }
    public int getYearsExperience() { return yearsExperience; }
}