// SAMPLE 12 — java_complex_generics
// COMPLEXITY: high
// CHALLENGE: nested generics like Map<String, List<Course>>, Map<String, Double>
//            regex must correctly extract field names without being confused by <> syntax
// EXPECTED: 3 classes, 10 fields, 11 methods, 3 relationships

import java.util.List;
import java.util.Map;
import java.util.HashMap;

class Course {
    private String courseId;
    private String title;
    private int creditHours;

    public String getCourseId() { return courseId; }
    public String getTitle() { return title; }
    public int getCreditHours() { return creditHours; }
}

class AcademicRecord {
    private String studentId;
    private Map<String, Double> gradeMap;         // courseId -> grade
    private Map<String, List<Course>> semesterMap; // semester -> courses
    private List<String> completedCourseIds;

    public String getStudentId() { return studentId; }
    public Map<String, Double> getGradeMap() { return gradeMap; }
    public void addGrade(String courseId, double grade) { gradeMap.put(courseId, grade); }
    public double getGrade(String courseId) { return gradeMap.getOrDefault(courseId, 0.0); }
    public List<Course> getCoursesForSemester(String semester) {
        return semesterMap.getOrDefault(semester, List.of());
    }
    public double calculateGpa() {
        return gradeMap.values().stream().mapToDouble(Double::doubleValue).average().orElse(0.0);
    }
}

class TranscriptService {
    private Map<String, AcademicRecord> records;  // studentId -> record
    private List<Course> availableCourses;

    public AcademicRecord getRecord(String studentId) { return records.get(studentId); }
    public void registerRecord(AcademicRecord record) { records.put(record.getStudentId(), record); }
    public List<Course> getAvailableCourses() { return availableCourses; }
    public Map<String, Double> getClassRanking() {
        Map<String, Double> ranking = new HashMap<>();
        records.forEach((id, rec) -> ranking.put(id, rec.calculateGpa()));
        return ranking;
    }
}