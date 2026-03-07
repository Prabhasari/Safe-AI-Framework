// SAMPLE 22 — java_nested_generics_complex
// COMPLEXITY: high
// DESIGNED TO BREAK: baseline regex — deeply nested generics cause field
//                    type extraction to fail, field names are misidentified,
//                    Map<String, Map<String, List<T>>> trips up greedy patterns
// CIR-based pipeline uses AST so handles this cleanly
// EXPECTED: 3 classes, 10 fields, 10 methods, 4 relationships

import java.util.List;
import java.util.Map;
import java.util.Optional;

public class GradeBook {
    private Map<String, Map<String, Double>> gradeMatrix;   // nested map — breaks regex
    private Map<String, List<Assessment>> assessmentMap;    // map of lists
    private List<String> courseIds;
    private String bookId;

    public Map<String, Map<String, Double>> getGradeMatrix() {
        return gradeMatrix;
    }
    public Optional<Double> getGrade(String studentId, String courseId) {
        return Optional.empty();
    }
    public void addAssessment(String courseId, Assessment a) {
        assessmentMap.get(courseId).add(a);
    }
    public List<Assessment> getAssessments(String courseId) {
        return assessmentMap.get(courseId);
    }
}

public class Assessment {
    private String assessmentId;
    private String title;
    private Map<String, Double> scoreMap;    // studentId -> score
    private double maxScore;

    public String getAssessmentId() { return assessmentId; }
    public String getTitle() { return title; }
    public double getMaxScore() { return maxScore; }
    public void recordScore(String studentId, double score) {
        scoreMap.put(studentId, score);
    }
    public Optional<Double> getScore(String studentId) {
        return Optional.ofNullable(scoreMap.get(studentId));
    }
}

public class ReportEngine {
    private GradeBook gradeBook;
    private Map<String, List<String>> reportCache;    // nested generic
    private String engineVersion;

    public String generateReport(String courseId) { return ""; }
    public List<String> getCachedReport(String key) {
        return reportCache.getOrDefault(key, List.of());
    }
    public void clearCache() { reportCache.clear(); }
    public GradeBook getGradeBook() { return gradeBook; }
}