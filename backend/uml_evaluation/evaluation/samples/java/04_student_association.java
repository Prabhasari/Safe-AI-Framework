// SAMPLE 04 — java_student_association
// COMPLEXITY: medium
// TESTS: ASSOCIATES edge, List<T> multiplicity, DEPENDS_ON via method param
// EXPECTED: 2 classes, 6 fields, 7 methods, 1 ASSOCIATES + 1 DEPENDS_ON edge

import java.util.List;

class Course {
    private String courseId;
    private String title;
    private int credits;

    public String getCourseId() { return courseId; }
    public String getTitle() { return title; }
    public int getCredits() { return credits; }
}

class Student {
    private String studentId;
    private String name;
    private double gpa;
    private List<Course> enrolledCourses;

    public String getStudentId() { return studentId; }
    public String getName() { return name; }
    public double getGpa() { return gpa; }
    public void enroll(Course course) { enrolledCourses.add(course); }
    public List<Course> getCourses() { return enrolledCourses; }
    public void drop(Course course) { enrolledCourses.remove(course); }
}