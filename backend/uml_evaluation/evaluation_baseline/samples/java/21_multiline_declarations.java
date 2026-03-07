// SAMPLE 21 — java_multiline_declarations
// COMPLEXITY: medium
// DESIGNED TO BREAK: baseline regex — multi-line method signatures,
//                    multi-line field declarations, chained annotations
// CIR-based pipeline should handle this fine via AST
// EXPECTED: 3 classes, 8 fields, 9 methods, 3 relationships

import java.util.List;
import java.util.Map;

public class StudentRegistrar {

    private Map<String,
                List<String>> semesterMap;   // multi-line generic — breaks naive regex

    private final StudentValidator
            validator;                        // multi-line field declaration

    private List<Course> activeCourses;

    public boolean registerStudent(
            String studentId,
            String name,
            int semester) {                   // multi-line params — regex misses this
        return true;
    }

    public Map<String, List<String>> getSemesterMap() {
        return semesterMap;
    }

    public void validateAndSave(
            Student student,
            boolean force) {
    }
}

public class StudentValidator {
    private String validationMode;
    private int maxRetries;

    public boolean validate(Student s) { return true; }
    public String getMode() { return validationMode; }
    public void setMaxRetries(int n) { this.maxRetries = n; }
}

public class Course {
    private String courseId;
    private String title;
    private int credits;

    public String getCourseId() { return courseId; }
    public String getTitle() { return title; }
    public int getCredits() { return credits; }
}