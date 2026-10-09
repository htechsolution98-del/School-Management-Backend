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
        config = None
        if student and getattr(student, "school_class", None):
            config = ResultWeightageConfig.objects.filter(
                school=school, academic_year=academic_year, school_class=student.school_class, is_active=True
            ).first()

        if not config:
            config = ResultWeightageConfig.objects.filter(
                school=school, academic_year=academic_year, school_class__isnull=True, is_active=True
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

    @staticmethod
    def check_readiness(school, academic_year, school_class=None, division=None):
        """
        Validates whether results for a class or school are 100% ready for calculation & publication.
        Returns a list of exact blockers if not ready, adhering to Section 18 & 30 of the specification.
        """
        blockers = []
        warnings = []

        # 1. Check Result Weightage
        config = ResultWeightageConfig.objects.filter(
            school=school, academic_year=academic_year
        ).first()

        if not config:
            blockers.append("Result Weightage Configuration has not been created for this Academic Year.")
        else:
            components = list(config.components.all())
            total_wt = sum([float(c.weightage_percentage) for c in components])
            if abs(total_wt - 100.0) > 0.01:
                blockers.append(f"Result Weightage is {total_wt}% (must equal exactly 100% to activate).")
            elif not config.is_active and config.status != "LOCKED":
                blockers.append("Result Weightage Configuration is currently in DRAFT mode and not activated.")

        # 2. Check Students
        students_qs = Student.objects.filter(school=school, is_active=True)
        if school_class:
            students_qs = students_qs.filter(school_class=school_class)
        if division and division != "ALL":
            students_qs = students_qs.filter(division=division)

        total_students = students_qs.count()
        if total_students == 0:
            blockers.append("No active students found for the selected criteria.")
            return {
                "is_ready": False,
                "status": "NOT_READY",
                "blockers": blockers,
                "warnings": warnings,
                "total_students": 0,
            }

        # 3. Check Exams and Marks Completion
        exams_qs = Exam.objects.filter(school=school, academic_year=academic_year)
        if school_class:
            exams_qs = exams_qs.filter(class_group=school_class)
        if division and division != "ALL":
            exams_qs = exams_qs.filter(Q(division__isnull=True) | Q(division="") | Q(division="ALL") | Q(division=division))

        if not exams_qs.exists():
            blockers.append("No examination schedules have been configured for this Academic Year.")
        else:
            for ex in exams_qs:
                target_students = students_qs.filter(school_class=ex.class_group)
                if ex.division and ex.division != "ALL":
                    target_students = target_students.filter(division=ex.division)
                
                req_count = target_students.count()
                entered_count = Result.objects.filter(exam=ex, student__in=target_students).count()
                
                cls_name = ex.class_group.school_class if ex.class_group else "Class"
                div_str = f" (Div {ex.division})" if ex.division else ""
                subj_name = ex.subject.name if ex.subject else "Subject"

                if entered_count < req_count:
                    missing = req_count - entered_count
                    blockers.append(f"Marks missing for {subj_name} in {cls_name}{div_str}: {missing} student(s) pending.")

        # 4. Check Class Teacher Verification
        if school_class:
            terms = ExamTerm.objects.filter(school=school, academic_year=academic_year)
            for term in terms:
                verif = ClassTeacherMarksVerification.objects.filter(
                    school=school,
                    academic_year=academic_year,
                    school_class=school_class,
                    exam_term=term,
                )
                if division and division != "ALL":
                    verif = verif.filter(division=division)
                
                verif_rec = verif.first()
                cls_name = school_class.school_class
                div_str = f" (Div {division})" if division and division != "ALL" else ""
                if not verif_rec or verif_rec.status != "VERIFIED":
                    status_text = verif_rec.status if verif_rec else "PENDING"
                    blockers.append(f"Class Teacher marks verification for {term.name} in {cls_name}{div_str} is {status_text}.")

        # 5. Check Teacher Assessment
        students_without_assessment = 0
        for st in students_qs:
            has_ta = TeacherAssessmentScore.objects.filter(student=st, academic_year=academic_year).exists()
            if not has_ta:
                students_without_assessment += 1

        if students_without_assessment > 0:
            cls_info = f" in {school_class.school_class}" if school_class else ""
            blockers.append(f"Teacher Assessment is pending for {students_without_assessment} student(s){cls_info}.")

        # 6. Check Attendance
        att_count = StudentAttendance.objects.filter(school=school, student__in=students_qs).count()
        if att_count == 0:
            warnings.append("No student attendance records logged. System will default attendance percentage to 100%.")

        is_ready = len(blockers) == 0
        return {
            "is_ready": is_ready,
            "status": "READY_FOR_REVIEW" if is_ready else "NOT_READY",
            "blockers": blockers,
            "warnings": warnings,
            "total_students": total_students,
        }

    @staticmethod
    def get_dashboard_summary(school, academic_year):
        """
        Calculates high-level metrics for the Principal Result Dashboard.
        Adheres to Section 5 of Exam_Result_Management_Full_Flow.md.
        """
        # 1. Weightage Info
        config = ResultWeightageConfig.objects.filter(
            school=school, academic_year=academic_year
        ).first()

        weightage_data = {
            "is_configured": False,
            "status": "DRAFT",
            "total_weightage": 0.0,
            "is_active": False,
            "components": [],
        }

        if config:
            comps = list(config.components.all().order_by("sequence"))
            total_sum = sum([float(c.weightage_percentage) for c in comps])
            weightage_data = {
                "is_configured": True,
                "status": config.status,
                "total_weightage": total_sum,
                "is_active": config.is_active or config.status == "LOCKED",
                "components": [
                    {
                        "name": c.name,
                        "type": c.component_type,
                        "weightage": float(c.weightage_percentage),
                    }
                    for c in comps
                ],
            }

        # 2. Terms Breakdown (Term 1, Term 2, etc.)
        terms = list(ExamTerm.objects.filter(school=school, academic_year=academic_year).order_by("id"))
        terms_summary = []

        total_exams = Exam.objects.filter(school=school, academic_year=academic_year).count()
        scheduled_exams = Exam.objects.filter(school=school, academic_year=academic_year, status__in=["SCHEDULED", "PUBLISHED", "COMPLETED", "VERIFIED"]).count()
        completed_exams = Exam.objects.filter(school=school, academic_year=academic_year, status__in=["COMPLETED", "VERIFIED"]).count()

        for term in terms:
            term_exams = Exam.objects.filter(school=school, academic_year=academic_year, exam_term=term)
            ex_count = term_exams.count()
            
            # Count expected marks vs entered marks
            total_expected_marks = 0
            total_entered_marks = 0
            for ex in term_exams:
                st_cnt = Student.objects.filter(school=school, school_class=ex.class_group, is_active=True).count()
                total_expected_marks += st_cnt
                total_entered_marks += Result.objects.filter(exam=ex).count()

            marks_pct = round((total_entered_marks / total_expected_marks * 100), 1) if total_expected_marks > 0 else 0.0
            
            # Verifications
            classes_with_exams = list(term_exams.values_list("class_group_id", flat=True).distinct())
            verified_classes_cnt = ClassTeacherMarksVerification.objects.filter(
                school=school,
                academic_year=academic_year,
                exam_term=term,
                school_class_id__in=classes_with_exams,
                status="VERIFIED"
            ).count()
            
            total_classes_cnt = len(classes_with_exams)
            verif_pct = round((verified_classes_cnt / total_classes_cnt * 100), 1) if total_classes_cnt > 0 else 0.0

            terms_summary.append({
                "term_id": term.id,
                "term_name": term.name,
                "exams_count": ex_count,
                "is_scheduled": ex_count > 0,
                "marks_percentage": marks_pct,
                "verification_percentage": verif_pct,
                "status": "Completed" if (marks_pct >= 100 and verif_pct >= 100) else ("In Progress" if marks_pct > 0 else "Pending")
            })

        # 3. Attendance Status
        att_logs_cnt = StudentAttendance.objects.filter(school=school).count()
        attendance_status = {
            "is_available": True,
            "total_logs": att_logs_cnt,
            "status": "Available" if att_logs_cnt > 0 else "Default (100%)",
        }

        # 4. Teacher Assessment Status
        students_count = Student.objects.filter(school=school, is_active=True).count()
        assessed_students = TeacherAssessmentScore.objects.filter(
            school=school, academic_year=academic_year
        ).values("student").distinct().count()

        ta_pct = round((assessed_students / students_count * 100), 1) if students_count > 0 else 0.0
        teacher_assessment_status = {
            "total_students": students_count,
            "assessed_students": assessed_students,
            "percentage": ta_pct,
            "status": "Completed" if ta_pct >= 100 else (f"{ta_pct}% Completed" if ta_pct > 0 else "Pending"),
        }

        # 5. Published Results Counts
        final_results = FinalStudentResult.objects.filter(school=school, academic_year=academic_year)
        ready_count = final_results.filter(status="READY_FOR_REVIEW").count()
        approved_count = final_results.filter(status="APPROVED").count()
        published_count = final_results.filter(status="PUBLISHED").count()

        # 6. Overall Readiness
        overall_readiness = ResultCalculationEngine.check_readiness(school, academic_year)

        return {
            "academic_year_id": academic_year.id,
            "academic_year_name": academic_year.name if hasattr(academic_year, "name") else str(academic_year),
            "weightage": weightage_data,
            "terms": terms_summary,
            "attendance": attendance_status,
            "teacher_assessment": teacher_assessment_status,
            "overall_readiness": overall_readiness,
            "counts": {
                "total_exams": total_exams,
                "scheduled_exams": scheduled_exams,
                "completed_exams": completed_exams,
                "ready_count": ready_count,
                "approved_count": approved_count,
                "published_count": published_count,
                "total_students": students_count,
            }
        }
