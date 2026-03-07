# SAMPLE 17 — python_complex_generics
# COMPLEXITY: high
# CHALLENGE: Dict[str, List[float]], Dict[str, Dict[str, float]], Optional[Dict]
#             field extractor must handle nested generic types without
#             misidentifying the field name or breaking on nested brackets
# EXPECTED: 3 classes, 10 fields, 12 methods, 3 relationships

from typing import Dict, List, Optional, Tuple


class CourseResult:
    def __init__(self, course_id: str, score: float, grade: str):
        self.course_id: str = course_id
        self.score: float = score
        self.grade: str = grade

    def get_course_id(self) -> str:
        return self.course_id

    def get_score(self) -> float:
        return self.score

    def is_passing(self) -> bool:
        return self.score >= 50.0


class AcademicProfile:
    def __init__(self, student_id: str):
        self.student_id: str = student_id
        self.semester_results: Dict[str, List[CourseResult]] = {}   # semester -> results
        self.grade_history: Dict[str, float] = {}                   # courseId -> grade
        self.ranking_data: Optional[Dict[str, float]] = None        # optional rankings

    def add_result(self, semester: str, result: CourseResult) -> None:
        if semester not in self.semester_results:
            self.semester_results[semester] = []
        self.semester_results[semester].append(result)

    def get_semester_results(self, semester: str) -> List[CourseResult]:
        return self.semester_results.get(semester, [])

    def calculate_gpa(self) -> float:
        all_scores = [r.score for results in self.semester_results.values() for r in results]
        return sum(all_scores) / len(all_scores) if all_scores else 0.0

    def get_grade_history(self) -> Dict[str, float]:
        return self.grade_history

    def set_ranking(self, ranking: Dict[str, float]) -> None:
        self.ranking_data = ranking


class AnalyticsService:
    def __init__(self):
        self.profiles: Dict[str, AcademicProfile] = {}
        self.cohort_stats: Dict[str, Dict[str, float]] = {}   # nested dict — hard for regex

    def register_profile(self, profile: AcademicProfile) -> None:
        self.profiles[profile.student_id] = profile

    def get_profile(self, student_id: str) -> Optional[AcademicProfile]:
        return self.profiles.get(student_id)

    def get_top_performers(self, threshold: float) -> List[AcademicProfile]:
        return [p for p in self.profiles.values() if p.calculate_gpa() >= threshold]

    def compute_cohort_stats(self, semester: str) -> Dict[str, float]:
        stats: Dict[str, float] = {}
        return stats

    def get_ranking_pairs(self) -> List[Tuple[str, float]]:
        return [(sid, p.calculate_gpa()) for sid, p in self.profiles.items()]