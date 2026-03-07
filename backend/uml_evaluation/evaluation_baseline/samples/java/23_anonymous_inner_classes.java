// SAMPLE 23 — java_anonymous_and_inner_classes
// COMPLEXITY: high
// DESIGNED TO BREAK: baseline regex — anonymous class bodies and inner
//                    class declarations confuse class-boundary tracking,
//                    causing fields/methods to be assigned to wrong class
//                    or missed entirely
// CIR-based pipeline uses proper AST scoping so handles this correctly
// EXPECTED: 3 classes, 9 fields, 11 methods, 3 relationships

import java.util.List;
import java.util.Comparator;

public class StudentSorter {
    private List<Student> students;
    private String sortMode;
    private boolean descending;

    public List<Student> sortByGpa() {
        // Anonymous Comparator — baseline regex may enter this block
        // and incorrectly extract its method as belonging to StudentSorter
        students.sort(new Comparator<Student>() {
            @Override
            public int compare(Student a, Student b) {
                return Double.compare(a.getGpa(), b.getGpa());
            }
        });
        return students;
    }

    public List<Student> sortByName() {
        students.sort(Comparator.comparing(Student::getName));
        return students;
    }

    public void setDescending(boolean descending) {
        this.descending = descending;
    }

    public String getSortMode() { return sortMode; }
    public void setSortMode(String mode) { this.sortMode = mode; }
}

public class Student {
    private String studentId;
    private String name;
    private double gpa;
    private String major;

    public String getStudentId() { return studentId; }
    public String getName() { return name; }
    public double getGpa() { return gpa; }
    public void setGpa(double gpa) { this.gpa = gpa; }
    public String getMajor() { return major; }
}

public class SortResult {
    private List<Student> sorted;
    private int totalCount;
    private String appliedMode;

    public List<Student> getSorted() { return sorted; }
    public int getTotalCount() { return totalCount; }
    public String getAppliedMode() { return appliedMode; }
    public void setAppliedMode(String mode) { this.appliedMode = mode; }
}