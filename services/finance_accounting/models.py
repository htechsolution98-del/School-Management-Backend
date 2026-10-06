from django.db import models


class FeeType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "finance_fee_type"

    def __str__(self):
        return self.name


class FeeWiseClass(models.Model):
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE)
    school_class = models.ForeignKey("academic_timetable.SchoolClass", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "finance_fee_wise_class"


class StudentFee(models.Model):
    student = models.ForeignKey("student_admission.Student", on_delete=models.CASCADE, related_name="fees")
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    is_paid = models.BooleanField(default=False)

    class Meta:
        db_table = "finance_student_fee"


class StudentFeePayment(models.Model):
    student_fee = models.ForeignKey(StudentFee, on_delete=models.CASCADE, related_name="payments")
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=50, default="CASH")
    payment_date = models.DateTimeField(auto_now_add=True)
    receipt_no = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "finance_student_fee_payment"


class SalaryComponent(models.Model):
    name = models.CharField(max_length=100)
    component_type = models.CharField(max_length=50, default="EARNING")

    class Meta:
        db_table = "finance_salary_component"
