import os
import django
import sys

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms.settings')
django.setup()

from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User, Group
from sms_app.models import School, Staff, Exam, Result, Student

def get_token(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)

def run_tests():
    # Find existing Principal and Teacher
    principal_staff = Staff.objects.filter(user__groups__name="PRINCIPAL").first()
    teacher_staff = Staff.objects.filter(user__groups__name="TEACHER").first()
    student = Student.objects.first()

    if not (principal_staff and teacher_staff and student):
        print("Missing required users in database (Principal, Teacher, Student) to run tests.")
        return

    exam = Exam.objects.filter(school=teacher_staff.school).first()
    if not exam:
        print("No exam found for the teacher's school.")
        return

    # Create a dummy result for the exam if none exists
    result, created = Result.objects.get_or_create(
        exam=exam,
        student=student,
        defaults={'max_marks': 100, 'marks_obtained': 50, 'is_published': False}
    )

    client = Client()
    
    print("--- Running Test Cases ---")
    
    # 1. Unauthorized Access
    print("1. Unauthorized Access (No Token)")
    response = client.post('/api/results/publish/', {'exam': exam.id}, content_type='application/json')
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("PASS: Unauthorized request blocked.")
    
    # 2. Student Access
    print("\n2. Unauthorized Access (Student Token)")
    student_token = get_token(student.user)
    response = client.post('/api/results/publish/', {'exam': exam.id}, 
                           content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {student_token}')
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    print("PASS: Student request blocked.")
    
    # 3. Invalid Exam ID
    print("\n3. Invalid Exam ID (Teacher)")
    teacher_token = get_token(teacher_staff.user)
    response = client.post('/api/results/publish/', {'exam': 99999}, 
                           content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {teacher_token}')
    assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    print("PASS: Invalid Exam ID handled correctly.")
    
    # 4. Exam from Another School
    print("\n4. Exam from Another School (Teacher)")
    other_school = School.objects.exclude(id=teacher_staff.school.id).first()
    if other_school:
        other_exam = Exam.objects.filter(school=other_school).first()
        if other_exam:
            response = client.post('/api/results/publish/', {'exam': other_exam.id}, 
                                   content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {teacher_token}')
            assert response.status_code == 400, f"Expected 400, got {response.status_code}"
            print("PASS: Exam from another school blocked.")
        else:
            print("SKIP: No exam found in another school.")
    else:
        print("SKIP: No other school found.")
        
    # 5. Publish as Teacher
    print("\n5. Publish as Teacher")
    # Reset is_published
    result.is_published = False
    result.save()
    
    response = client.post('/api/results/publish/', {'exam': exam.id}, 
                           content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {teacher_token}')
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.content}"
    result.refresh_from_db()
    assert result.is_published == True, "Result was not published!"
    print("PASS: Teacher successfully published results.")
    
    # 6. Publish as Principal
    print("\n6. Publish as Principal")
    # Reset is_published
    result.is_published = False
    result.save()
    
    principal_token = get_token(principal_staff.user)
    
    # Wait, the principal might not be in the same school as this exam. Let's make sure.
    exam_principal = Exam.objects.filter(school=principal_staff.school).first()
    if exam_principal:
        res_prin, _ = Result.objects.get_or_create(
            exam=exam_principal,
            student=student,
            defaults={'max_marks': 100, 'marks_obtained': 50, 'is_published': False}
        )
        res_prin.is_published = False
        res_prin.save()
        
        response = client.post('/api/results/publish/', {'exam': exam_principal.id}, 
                               content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {principal_token}')
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.content}"
        res_prin.refresh_from_db()
        assert res_prin.is_published == True, "Result was not published!"
        print("PASS: Principal successfully published results.")
    else:
        print("SKIP: No exam found for principal's school.")
    
    print("\nAll tests passed successfully!")

if __name__ == '__main__':
    run_tests()
