// SAMPLE 15 — java_multi_interface_web
// COMPLEXITY: high
// CHALLENGE: one class implements two interfaces, another implements one,
//            plus associations — creates a dense relationship web that
//            regex must map correctly and AI may over-infer
// EXPECTED: 2 interfaces, 3 classes, 11 fields, 16 methods, 7+ edges

import java.util.List;

interface Gradable {
    double calculateFinalGrade();
    String getLetterGrade();
    boolean isPassing();
}

interface Reportable {
    String generateSummary();
    List<String> getWarnings();
    boolean requiresIntervention();
}

class Assessment {
    private String assessmentId;
    private String title;
    private double maxScore;
    private double weight;

    public String getAssessmentId() { return assessmentId; }
    public String getTitle() { return title; }
    public double getMaxScore() { return maxScore; }
    public double getWeight() { return weight; }
    public void setWeight(double weight) { this.weight = weight; }
}

class StudentGrade implements Gradable, Reportable {
    private String studentId;
    private List<Assessment> assessments;
    private List<Double> scores;
    private String remarks;

    public double calculateFinalGrade() {
        if (scores.isEmpty()) return 0.0;
        return scores.stream().mapToDouble(Double::doubleValue).average().orElse(0.0);
    }
    public String getLetterGrade() {
        double g = calculateFinalGrade();
        return g >= 75 ? "A" : g >= 65 ? "B" : g >= 55 ? "C" : "F";
    }
    public boolean isPassing() { return calculateFinalGrade() >= 55; }
    public String generateSummary() { return "Student: " + studentId; }
    public List<String> getWarnings() { return List.of(); }
    public boolean requiresIntervention() { return !isPassing(); }
    public String getStudentId() { return studentId; }
    public String getRemarks() { return remarks; }
}

class GradeBook {
    private String courseId;
    private List<StudentGrade> grades;
    private Assessment finalExam;

    public void addGrade(StudentGrade grade) { grades.add(grade); }
    public List<StudentGrade> getGrades() { return grades; }
    public double getCourseAverage() {
        return grades.stream().mapToDouble(StudentGrade::calculateFinalGrade).average().orElse(0.0);
    }
    public String getCourseId() { return courseId; }
    public long getPassCount() { return grades.stream().filter(StudentGrade::isPassing).count(); }
    public Assessment getFinalExam() { return finalExam; }
}