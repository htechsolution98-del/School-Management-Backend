import os
import django
import random
from datetime import date

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sms.settings")
django.setup()

from django.contrib.auth import get_user_model
from sms_app.models import School, SchoolClass, Division, AcademicYear, Student, ExamRoom, FormField, StudentFieldValue

User = get_user_model()

STUDENT_DATA = [
    {"name": "Yuji", "surname": "Itadori", "father": "Jin Itadori", "mother": "Kaori Itadori", "gender": "M"},
    {"name": "Megumi", "surname": "Fushiguro", "father": "Toji Fushiguro", "mother": "Mamaguro", "gender": "M"},
    {"name": "Nobara", "surname": "Kugisaki", "father": "Daiki Kugisaki", "mother": "Sayuri Kugisaki", "gender": "F"},
    {"name": "Maki", "surname": "Zenin", "father": "Ogi Zenin", "mother": "Mrs. Zenin", "gender": "F"},
    {"name": "Toge", "surname": "Inumaki", "father": "Takeshi Inumaki", "mother": "Hana Inumaki", "gender": "M"},
    {"name": "Panda", "surname": "Yaga", "father": "Masamichi Yaga", "mother": "Elena Yaga", "gender": "M"},
    {"name": "Yuta", "surname": "Okkotsu", "father": "Hiroshi Okkotsu", "mother": "Aoi Okkotsu", "gender": "M"},
    {"name": "Aoi", "surname": "Todo", "father": "Ryu Todo", "mother": "Takako Todo", "gender": "M"},
    {"name": "Mai", "surname": "Zenin", "father": "Ogi Zenin", "mother": "Mrs. Zenin", "gender": "F"},
    {"name": "Kasumi", "surname": "Miwa", "father": "Kenji Miwa", "mother": "Satoko Miwa", "gender": "F"},
    {"name": "Noritoshi", "surname": "Kamo", "father": "Shuji Kamo", "mother": "Chiyo Kamo", "gender": "M"},
    {"name": "Momo", "surname": "Nishimiya", "father": "George Nishimiya", "mother": "Kiko Nishimiya", "gender": "F"},
    {"name": "Kokichi", "surname": "Muta", "father": "Shin Muta", "mother": "Emi Muta", "gender": "M"},
    {"name": "Arata", "surname": "Nitta", "father": "Ren Nitta", "mother": "Akari Nitta", "gender": "M"},
    {"name": "Junpei", "surname": "Yoshino", "father": "Satoru Yoshino", "mother": "Nagi Yoshino", "gender": "M"},
    {"name": "Riko", "surname": "Amanai", "father": "Tetsuo Amanai", "mother": "Misato Kuroi", "gender": "F"},
    {"name": "Kento", "surname": "Nanami", "father": "Daisuke Nanami", "mother": "Keiko Nanami", "gender": "M"},
    {"name": "Suguru", "surname": "Geto", "father": "Mr. Geto", "mother": "Mrs. Geto", "gender": "M"},
    {"name": "Shoko", "surname": "Ieiri", "father": "Tadashi Ieiri", "mother": "Yumi Ieiri", "gender": "F"},
    {"name": "Satoru", "surname": "Gojo", "father": "Lord Gojo", "mother": "Lady Gojo", "gender": "M"},
]

def seed():
    print("[+] Starting student seed process...")

    # 1. Identify School
    school = None
    user = User.objects.filter(email__iexact="jujutsu@gmail.com").first()
    if user and user.school:
        school = user.school
    else:
        school = School.objects.filter(name__icontains="jujutsu").first() or School.objects.filter(id=16).first() or School.objects.first()

    if not school:
        print("[!] Error: School not found!")
        return

    print(f"[+] School Found: ID {school.id} - '{school.name}'")

    # 2. Identify / Ensure Class 8
    class_obj = SchoolClass.objects.filter(school=school, school_class__iexact="class 8").first()
    if not class_obj:
        class_obj = SchoolClass.objects.filter(school=school, school_class__icontains="8").first()
    if not class_obj:
        class_obj = SchoolClass.objects.create(school=school, school_class="class 8", is_rte_applicable=False)
        print(f"[+] Created Class: {class_obj.school_class} (ID: {class_obj.id})")
    else:
        print(f"[+] Target Class: '{class_obj.school_class}' (ID: {class_obj.id})")

    # 3. Identify / Ensure Division 'a'
    div_obj = Division.objects.filter(school=school, SchoolClass=class_obj, division__iexact="a").first()
    if not div_obj:
        div_obj = Division.objects.create(school=school, SchoolClass=class_obj, division="a", capacity=40)
        print(f"[+] Created Division: 'a' for Class '{class_obj.school_class}' (ID: {div_obj.id})")
    else:
        print(f"[+] Target Division: '{div_obj.division}' (ID: {div_obj.id})")

    # 4. Identify / Ensure Academic Year
    academic_year = AcademicYear.objects.filter(school=school, is_active=True).first()
    if not academic_year:
        academic_year = AcademicYear.objects.filter(school=school).first()
    if not academic_year:
        academic_year = AcademicYear.objects.create(school=school, name="2026-27", is_active=True)
        print(f"[+] Created Academic Year: {academic_year.name}")
    else:
        print(f"[+] Target Academic Year: '{academic_year.name}' (ID: {academic_year.id})")

    # 5. Ensure Active Exam Room
    room = ExamRoom.objects.filter(school=school, is_active=True).first()
    if not room:
        room = ExamRoom.objects.create(school=school, room_number="Room 1", building_block="Main Wing", capacity=40, is_active=True)
        print(f"[+] Created Exam Room: {room.room_number} (Capacity: {room.capacity})")
    elif room.capacity < 30:
        room.capacity = 40
        room.save()
        print(f"[+] Updated Exam Room Capacity: {room.room_number} -> {room.capacity}")
    else:
        print(f"[+] Exam Room Available: '{room.room_number}' (Capacity: {room.capacity})")

    # 6. Ensure FormField for Gender
    gender_field = FormField.objects.filter(school=school, label__icontains="gender").first()
    if not gender_field:
        gender_field = FormField.objects.create(school=school, label="gender", field_type="select")
        print(f"[+] Created FormField: 'gender' (ID: {gender_field.id})")
    else:
        print(f"[+] Found FormField: 'gender' (ID: {gender_field.id})")

    # 7. Seed / Update 20 Students
    created_count = 0
    updated_count = 0

    for idx, st_info in enumerate(STUDENT_DATA, start=1):
        gr_no = f"GR-8{idx:02d}"
        roll_no = str(idx)
        mobile = f"98765{idx:05d}"
        dob_year = random.randint(2011, 2013)
        dob_month = random.randint(1, 12)
        dob_day = random.randint(1, 28)
        dob = date(dob_year, dob_month, dob_day)
        gender_str = "Male" if st_info["gender"] == "M" else "Female"

        # Check existing student by gr_no or roll_no in class
        student = Student.objects.filter(school=school, gr_no=gr_no).first()

        if not student:
            student = Student.objects.create(
                school=school,
                school_class=class_obj,
                division="a",
                roll_no=roll_no,
                gr_no=gr_no,
                name=st_info["name"],
                surname=st_info["surname"],
                father_name=st_info["father"],
                mother_name=st_info["mother"],
                date_of_birth=dob,
                mobile=mobile,
                admission_date=date(2026, 6, 1),
                academic_year=academic_year,
                is_verified=True,
                is_active=True,
            )
            created_count += 1
            print(f"  [+] Created Roll #{roll_no:>2s} | {st_info['name']} {st_info['surname']} ({gender_str}, {gr_no}) - Class 8 Div a")
        else:
            student.school_class = class_obj
            student.division = "a"
            student.roll_no = roll_no
            student.name = st_info["name"]
            student.surname = st_info["surname"]
            student.father_name = st_info["father"]
            student.mother_name = st_info["mother"]
            student.academic_year = academic_year
            student.is_verified = True
            student.is_active = True
            student.save()
            updated_count += 1
            print(f"  [*] Updated Roll #{roll_no:>2s} | {st_info['name']} {st_info['surname']} ({gender_str}, {gr_no}) - Class 8 Div a")

        # Set Demographic Gender Value
        StudentFieldValue.objects.update_or_create(
            student=student,
            field=gender_field,
            defaults={"value": gender_str, "school": school}
        )

    total_in_class = Student.objects.filter(school=school, school_class=class_obj, division__iexact="a").count()
    print("\n" + "=" * 60)
    print(f"[SUCCESS] Seeding Completed!")
    print(f"Newly Created Students: {created_count}")
    print(f"Updated Existing Students: {updated_count}")
    print(f"Total Students in Class 8 Division 'a': {total_in_class}")
    print("=" * 60)

if __name__ == "__main__":
    seed()
