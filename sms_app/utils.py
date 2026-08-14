
import string
# pyrefly: ignore [missing-import]
from django.db import transaction
import random
# pyrefly: ignore [missing-import]
from django.core.mail import send_mail
import datetime
import pandas as pd
import uuid
from io import BytesIO
from PIL import Image
# pyrefly: ignore [missing-import]
from django.core.files.uploadedfile import InMemoryUploadedFile
from .models import *
# pyrefly: ignore [missing-import]
from django.contrib.auth import get_user_model

User = get_user_model()

def generate_school_code(name):
    school_name = name.split(" ")[0]
    digit = string.digits

    four_digit = "".join(random.choices(digit, k=4))
    school_code = school_name + four_digit

    if School.objects.filter(code=school_code).exists():
        return generate_school_code(name)

    return school_code




def generate_staff_username(name):
    Staff_name = name.split(" ")[0]
    digit = string.digits

    four_digit = "".join(random.choices(digit, k=4))
    Staff_username = Staff_name + four_digit

    if User.objects.filter(username=Staff_username).exists():
        return generate_staff_username(name)

    return Staff_username


# ======END CODE for GENERATE ID & CODE =====




def generate_username(email=None, mobile=None, otp=None):
    if email:
        base = email.split("@")[0][:4]  # first 4 chars
    else:
        base = mobile[-4:]  # last 4 digits of mobile

    otp_part = otp[-3:] if otp else str(random.randint(100, 999))

    username = f"{base}{otp_part}".lower()

    # Ensure uniqueness
    while User.objects.filter(username=username).exists():
        random_suffix = "".join(random.choices(string.digits, k=3))
        username = f"{base}{random_suffix}"

    return username


# ========= TO GENERATE OTP=========


def generate_otp():
    return str(random.randint(100000, 999999))


# pyrefly: ignore [missing-import]
from rest_framework.views import APIView
# pyrefly: ignore [missing-import]
from rest_framework.response import Response
# pyrefly: ignore [missing-import]
from rest_framework import status

# from .serializers import SendOTPSerializer, VerifyOTPSerializer
from .models import OTP
import random
# pyrefly: ignore [missing-import]
from django.core.mail import send_mail

# pyrefly: ignore [missing-import]
from django.core.mail import EmailMultiAlternatives
# pyrefly: ignore [missing-import]
from django.template.loader import render_to_string




def send_otp_email(email, otp, user_name=None):
    subject = "Your OTP Code"

    html_content = render_to_string(
        "otp_email.html", {"otp": otp, "user_name": user_name}
    )

    email_message = EmailMultiAlternatives(
        subject=subject,
        body=f"Your OTP is {otp}",  # fallback (plain text)
        from_email="yash.error.1@gmail.com",
        to=[email],
    )

    email_message.attach_alternative(html_content, "text/html")
    email_message.send()




def parse_date(value):
    try:
        return pd.to_datetime(value).date() if pd.notna(value) else None
    except Exception:
        return None




def clean(value):
    return value if pd.notna(value) else None


# ----------------------------
# Column Mapping (Excel → Model)
# ----------------------------
COLUMN_MAPPING = {
    "GR No": "gr_no",
    "Surname": "surname",
    "Student Name": "name",
    "Father's Name": "father_name",
    "Mother's Name": "mother_name",
    "Aadhaar Card No": "aadhar_number",
    "Religion": "religion",
    "Caste Category": "scheduled_caste",
    "Place of Birth": "place_of_birth",
    "Date of Birth": "date_of_birth",
    "Admission Date": "admission_date",
    "Leaving Date": "leaving_date",
    "Last School Attended": "last_school",
    "Progress": "progress",
    "Conduct": "conduct",
    "Remarks": "remarks",
    "Mobile": "mobile",
    "Standard": "school_class",
    "Academic Year": "academic_year",
}


# ----------------------------
# Main Import Function
# ----------------------------


@transaction.atomic


def import_students_from_excel(file, school_id, use_bulk=True):
    df = pd.read_excel(file)
    df.columns = df.columns.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)

    school = School.objects.get(id=school_id)

    students = []
    errors = []

    # ✅ Track duplicates inside Excel
    excel_gr_set = set()

    # ✅ Fetch existing GR numbers from DB
    existing_gr_nos = set(
        Student.objects.filter(school=school).values_list("gr_no", flat=True)
    )

    for index, row in df.iterrows():
        try:
            data = {}
            for excel_col, model_field in COLUMN_MAPPING.items():
                data[model_field] = clean(row.get(excel_col))

            gr_no = str(data.get("gr_no")).strip() if data.get("gr_no") else None

            # ----------------------------
            # 🔴 GR NO VALIDATION
            # ----------------------------
            if not gr_no:
                errors.append(f"Row {index+2}: GR No is required")
                continue

            if gr_no in excel_gr_set:
                errors.append(f"Row {index+2}: Duplicate GR No '{gr_no}' in Excel")
                continue

            if gr_no in existing_gr_nos:
                errors.append(
                    f"Row {index+2}: GR No '{gr_no}' already exists for this school"
                )
                continue

            excel_gr_set.add(gr_no)

            # ----------------------------
            # Class validation
            # ----------------------------
            school_class = None

            if data.get("school_class"):
                class_name = str(data["school_class"]).strip()

                school_class = SchoolClass.objects.filter(
                    school_class=class_name,
                    school=school,
                ).first()

                if not school_class:
                    errors.append(f"Row {index+2}: Class '{class_name}' not found")
                    continue

            student_data = {
                "school": school,
                "gr_no": gr_no,
                "surname": data["surname"],
                "name": data["name"],
                "father_name": data["father_name"],
                "mother_name": data["mother_name"],
                "date_of_birth": parse_date(data["date_of_birth"]),
                "admission_date": parse_date(data["admission_date"]),
                "school_class": school_class,
                "academic_year": data["academic_year"],
                "mobile": data["mobile"],
                "aadhar_number": data["aadhar_number"],
            }

            extra_data = {
                "religion": data.get("religion"),
                "scheduled_caste": data.get("scheduled_caste"),
                "place_of_birth": data.get("place_of_birth"),
                "leaving_date": parse_date(data.get("leaving_date")),
                "last_school": data.get("last_school"),
                "progress": data.get("progress"),
                "conduct": data.get("conduct"),
                "remarks": data.get("remarks"),
            }

            students.append((student_data, extra_data))

        except Exception as e:
            errors.append(f"Row {index+2}: {str(e)}")

    # ----------------------------
    # STOP if any error
    # ----------------------------
    if errors:
        # rollback automatically due to atomic
        return {"created": 0, "errors": errors}

    # ----------------------------
    # Save to DB
    # ----------------------------
    created_count = 0

    if use_bulk:
        student_objects = [Student(**student_data) for student_data, _ in students]
        Student.objects.bulk_create(student_objects)

        created_students = Student.objects.filter(
            school=school,
            gr_no__in=[student_data["gr_no"] for student_data, _ in students],
        )
        student_map = {student.gr_no: student for student in created_students}

        extra_objects = []
        for student_data, extra_data in students:
            student = student_map.get(student_data["gr_no"])
            if student and any(extra_data.values()):
                extra_objects.append(StudentExtraData(student=student, **extra_data))

        if extra_objects:
            StudentExtraData.objects.bulk_create(extra_objects)

        created_count = len(student_objects)
    else:
        for student_data, extra_data in students:
            student = Student.objects.create(**student_data)
            if any(extra_data.values()):
                StudentExtraData.objects.create(student=student, **extra_data)
            created_count += 1

    return {"created": created_count, "errors": []}


# ----------------------------
# API View
# ----------------------------




def optimize_image(uploaded_file, size=(800, 800), quality=60):
    """
    Resize + compress image to avoid Face++ 413 error
    """

    image = Image.open(uploaded_file)
    image = image.convert("RGB")
    image.thumbnail(size)

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)

    buffer.seek(0)
    return buffer


# -------------------------
# VIEW
# -------------------------


def progress_group(school_id, student_id):
    return f"school_{school_id}_student_{student_id}_progress-report"






