import calendar
from datetime import date
from decimal import Decimal
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from sms_app.models import Staff, StaffSalaryPayment, PayrollPayslip, PayrollRun, School
from sms_app.permissions import IsFeeManager, IsTrusteeUser, IsClerkOrAdmin
from sms_app.services.payroll_service import (
    generate_payslip,
    generate_payroll_run,
    get_salary_preview,
    get_month_date_range,
    MissingPunchError,
)


def get_request_school(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None
    if hasattr(user, "school") and user.school:
        return user.school
    staff = Staff.objects.filter(user=user).select_related("school").first()
    if staff and staff.school:
        return staff.school
    return None


def number_to_words_inr(num):
    try:
        n = int(Decimal(str(num)).quantize(Decimal("1")))
    except Exception:
        return ""
    if n == 0:
        return "Zero Rupees Only"

    units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
             "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
             "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _two_digits(val):
        if val < 20:
            return units[val]
        t = tens[val // 10]
        u = units[val % 10]
        return f"{t} {u}".strip()

    def _three_digits(val):
        h = val // 100
        rem = val % 100
        h_str = f"{units[h]} Hundred" if h > 0 else ""
        rem_str = _two_digits(rem) if rem > 0 else ""
        if h_str and rem_str:
            return f"{h_str} and {rem_str}"
        return h_str or rem_str

    parts = []
    crores = n // 10000000
    n %= 10000000
    if crores > 0:
        parts.append(f"{_three_digits(crores)} Crore")

    lakhs = n // 100000
    n %= 100000
    if lakhs > 0:
        parts.append(f"{_three_digits(lakhs)} Lakh")

    thousands = n // 1000
    n %= 1000
    if thousands > 0:
        parts.append(f"{_three_digits(thousands)} Thousand")

    if n > 0:
        parts.append(_three_digits(n))

    words = " ".join(parts).strip()
    return f"Indian Rupees {words} Only"


def format_currency_inr(amount):
    try:
        val = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
        s, *d = f"{val:.2f}".split(".")
        d_part = f".{d[0]}" if d else ".00"
        if len(s) > 3:
            last3 = s[-3:]
            rest = s[:-3]
            res = ",".join([rest[max(i - 2, 0):i] for i in range(len(rest), 0, -2)][::-1])
            formatted = f"{res},{last3}{d_part}"
        else:
            formatted = f"{s}{d_part}"
        return f"₹{formatted}"
    except Exception:
        return f"₹{amount}"


def render_payslip_html(payment, school, request):
    breakdown = payment.component_breakdown or {}
    earnings = list(breakdown.get("earnings") or [])
    deductions = list(breakdown.get("deductions") or [])

    # If breakdown lists are empty, fall back to snapshot
    if not earnings and not deductions and payment.component_snapshot:
        for c in payment.component_snapshot:
            item = {"name": c.get("name", "Component"), "amount": str(c.get("amount", "0.00"))}
            if str(c.get("component_type", "")).lower() == "earning":
                earnings.append(item)
            else:
                deductions.append(item)

    # Ensure Basic Salary is present in earnings
    has_basic = any("basic" in str(e.get("name", "")).lower() for e in earnings)
    if not has_basic and payment.basic_salary and float(payment.basic_salary) > 0:
        earnings.insert(0, {"name": "Basic Salary", "amount": str(payment.basic_salary)})

    if not earnings:
        earnings = [{"name": "Basic Salary", "amount": str(payment.basic_salary or payment.net_salary)}]

    computed_gross = sum(float(e.get("amount", 0)) for e in earnings) if earnings else float(payment.basic_salary or 0)
    gross_display = float(payment.total_earnings or 0)
    if gross_display <= 0:
        gross_display = computed_gross

    computed_deductions = sum(float(d.get("amount", 0)) for d in deductions) if deductions else float(payment.total_deductions or 0)
    deductions_display = float(payment.total_deductions or 0)
    if deductions_display <= 0:
        deductions_display = computed_deductions

    net_display = float(payment.net_salary or 0)
    if net_display <= 0:
        net_display = max(0.0, gross_display - deductions_display)

    working_days = breakdown.get("working_days", payment.working_days or 30)
    present_days = breakdown.get("present_days", float(payment.present_days or 0))
    paid_leaves = breakdown.get("paid_leaves", 0)
    unpaid_leaves = breakdown.get("unpaid_leaves", breakdown.get("lwp_days", 0))
    lwp_deduction = breakdown.get("lop_deduction_amount", breakdown.get("lwp_deduction", payment.attendance_deduction or 0))

    try:
        parts = str(payment.salary_month).split("-")
        month_label = date(int(parts[0]), int(parts[1]), 1).strftime("%B %Y")
    except Exception:
        month_label = str(payment.salary_month)

    school_name = getattr(school, "name", "Institutional Academy")
    school_address = getattr(school, "address", "") or getattr(school, "city", "")
    school_contact = getattr(school, "contact_number", "") or getattr(school, "email", "")
    logo_url = getattr(school, "logo", "") or "/logo.png"

    amount_in_words = number_to_words_inr(net_display)

    earnings_rows = "".join([
        f'<tr><td style="padding: 9px 12px; border-bottom: 1px solid #f1f5f9; color: #334155; font-size: 13px;">{e.get("name")}</td>'
        f'<td style="padding: 9px 12px; border-bottom: 1px solid #f1f5f9; text-align: right; font-weight: 600; color: #0f172a; font-size: 13px;">{format_currency_inr(e.get("amount"))}</td></tr>'
        for e in earnings
    ])

    deductions_rows = "".join([
        f'<tr><td style="padding: 9px 12px; border-bottom: 1px solid #f1f5f9; color: #334155; font-size: 13px;">{d.get("name")}</td>'
        f'<td style="padding: 9px 12px; border-bottom: 1px solid #f1f5f9; text-align: right; font-weight: 600; color: #dc2626; font-size: 13px;">{format_currency_inr(d.get("amount"))}</td></tr>'
        for d in deductions
    ]) or '<tr><td colspan="2" style="padding: 9px 12px; text-align: center; color: #94a3b8; font-size: 12px; font-style: italic;">No deductions applied</td></tr>'

    payment_status_badge = (
        '<span style="background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; padding: 3px 10px; border-radius: 9999px; font-weight: 700; font-size: 11px; text-transform: uppercase;">Paid & Reconciled</span>'
        if payment.payment_status == "paid" else
        '<span style="background: #fffbeb; color: #b45309; border: 1px solid #fde68a; padding: 3px 10px; border-radius: 9999px; font-weight: 700; font-size: 11px; text-transform: uppercase;">Draft / Pending Disbursement</span>'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Salary Slip - {payment.staff_name} ({month_label})</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  body {{ background: #f8fafc; color: #1e293b; padding: 24px; }}
  .container {{ max-width: 820px; margin: 0 auto; background: #ffffff; border-radius: 16px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.06), 0 8px 10px -6px rgba(0,0,0,0.04); border: 1px solid #e2e8f0; overflow: hidden; }}
  .no-print {{ display: flex; justify-content: space-between; align-items: center; background: #0f172a; color: #ffffff; padding: 12px 24px; font-size: 13px; }}
  .btn {{ background: #4f46e5; color: #ffffff; border: none; padding: 8px 18px; border-radius: 8px; font-weight: 600; cursor: pointer; transition: background 0.15s; font-size: 13px; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }}
  .btn:hover {{ background: #4338ca; }}
  .header {{ padding: 28px 32px; border-bottom: 2px solid #4f46e5; display: flex; justify-content: space-between; align-items: center; gap: 20px; }}
  .school-title {{ font-size: 22px; font-weight: 800; color: #1e1b4b; letter-spacing: -0.02em; }}
  .school-sub {{ font-size: 12px; color: #64748b; margin-top: 2px; }}
  .slip-badge {{ text-align: right; }}
  .slip-label {{ font-size: 11px; font-weight: 800; color: #4f46e5; text-transform: uppercase; letter-spacing: 0.08em; }}
  .slip-month {{ font-size: 16px; font-weight: 700; color: #0f172a; margin-top: 2px; }}
  .body-content {{ padding: 28px 32px; }}
  .meta-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; background: #f8fafc; padding: 18px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 24px; font-size: 12px; }}
  .meta-item .label {{ color: #64748b; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }}
  .meta-item .val {{ font-weight: 700; color: #0f172a; font-size: 13px; margin-top: 3px; word-break: break-word; }}
  .duty-card {{ background: #f1f5f9; border-radius: 12px; padding: 14px 18px; margin-bottom: 24px; border-left: 4px solid #4f46e5; }}
  .duty-title {{ font-size: 11px; font-weight: 800; text-transform: uppercase; color: #475569; letter-spacing: 0.05em; margin-bottom: 10px; }}
  .duty-metrics {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; text-align: center; }}
  .duty-stat {{ background: #ffffff; padding: 10px 6px; border-radius: 8px; border: 1px solid #e2e8f0; }}
  .duty-stat .num {{ font-size: 15px; font-weight: 800; color: #0f172a; display: block; }}
  .duty-stat .lbl {{ font-size: 10px; color: #64748b; font-weight: 600; text-transform: uppercase; margin-top: 2px; display: block; }}
  .table-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }}
  .pane {{ border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }}
  .pane-head {{ background: #f8fafc; padding: 12px 16px; font-size: 12px; font-weight: 800; color: #334155; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; }}
  table {{ width: 100%; border-collapse: collapse; }}
  .pane-total {{ background: #faf5ff; padding: 12px 16px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; font-weight: 800; font-size: 13px; color: #581c87; }}
  .net-card {{ background: linear-gradient(135deg, #4f46e5 0%, #3730a3 100%); color: #ffffff; padding: 22px 28px; border-radius: 14px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; box-shadow: 0 4px 15px rgba(79, 70, 229, 0.25); }}
  .net-card .title {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: #c7d2fe; font-weight: 700; }}
  .net-card .amt {{ font-size: 28px; font-weight: 900; letter-spacing: -0.02em; margin-top: 4px; }}
  .net-card .words {{ font-size: 12px; color: #e0e7ff; font-weight: 500; margin-top: 4px; font-style: italic; }}
  .footer-sig {{ display: flex; justify-content: space-between; margin-top: 48px; padding-top: 20px; border-top: 1px dashed #cbd5e1; font-size: 12px; color: #64748b; }}
  .sig-box {{ text-align: center; width: 200px; }}
  .sig-line {{ border-bottom: 1px solid #94a3b8; height: 32px; margin-bottom: 8px; }}
  @media print {{
    body {{ background: #ffffff; padding: 0; }}
    .container {{ box-shadow: none; border: none; max-width: 100%; border-radius: 0; }}
    .no-print {{ display: none !important; }}
    @page {{ margin: 12mm; size: A4 portrait; }}
  }}
</style>
</head>
<body>

<div class="no-print">
  <div><strong>Trustee Audit View:</strong> Official Salary Slip for {payment.staff_name} ({month_label})</div>
  <div style="display: flex; gap: 8px;">
    <button class="btn" onclick="window.print()">🖨️ Print / Save PDF</button>
  </div>
</div>

<div class="container">
  <div class="header">
    <div>
      <h1 class="school-title">{school_name}</h1>
      <p class="school-sub">{school_address} {f"• {school_contact}" if school_contact else ""}</p>
      <p style="font-size: 11px; color: #4f46e5; font-weight: 700; margin-top: 4px; text-transform: uppercase;">Official Staff Compensation Statement</p>
    </div>
    <div class="slip-badge">
      <div class="slip-label">Monthly Payslip</div>
      <div class="slip-month">{month_label}</div>
      <div style="margin-top: 6px;">{payment_status_badge}</div>
    </div>
  </div>

  <div class="body-content">
    <div class="meta-grid">
      <div class="meta-item">
        <div class="label">Employee Name</div>
        <div class="val">{payment.staff_name}</div>
      </div>
      <div class="meta-item">
        <div class="label">Staff ID</div>
        <div class="val">EMP-{payment.staff_id}</div>
      </div>
      <div class="meta-item">
        <div class="label">Designation / Role</div>
        <div class="val">{payment.staff_category or "Staff"}</div>
      </div>
      <div class="meta-item">
        <div class="label">Department</div>
        <div class="val">{getattr(payment.staff, "department", None) or payment.staff_category or "General"}</div>
      </div>
      <div class="meta-item">
        <div class="label">Payment Mode</div>
        <div class="val" style="text-transform: capitalize;">{payment.payment_mode or "Offline"}</div>
      </div>
      <div class="meta-item">
        <div class="label">Receipt Number</div>
        <div class="val">{payment.receipt_number or f"SAL-{payment.id}"}</div>
      </div>
      <div class="meta-item">
        <div class="label">Transaction Ref</div>
        <div class="val">{payment.transaction_id or "N/A"}</div>
      </div>
      <div class="meta-item">
        <div class="label">Disbursement Date</div>
        <div class="val">{payment.payment_date.strftime("%d %b %Y") if payment.payment_date else (payment.created_at.strftime("%d %b %Y") if payment.created_at else "—")}</div>
      </div>
    </div>

    <div class="duty-card">
      <div class="duty-title">Attendance & Duty Summary ({month_label})</div>
      <div class="duty-metrics">
        <div class="duty-stat">
          <span class="num">{working_days}</span>
          <span class="lbl">Total Days</span>
        </div>
        <div class="duty-stat" style="border-color: #bbf7d0;">
          <span class="num" style="color: #15803d;">{present_days}</span>
          <span class="lbl" style="color: #166534;">Present</span>
        </div>
        <div class="duty-stat" style="border-color: #c7d2fe;">
          <span class="num" style="color: #4338ca;">{paid_leaves}</span>
          <span class="lbl" style="color: #3730a3;">Paid Leaves</span>
        </div>
        <div class="duty-stat" style="border-color: #fecaca;">
          <span class="num" style="color: #b91c1c;">{unpaid_leaves}</span>
          <span class="lbl" style="color: #991b1b;">LWP (Unpaid)</span>
        </div>
        <div class="duty-stat" style="border-color: #fed7aa;">
          <span class="num" style="color: #c2410c;">{format_currency_inr(lwp_deduction)}</span>
          <span class="lbl" style="color: #9a3412;">LWP Deduction</span>
        </div>
      </div>
    </div>

    <div class="table-grid">
      <div class="pane">
        <div class="pane-head">
          <span>Earnings</span>
          <span>Amount</span>
        </div>
        <table>
          <tbody>
            {earnings_rows}
          </tbody>
        </table>
        <div class="pane-total">
          <span>Gross Earnings</span>
          <span>{format_currency_inr(gross_display)}</span>
        </div>
      </div>

      <div class="pane">
        <div class="pane-head" style="color: #991b1b; background: #fef2f2;">
          <span>Deductions</span>
          <span>Amount</span>
        </div>
        <table>
          <tbody>
            {deductions_rows}
          </tbody>
        </table>
        <div class="pane-total" style="background: #fef2f2; color: #991b1b;">
          <span>Total Deductions</span>
          <span>{format_currency_inr(deductions_display)}</span>
        </div>
      </div>
    </div>

    <div class="net-card">
      <div>
        <div class="title">Net Payable Compensation</div>
        <div class="amt">{format_currency_inr(net_display)}</div>
        <div class="words">{amount_in_words}</div>
      </div>
      <div style="text-align: right;">
        <span style="display: inline-block; background: rgba(255,255,255,0.18); padding: 6px 14px; border-radius: 8px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">
          {payment.payment_status.upper()}
        </span>
      </div>
    </div>

    <div class="footer-sig">
      <div class="sig-box">
        <div class="sig-line"></div>
        <div>Employee Signature</div>
      </div>
      <div class="sig-box">
        <div class="sig-line"></div>
        <div>Authorized Signatory / Trustee</div>
      </div>
    </div>
  </div>
</div>

</body>
</html>"""
    return html


class SalaryPreviewAPIView(APIView):
    """
    GET /api/payroll/preview/?staff=<id>&salary_month=<YYYY-MM>
    Calculates attendance, leaves, LWP deduction, and net salary preview dynamically.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school = get_request_school(request)
        if not school:
            return Response({"error": "User school is not configured."}, status=status.HTTP_400_BAD_REQUEST)

        staff_id = request.query_params.get("staff") or request.query_params.get("staff_id")
        salary_month = request.query_params.get("salary_month")

        if not staff_id or not salary_month:
            return Response(
                {"error": "Both 'staff' and 'salary_month' (YYYY-MM) query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            preview = get_salary_preview(staff_id=int(staff_id), salary_month=salary_month, school=school)
            return Response(preview, status=status.HTTP_200_OK)
        except ValidationError as ve:
            return Response({"error": str(ve.detail if hasattr(ve, "detail") else ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BulkSalaryGenerateAPIView(APIView):
    """
    POST /api/payroll/bulk-generate/
    Batch-process and generate draft salaries for all active staff of the authenticated school.
    """
    permission_classes = [IsAuthenticated, IsFeeManager | IsTrusteeUser]

    def post(self, request):
        school = get_request_school(request)
        if not school:
            return Response({"error": "User school is not configured."}, status=status.HTTP_400_BAD_REQUEST)

        salary_month = request.data.get("salary_month")
        if not salary_month:
            today = timezone.localdate()
            year, month = today.year, today.month
            salary_month = f"{year}-{month:02d}"
        else:
            try:
                parts = str(salary_month).strip().split("-")
                year = int(parts[0])
                month = int(parts[1])
            except Exception:
                return Response({"error": "Invalid salary_month format. Use YYYY-MM."}, status=status.HTTP_400_BAD_REQUEST)

        payment_mode = request.data.get("payment_mode", "offline")
        try:
            result = generate_payroll_run(school=school, month=month, year=year, staff_id=None)
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as ve:
            return Response({"error": str(ve.detail if hasattr(ve, "detail") else ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BulkSalaryDisburseAPIView(APIView):
    """
    POST /api/payroll/bulk-disburse/
    Batch-update the status of all filtered 'Pending/Draft' salaries to 'Paid/Disbursed' in a single click.
    """
    permission_classes = [IsAuthenticated, IsFeeManager | IsTrusteeUser]

    def post(self, request):
        school = get_request_school(request)
        if not school:
            return Response({"error": "User school is not configured."}, status=status.HTTP_400_BAD_REQUEST)

        salary_month = request.data.get("salary_month")
        if not salary_month:
            today = timezone.localdate()
            salary_month = f"{today.year}-{today.month:02d}"

        payment_ids = request.data.get("payment_ids")
        staff_ids = request.data.get("staff_ids")
        payment_mode = request.data.get("payment_mode", "offline")

        qs = StaffSalaryPayment.objects.filter(school=school, salary_month=salary_month)

        if payment_ids and isinstance(payment_ids, list):
            valid_pids = [int(pid) for pid in payment_ids if pid]
            if valid_pids:
                qs = qs.filter(id__in=valid_pids)
        elif staff_ids and isinstance(staff_ids, list):
            valid_sids = [int(sid) for sid in staff_ids if sid]
            if valid_sids:
                qs = qs.filter(staff_id__in=valid_sids)

        pending_qs = qs.exclude(payment_status="paid")
        count = pending_qs.count()

        if count == 0:
            return Response({
                "status": "success",
                "disbursed_count": 0,
                "message": "No pending salary records found to disburse.",
            }, status=status.HTTP_200_OK)

        now = timezone.now()
        updated_count = pending_qs.update(
            payment_status="paid",
            payment_mode=payment_mode,
            payment_date=now,
            paid_by=request.user,
        )

        return Response({
            "status": "success",
            "disbursed_count": updated_count,
            "message": f"Successfully approved and disbursed {updated_count} salaries.",
        }, status=status.HTTP_200_OK)


class PayslipDocumentView(APIView):
    """
    GET /api/payroll/payslip/<int:pk>/
    Returns structured Payslip format (HTML or JSON) showing Basic, Earnings, Deductions, LWP, Net Payable.
    Supports JWT Bearer header, URL ?token= param, and cookies for browser new tab printing.
    """
    permission_classes = [AllowAny]

    def get(self, request, pk=None):
        # 1. Authenticate user (Supports Header, Query Param ?token=, or Cookie)
        user = request.user
        if not user or not user.is_authenticated:
            token = request.query_params.get("token") or request.COOKIES.get("access_token")
            if token:
                try:
                    from rest_framework_simplejwt.tokens import AccessToken
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    access_token = AccessToken(token)
                    user_id = access_token.get("user_id")
                    if user_id:
                        user = User.objects.filter(id=user_id).first()
                        if user:
                            request.user = user
                except Exception:
                    pass

        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentication credentials were not provided or have expired."}, status=status.HTTP_401_UNAUTHORIZED)

        school = get_request_school(request)
        if not school:
            return Response({"error": "User school is not configured."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Resolve Payment / Payslip Record
        requested_month = request.query_params.get("salary_month")
        staff_id_param = request.query_params.get("staff_id")

        payment = None
        if pk:
            # Try pk as StaffSalaryPayment.id
            payment = StaffSalaryPayment.objects.filter(pk=pk, school=school).select_related("staff", "school", "paid_by").first()

            # Try pk as PayrollPayslip.id
            if not payment:
                payslip = PayrollPayslip.objects.filter(pk=pk, payroll_run__school=school).select_related("staff", "payroll_run").first()
                if payslip:
                    month_str = payslip.payroll_run.salary_month.strftime("%Y-%m") if payslip.payroll_run and payslip.payroll_run.salary_month else None
                    payment = StaffSalaryPayment.objects.filter(staff=payslip.staff, salary_month=month_str, school=school).first()

            # Try pk as Staff.id
            if not payment:
                staff_qs = StaffSalaryPayment.objects.filter(staff_id=pk, school=school)
                if requested_month:
                    payment = staff_qs.filter(salary_month=requested_month).first()
                else:
                    payment = staff_qs.order_by("-salary_month").first()

        # If still not found, check staff_id param
        if not payment and staff_id_param:
            try:
                staff_qs = StaffSalaryPayment.objects.filter(staff_id=int(staff_id_param), school=school)
                if requested_month:
                    payment = staff_qs.filter(salary_month=requested_month).first()
                else:
                    payment = staff_qs.order_by("-salary_month").first()
            except Exception:
                pass

        # If payment record doesn't exist yet, but Staff exists, generate dynamically
        if not payment:
            target_staff = None
            if pk:
                target_staff = Staff.objects.filter(pk=pk, school=school).first()
            if not target_staff and staff_id_param:
                try:
                    target_staff = Staff.objects.filter(pk=int(staff_id_param), school=school).first()
                except Exception:
                    pass

            if target_staff:
                if requested_month:
                    try:
                        p_parts = str(requested_month).strip().split("-")
                        p_year = int(p_parts[0])
                        p_month = int(p_parts[1])
                    except Exception:
                        today = timezone.localdate()
                        p_year, p_month = today.year, today.month
                else:
                    today = timezone.localdate()
                    p_year, p_month = today.year, today.month

                try:
                    from sms_app.services.payroll_service import generate_payslip
                    generate_payslip(target_staff, p_month, p_year, preview_only=False)
                    payment = StaffSalaryPayment.objects.filter(
                        staff=target_staff,
                        salary_month=f"{p_year}-{p_month:02d}",
                        school=school
                    ).first()
                except Exception:
                    pass

        if not payment:
            return Response({"error": "Salary slip record not found for this institution."}, status=status.HTTP_404_NOT_FOUND)

        # 3. Role-based row security: Non-managers can only view their own slip
        from sms_app.dynamic_hr_views import _is_trustee_or_superadmin, _get_staff_for_user
        if not _is_trustee_or_superadmin(request.user):
            staff_user = _get_staff_for_user(request.user)
            if not staff_user or payment.staff_id != staff_user.id:
                raise PermissionDenied("You do not have permission to view this salary slip.")

        requested_format = request.query_params.get("format", "").lower()
        accept_header = request.META.get("HTTP_ACCEPT", "")

        if requested_format == "html" or ("text/html" in accept_header and requested_format != "json"):
            html_content = render_payslip_html(payment, school, request)
            return HttpResponse(html_content, content_type="text/html; charset=utf-8")

        # Return structured JSON
        breakdown = payment.component_breakdown or {}
        gross_val = payment.total_earnings if (payment.total_earnings and float(payment.total_earnings) > 0) else breakdown.get("gross_earnings", payment.basic_salary)
        ded_val = payment.total_deductions if (payment.total_deductions and float(payment.total_deductions) > 0) else breakdown.get("total_deductions", "0.00")
        net_val = payment.net_salary if (payment.net_salary and float(payment.net_salary) > 0) else breakdown.get("net_salary", str(max(0.0, float(gross_val or 0) - float(ded_val or 0))))

        return Response({
            "id": payment.id,
            "staff_id": payment.staff_id,
            "staff_name": payment.staff_name,
            "staff_category": payment.staff_category,
            "salary_month": payment.salary_month,
            "basic_salary": str(payment.basic_salary),
            "total_earnings": str(gross_val),
            "gross_earnings": str(gross_val),
            "total_deductions": str(ded_val),
            "net_salary": str(net_val),
            "paid_amount": str(payment.paid_amount or net_val),
            "payment_mode": payment.payment_mode,
            "payment_status": payment.payment_status,
            "receipt_number": payment.receipt_number,
            "working_days": payment.working_days or breakdown.get("working_days", 30),
            "present_days": float(payment.present_days or breakdown.get("present_days", 0)),
            "paid_leaves": float(breakdown.get("paid_leaves", 0)),
            "unpaid_leaves": float(breakdown.get("unpaid_leaves", 0)),
            "attendance_deduction": str(payment.attendance_deduction or breakdown.get("lop_deduction_amount", "0.00")),
            "component_breakdown": breakdown,
        }, status=status.HTTP_200_OK)

