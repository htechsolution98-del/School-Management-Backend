from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.utils import timezone
from sms_app.models import (
    School,
    AcademicYear,
    Student,
    SchoolClass,
    ResultWeightageConfig,
    ResultWeightageComponent,
    ExamTerm,
    Exam,
    Result,
    TeacherAssessmentScore,
    StudentAttendance,
    FinalStudentResult,
    ResultAuditLog,
)

class ResultCalculationEngine:
    """
    100% Fully Dynamic Result Calculation Engine.
    Evaluates dynamic weightage components defined by Principal (sum = 100%).
    Computes component contributions dynamically for students and saves FinalStudentResult.
    """

    @staticmethod
    def calculate_student_result(school, academic_year, student):
        config = ResultWeightageConfig.objects.filter(
            school=school, academic_year=academic_year, is_active=True
        ).first()

        if not config:
            return {
                "success": False,
                "reason": "No active Result Weightage Configuration found for this Academic Year.",
            }

        components = list(config.components.all().order_by("sequence"))
        if not components:
            return {
                "success": False,
                "reason": "Result Weightage Configuration has no components defined.",
            }

        total_weightage = sum([float(c.weightage_percentage) for c in components])
        if abs(total_weightage - 100.0) > 0.01:
            return {
                "success": False,
                "reason": f"Total weightage sum is {total_weightage}%, but must equal 100%.",
            }

        component_breakdowns = []
        final_percentage = Decimal("0.00")

        for comp in components:
            weightage_pct = Decimal(str(comp.weightage_percentage))
            comp_type = comp.component_type
            score_pct = Decimal("0.00")
            obtained_val = 0.0
            max_val = 100.0
            details_str = ""

            if comp_type == "EXAM":
                # Find ExamTerms linked to this weightage component
                terms = ExamTerm.objects.filter(weightage_component=comp, academic_year=academic_year)
                
                results_qs = Result.objects.filter(
                    student=student,
                    exam__academic_year=academic_year,
                )
                if terms.exists():
                    results_qs = results_qs.filter(exam__exam_term__in=terms)
                else:
                    # Match by component name or keywords
                    name_clean = comp.name.lower().replace("examination", "").replace("exam", "").strip()
                    matching_terms = ExamTerm.objects.filter(academic_year=academic_year).filter(
                        Q(name__icontains=comp.name) | Q(name__icontains=name_clean)
                    )
                    if matching_terms.exists():
                        results_qs = results_qs.filter(exam__exam_term__in=matching_terms)
                    else:
                        matching_exams = Exam.objects.filter(
                            academic_year=academic_year
                        ).filter(
                            Q(title__icontains=comp.name) |
                            Q(title__icontains=name_clean) |
                            Q(exam_term__name__icontains=comp.name) |
                            Q(exam_term__name__icontains=name_clean)
                        )
                        if matching_exams.exists():
                            results_qs = results_qs.filter(exam__in=matching_exams)

                if results_qs.exists():
                    total_obtained = sum([float(r.marks_obtained or 0) for r in results_qs if not r.is_absent])
                    total_max = sum([float(r.max_marks or 100) for r in results_qs])
                    if total_max > 0:
                        score_pct = Decimal(str(round((total_obtained / total_max) * 100, 2)))
                        obtained_val = total_obtained
                        max_val = total_max
                        details_str = f"Marks: {total_obtained}/{total_max}"
                else:
                    details_str = "No exam marks recorded"

            elif comp_type == "ATTENDANCE":
                # Calculate attendance percentage from StudentAttendance records
                attendances = StudentAttendance.objects.filter(student=student, school=school)
                total_days = attendances.count()
                present_days = attendances.filter(is_present=True).count()

                if total_days > 0:
                    att_pct = (present_days / total_days) * 100
                    score_pct = Decimal(str(round(att_pct, 2)))
                    details_str = f"Present: {present_days}/{total_days} days ({score_pct}%)"
                else:
                    score_pct = Decimal("100.00") # fallback if attendance module has no records yet
                    details_str = "Attendance data unavailable (defaulted to 100%)"

            elif comp_type == "TEACHER_ASSESSMENT":
                # Aggregate teacher assessment scores for this student
                scores_qs = TeacherAssessmentScore.objects.filter(
                    student=student, academic_year=academic_year
                )
                if scores_qs.exists():
                    avg_pct = sum([(float(s.score) / float(s.max_score or 10)) * 100 for s in scores_qs]) / scores_qs.count()
                    score_pct = Decimal(str(round(avg_pct, 2)))
                    details_str = f"Avg score: {score_pct}% from {scores_qs.count()} teacher evaluation(s)"
                else:
                    details_str = "No teacher assessment recorded"

            elif comp_type == "CUSTOM":
                details_str = "Custom assessment"

            contribution = (score_pct * weightage_pct) / Decimal("100.00")
            final_percentage += contribution

            component_breakdowns.append({
                "component_id": comp.id,
                "name": comp.name,
                "type": comp_type,
                "weightage_pct": float(weightage_pct),
                "score_pct": float(score_pct),
                "contribution_pct": float(round(contribution, 2)),
                "details": details_str
            })

        final_percentage_rounded = Decimal(str(round(float(final_percentage), 2)))
        
        # Calculate grade
        grade = "F"
        if final_percentage_rounded >= 90: grade = "A+"
        elif final_percentage_rounded >= 80: grade = "A"
        elif final_percentage_rounded >= 70: grade = "B+"
        elif final_percentage_rounded >= 60: grade = "B"
        elif final_percentage_rounded >= 50: grade = "C+"
        elif final_percentage_rounded >= 40: grade = "C"
        elif final_percentage_rounded >= 33: grade = "D"

        final_record, created = FinalStudentResult.objects.update_or_create(
            academic_year=academic_year,
            student=student,
            defaults={
                "school": school,
                "school_class": student.school_class,
                "division": student.division,
                "component_breakdown": {
                    "components": component_breakdowns,
                    "final_percentage": float(final_percentage_rounded)
                },
                "total_percentage": final_percentage_rounded,
                "grade": grade,
                "status": "READY_FOR_REVIEW" if student.final_results.filter(status="PUBLISHED").count() == 0 else "PUBLISHED"
            }
        )

        return {
            "success": True,
            "final_percentage": float(final_percentage_rounded),
            "grade": grade,
            "components": component_breakdowns,
            "result_id": final_record.id
        }

    @staticmethod
    def calculate_class_results(school, academic_year, school_class, division=None):
        students = Student.objects.filter(school=school, school_class=school_class)
        if division:
            students = students.filter(division=division)

        processed_count = 0
        for student in students:
            res = ResultCalculationEngine.calculate_student_result(school, academic_year, student)
            if res.get("success"):
                processed_count += 1

        return {
            "success": True,
            "total_students": students.count(),
            "processed_count": processed_count
        }
