import ast
import calendar
import operator
import re
from datetime import date
from decimal import Decimal
from typing import Any
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from sms_app.models import (
    Staff,
    Attendance,
    AttendanceRegularization,
    LeavePerDay,
    SalaryStructure,
    SalaryComponent,
    StaffSalaryComponent,
    PayrollRun,
    PayrollPayslip,
    StaffSalaryPayment,
)


SAFE_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

SAFE_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_SAFE_OPERATORS = {**SAFE_BIN_OPS, **SAFE_UNARY_OPS}


def safe_eval(expr: str, variables: dict[str, Any] | None = None) -> Decimal:
    """
    Safely evaluate a mathematical formula string using Python's ast module.
    Never uses unsafe eval(). Supports +, -, *, /, //, %, **, unary +/-, numbers, and variable names.
    Returns a Decimal result, or Decimal("0.00") if evaluation fails, contains typos, or divides by zero.
    """
    if not expr or not isinstance(expr, str):
        return Decimal("0.00")

    var_map: dict[str, Decimal] = {}
    if variables:
        for k, v in variables.items():
            if k is not None:
                try:
                    var_map[k.strip().lower()] = Decimal(str(v or 0))
                except Exception:
                    pass

    def _eval_node(node):
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, Decimal)):
                return Decimal(str(node.value))
            raise ValueError(f"Unsupported constant type: {type(node.value)}")
        elif hasattr(ast, "Num") and isinstance(node, ast.Num):
            return Decimal(str(getattr(node, "n")))
        elif isinstance(node, ast.Name):
            key = node.id.strip().lower()
            if key in var_map:
                return var_map[key]
            raise KeyError(f"Unknown variable in formula: {node.id}")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_BIN_OPS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == Decimal("0"):
                raise ZeroDivisionError("Division by zero in formula")
            res = SAFE_BIN_OPS[op_type](left, right)
            return Decimal(str(res))
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in SAFE_UNARY_OPS:
                raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
            operand = _eval_node(node.operand)
            res = SAFE_UNARY_OPS[op_type](operand)
            return Decimal(str(res))
        else:
            raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    try:
        parsed = ast.parse(expr.strip(), mode="eval")
        result = _eval_node(parsed)
        return Decimal(str(result))
    except Exception:
        return Decimal("0.00")


def extract_formula_dependencies(expr: str) -> set[str]:
    """
    Safely extract variable names (identifiers) referenced in a mathematical expression.
    """
    if not expr or not isinstance(expr, str):
        return set()
    try:
        parsed = ast.parse(expr.strip(), mode="eval")
        return {
            node.id.strip().lower()
            for node in ast.walk(parsed)
            if isinstance(node, ast.Name)
        }
    except Exception:
        return {
            tok.lower() for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(expr))
        }


def topological_sort_components(comps: list) -> list:
    """
    Topologically sorts components so that dependencies are evaluated first.
    If Component B references Component A in its formula or uses Component A as calc_base,
    Component A will precede Component B in the returned list.
    Preserves original relative order when there are no dependencies.
    Gracefully handles dependency cycles without hanging.
    """
    if not comps or len(comps) <= 1:
        return list(comps)

    def _get_name(c):
        return getattr(c, "name", None) or getattr(getattr(c, "component", None), "name", "")

    def _get_calc_type(c):
        return (getattr(c, "calc_type", None) or getattr(c, "calculation_type", "") or "").strip().lower()

    def _get_formula(c):
        return (
            getattr(c, "formula", None)
            or getattr(getattr(c, "component", None), "formula", None)
            or getattr(c, "calc_base", None)
            or getattr(getattr(c, "component", None), "calc_base", None)
            or (str(c.value) if _get_calc_type(c) == "formula" and getattr(c, "value", None) else "")
        )

    def _get_calc_base(c):
        return getattr(c, "calc_base", None) or getattr(getattr(c, "component", None), "calc_base", None)

    # Map name variants to component
    comp_map: dict[str, Any] = {}
    for comp in comps:
        name = _get_name(comp)
        if name:
            clean = name.strip().lower()
            comp_map[clean] = comp
            comp_map[clean.replace(" ", "_").replace("-", "_")] = comp
            comp_map[clean.replace(" ", "").replace("-", "")] = comp
        cid = getattr(comp, "id", None) or getattr(getattr(comp, "component", None), "id", None)
        if cid is not None:
            comp_map[str(cid)] = comp

    # Build dependency map: comp -> set of comps it depends on
    deps: dict[int, set[int]] = {id(comp): set() for comp in comps}
    for comp in comps:
        comp_id = id(comp)
        formula_str = _get_formula(comp)
        if formula_str:
            referenced_names = extract_formula_dependencies(str(formula_str))
            for ref_name in referenced_names:
                dep_comp = comp_map.get(ref_name)
                if dep_comp and id(dep_comp) != comp_id:
                    deps[comp_id].add(id(dep_comp))

        calc_base = _get_calc_base(comp)
        if calc_base:
            cb_str = str(calc_base).strip().lower()
            dep_comp = (
                comp_map.get(cb_str)
                or comp_map.get(cb_str.replace(" ", "_").replace("-", "_"))
                or comp_map.get(cb_str.replace(" ", "").replace("-", ""))
            )
            if dep_comp and id(dep_comp) != comp_id:
                deps[comp_id].add(id(dep_comp))

    # Reverse graph for in-degrees
    in_degree: dict[int, int] = {id(comp): 0 for comp in comps}
    dependents: dict[int, list[int]] = {id(comp): [] for comp in comps}

    for comp_id, needed_ids in deps.items():
        for needed_id in needed_ids:
            if needed_id in in_degree:
                dependents[needed_id].append(comp_id)
                in_degree[comp_id] += 1

    id_to_comp = {id(comp): comp for comp in comps}
    queue = [id(comp) for comp in comps if in_degree[id(comp)] == 0]
    sorted_comps = []

    while queue:
        curr_id = queue.pop(0)
        sorted_comps.append(id_to_comp[curr_id])
        for dep_id in dependents[curr_id]:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                queue.append(dep_id)

    # In case of cycles, append any remaining components in original order
    visited = {id(c) for c in sorted_comps}
    for comp in comps:
        if id(comp) not in visited:
            sorted_comps.append(comp)

    return sorted_comps


def calculate_total_worked_hours(staff, effective_start, effective_end) -> Decimal:
    """
    Calculates total valid worked hours for the staff in the given date range.
    Sums Attendance.working_hours for present attendance records.
    Returns Decimal rounded to 2 decimal places.
    """
    if not effective_start or not effective_end:
        return Decimal("0.00")

    attendance_records = Attendance.objects.filter(
        staff=staff,
        attendance_date__range=(effective_start, effective_end),
        is_present=True,
    )
    total_hours = Decimal("0.00")
    for att in attendance_records:
        if att.working_hours:
            try:
                total_hours += Decimal(str(att.working_hours))
            except Exception:
                pass
    return total_hours.quantize(Decimal("0.01"))


class MissingPunchError(Exception):
    """Raised when calculation for a staff member is aborted due to missing check-out punches."""

    def __init__(self, staff, dates):
        self.staff = staff
        self.dates = dates
        dates_str = ", ".join(d.strftime("%Y-%m-%d") for d in dates)
        super().__init__(
            f"Staff {staff.name} requires regularization due to missing punch on: {dates_str}"
        )


def get_month_date_range(month, year):
    """
    Returns (month_start, month_end, total_working_days) without hardcoded 30/31 days.
    """
    total_days = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, total_days)
    return month_start, month_end, total_days


def calculate_eligible_dates(staff, month, year):
    """
    Priority 1 (Joining/Exit):
    Calculate the eligible_working_days based on the month and staff's joining_date and exit_date.
    If they joined mid-month, they are only eligible for those specific days.
    """
    month_start, month_end, total_days_in_month = get_month_date_range(month, year)

    # Check joining date
    if staff.joining_date:
        if staff.joining_date > month_end:
            # Joined in a future month
            return 0, None, None, total_days_in_month
        effective_start = max(month_start, staff.joining_date)
    else:
        effective_start = month_start

    # Check exit date
    if staff.exit_date:
        if staff.exit_date < month_start:
            # Exited in a past month
            return 0, None, None, total_days_in_month
        effective_end = min(month_end, staff.exit_date)
    else:
        effective_end = month_end

    if effective_start > effective_end:
        return 0, None, None, total_days_in_month

    eligible_days = (effective_end - effective_start).days + 1
    return eligible_days, effective_start, effective_end, total_days_in_month


def check_missing_punches(staff, effective_start, effective_end):
    """
    Priority 2 (Missing Punch):
    Check if the staff has any is_missing_punch (Check-In without Check-Out) for the month.
    Excludes punches that have already been regularized and approved.
    """
    if not effective_start or not effective_end:
        return []

    attendance_records = Attendance.objects.filter(
        staff=staff,
        attendance_date__range=(effective_start, effective_end),
        check_in__isnull=False,
        check_out__isnull=True,
    )

    missing_dates = []
    for att in attendance_records:
        has_approved_reg = AttendanceRegularization.objects.filter(
            staff=staff,
            attendance_date=att.attendance_date,
            status="Approved",
        ).exists()

        if not has_approved_reg:
            missing_dates.append(att.attendance_date)

    return sorted(missing_dates)


def calculate_leaves(staff, effective_start, effective_end):
    """
    Priority 3 (Leaves):
    Sum Approved Paid Leaves and Approved Unpaid Leaves (LOP).
    """
    if not effective_start or not effective_end:
        return Decimal("0.0"), Decimal("0.0")

    approved_leave_days = LeavePerDay.objects.filter(
        leave__staff=staff,
        status="APPROVED",
        date__range=(effective_start, effective_end),
    ).select_related("leave")

    paid_leaves = Decimal("0.0")
    unpaid_leaves = Decimal("0.0")

    for ld in approved_leave_days:
        if getattr(ld, "day_weight", None) is not None:
            day_weight = Decimal(str(ld.day_weight))
        elif (
            ld.leave is not None
            and hasattr(ld.leave, "total_days")
            and ld.leave.total_days == Decimal("0.5")
        ):
            day_weight = Decimal("0.5")
        else:
            day_weight = Decimal("1.0")

        if ld.leave and ld.leave.is_paid:
            paid_leaves += day_weight
        else:
            unpaid_leaves += day_weight

    return paid_leaves, unpaid_leaves


def calculate_attendance_days(staff, effective_start, effective_end):
    """
    Priority 4 (Attendance):
    Sum Present, Late, and Half-Days.
    Returns: (present_days, half_days, late_days)
    """
    if not effective_start or not effective_end:
        return Decimal("0.0"), Decimal("0.0"), 0

    attendance_records = Attendance.objects.filter(
        staff=staff, attendance_date__range=(effective_start, effective_end)
    )

    present_count = Decimal("0.0")
    half_day_count = Decimal("0.0")
    late_count = 0

    for att in attendance_records:
        if att.is_present:
            if att.is_half_day:
                half_day_count += Decimal("1.0")
            else:
                present_count += Decimal("1.0")
        if att.is_late:
            late_count += 1

    return present_count, half_day_count, late_count


def generate_payslip(
    staff,
    month,
    year,
    payroll_run=None,
    payment_data=None,
    raise_on_missing_punch=True,
):
    """
    Core calculation function: generate_payslip(staff, month, year)
    Strictly follows Attendance -> Leave -> Payroll Priority:
      Priority 1: Joining/Exit pro-rata eligible working days
      Priority 2: Missing Punch detection (aborts/flags if unregularized)
      Priority 3: Sum Approved Paid Leaves and Approved Unpaid Leaves (LOP)
      Priority 4: Sum Present, Late, and Half-Days
      Payable Days = Present + Paid Leaves + (Half-Days * 0.5)
      ProRataMultiplier = Payable Days / Total Working Days
      Component Math: Fixed * Multiplier, Percentage against calc_base
      Enforces Payroll Lock constraint
    """
    if isinstance(staff, (int, str)):
        staff = Staff.objects.select_related("school", "salary_structure").get(id=int(staff))

    month = int(month)
    year = int(year)
    month_start, month_end, total_days_in_month = get_month_date_range(month, year)

    # 0. Check Payroll Lock
    if payroll_run is None:
        payroll_run = PayrollRun.objects.filter(
            school=staff.school, salary_month=month_start
        ).first()

    if payroll_run and payroll_run.status == "Locked":
        raise ValidationError(
            f"Payroll run for {month_start.strftime('%B %Y')} is Locked. Recalculation is blocked."
        )

    # 1. Priority 1 (Joining/Exit)
    eligible_working_days, effective_start, effective_end, total_working_days = (
        calculate_eligible_dates(staff, month, year)
    )

    if eligible_working_days <= 0 or not effective_start or not effective_end:
        return {
            "status": "skipped",
            "flag": "Not Eligible",
            "reason": f"Staff was not active during {month:02d}-{year} (joining/exit bounds).",
            "staff_id": staff.id,
            "staff_name": staff.name,
        }

    # 2. Priority 2 (Missing Punch)
    missing_dates = check_missing_punches(staff, effective_start, effective_end)
    if missing_dates:
        if raise_on_missing_punch:
            raise MissingPunchError(staff, missing_dates)
        return {
            "status": "skipped",
            "flag": "Requires Regularization",
            "reason": f"Missing check-out punch on {', '.join(d.strftime('%Y-%m-%d') for d in missing_dates)}",
            "missing_punch_dates": [d.strftime("%Y-%m-%d") for d in missing_dates],
            "staff_id": staff.id,
            "staff_name": staff.name,
        }

    # 3. Priority 3 (Leaves)
    paid_leaves, unpaid_leaves = calculate_leaves(staff, effective_start, effective_end)

    # 4. Priority 4 (Attendance)
    full_day_present, half_days, late_count = calculate_attendance_days(
        staff, effective_start, effective_end
    )
    total_worked_hours = calculate_total_worked_hours(
        staff, effective_start, effective_end
    )

    # Calculate Payable Days = Present + Paid Leaves + (Half-Days * 0.5)
    raw_payable = full_day_present + paid_leaves + (half_days * Decimal("0.5"))
    payable_days = min(raw_payable, Decimal(eligible_working_days))

    # Calculate ProRataMultiplier = Payable Days / Total Working Days
    total_working_days_dec = Decimal(total_working_days)
    if total_working_days_dec > Decimal("0.0"):
        pro_rata_multiplier = (payable_days / total_working_days_dec).quantize(
            Decimal("0.0001")
        )
    else:
        pro_rata_multiplier = Decimal("0.0000")

    # 5. Salary Component Math
    earnings_list: list[dict[str, Any]] = []
    deductions_list: list[dict[str, Any]] = []
    calculated_map = {}

    # Identify base salary
    base_salary_val = staff.salary or Decimal("0.00")

    # Retrieve components from staff.salary_structure
    components = []
    if staff.salary_structure:
        components = list(
            staff.salary_structure.components.filter(is_active=True).order_by("id")
        )

    # Two-pass calculation:
    # Pass 1: Fixed components
    has_fixed_basic = False
    for comp in components:
        c_type = comp.type.capitalize()
        c_calc = comp.calc_type.capitalize()
        val = Decimal(str(comp.value or 0))

        if c_calc == "Fixed":
            amount = (val * pro_rata_multiplier).quantize(Decimal("0.01"))
            norm_name = comp.name.strip().lower()
            calculated_map[norm_name] = amount
            if "basic" in norm_name:
                has_fixed_basic = True
                calculated_map["basic"] = amount
                calculated_map["basic salary"] = amount

            item = {
                "component_id": comp.id,
                "name": comp.name,
                "type": c_type,
                "calc_type": "Fixed",
                "calc_base": None,
                "value": str(val),
                "amount": str(Decimal(str(amount))),
            }
            if c_type == "Earning":
                earnings_list.append(item)
            else:
                deductions_list.append(item)

    # If no Fixed component represents basic salary, use staff.salary
    if not has_fixed_basic and base_salary_val > Decimal("0.00"):
        basic_amount = (base_salary_val * pro_rata_multiplier).quantize(Decimal("0.01"))
        calculated_map["basic"] = basic_amount
        calculated_map["basic salary"] = basic_amount
        earnings_list.insert(
            0,
            {
                "component_id": None,
                "name": "Basic Salary",
                "type": "Earning",
                "calc_type": "Fixed",
                "calc_base": None,
                "value": str(base_salary_val),
                "amount": str(Decimal(str(basic_amount))),
            },
        )

    # Pass 2:
    # 2a. Percentage, Per Day, and Per Hour components
    non_formula_components = [
        comp
        for comp in components
        if (comp.calc_type or "").strip().lower() != "formula"
        and (comp.calc_type or "").strip().capitalize() != "Fixed"
    ]
    for comp in non_formula_components:
        c_type = comp.type.capitalize() if comp.type else "Earning"
        c_calc_raw = (comp.calc_type or "").strip()
        c_calc_lower = c_calc_raw.lower()
        val = Decimal(str(comp.value or 0))

        if c_calc_lower == "percentage":
            calc_base_str = (comp.calc_base or "basic").strip().lower()
            base_amount = calculated_map.get(calc_base_str)
            if base_amount is None:
                base_amount = (
                    calculated_map.get("basic salary")
                    or calculated_map.get("basic")
                    or (base_salary_val * pro_rata_multiplier)
                )

            amount = (
                Decimal(str(base_amount)) * (val / Decimal("100.0"))
            ).quantize(Decimal("0.01"))
            calculated_map[comp.name.strip().lower()] = amount

            item = {
                "component_id": comp.id,
                "name": comp.name,
                "type": c_type,
                "calc_type": "Percentage",
                "calc_base": comp.calc_base or "Basic Salary",
                "value": str(val),
                "amount": str(Decimal(str(amount))),
            }
            if c_type == "Earning":
                earnings_list.append(item)
            else:
                deductions_list.append(item)

        elif c_calc_lower in ["per day", "per_day", "perday"]:
            # Per Day: Multiply rate by payable_days
            amount = (val * Decimal(str(payable_days))).quantize(Decimal("0.01"))
            calculated_map[comp.name.strip().lower()] = amount

            item = {
                "component_id": comp.id,
                "name": comp.name,
                "type": c_type,
                "calc_type": "Per Day",
                "calc_base": f"{payable_days} payable days",
                "value": str(val),
                "amount": str(Decimal(str(amount))),
            }
            if c_type == "Earning":
                earnings_list.append(item)
            else:
                deductions_list.append(item)

        elif c_calc_lower in ["per hour", "per_hour", "perhour"]:
            # Per Hour: Multiply rate by total valid worked hours for the month
            amount = (val * Decimal(str(total_worked_hours))).quantize(Decimal("0.01"))
            calculated_map[comp.name.strip().lower()] = amount

            item = {
                "component_id": comp.id,
                "name": comp.name,
                "type": c_type,
                "calc_type": "Per Hour",
                "calc_base": f"{total_worked_hours} worked hours",
                "value": str(val),
                "amount": str(Decimal(str(amount))),
            }
            if c_type == "Earning":
                earnings_list.append(item)
            else:
                deductions_list.append(item)

    # 2b. Formula components: Topologically sorted so dependencies evaluate first
    formula_components = [
        comp
        for comp in components
        if (comp.calc_type or "").strip().lower() == "formula"
    ]
    sorted_formula_components = topological_sort_components(formula_components)
    for comp in sorted_formula_components:
        c_type = comp.type.capitalize() if comp.type else "Earning"
        val = Decimal(str(comp.value or 0))

        # Formula: Safe evaluation using ast
        formula_str = (
            getattr(comp, "formula", None)
            or comp.calc_base
            or (str(comp.value) if comp.value else "")
        )
        # Build variables dictionary mapping known values to their calculated base amounts
        formula_vars: dict[str, Any] = {}
        for k, v in calculated_map.items():
            formula_vars[k] = v
            clean_k = str(k).replace(" ", "_").replace("-", "_")
            formula_vars[clean_k] = v

        basic_val = (
            calculated_map.get("basic")
            or calculated_map.get("basic salary")
            or (base_salary_val * pro_rata_multiplier)
        )
        formula_vars["basic"] = basic_val
        formula_vars["basicsalary"] = basic_val
        formula_vars["basic_salary"] = basic_val
        formula_vars["base_salary"] = base_salary_val
        formula_vars["payable_days"] = payable_days
        formula_vars["working_days"] = Decimal(eligible_working_days)
        formula_vars["total_working_days"] = total_working_days_dec
        formula_vars["pro_rata_multiplier"] = pro_rata_multiplier
        formula_vars["worked_hours"] = total_worked_hours

        raw_evaluated = safe_eval(formula_str, formula_vars)
        amount = Decimal(str(raw_evaluated)).quantize(Decimal("0.01"))
        calculated_map[comp.name.strip().lower()] = amount

        item = {
            "component_id": comp.id,
            "name": comp.name,
            "type": c_type,
            "calc_type": "Formula",
            "calc_base": formula_str or "Formula",
            "value": str(val),
            "amount": str(Decimal(str(amount))),
        }
        if c_type == "Earning":
            earnings_list.append(item)
        else:
            deductions_list.append(item)

    # Fallback to StaffSalaryComponent if structure had no components
    if not components:
        staff_comps = list(
            StaffSalaryComponent.objects.filter(
                staff=staff, is_active=True, component__is_active=True
            ).select_related("component")
        )

        non_formula_sc = [
            sc
            for sc in staff_comps
            if (sc.calculation_type or "").strip().lower() != "formula"
        ]
        formula_sc = [
            sc
            for sc in staff_comps
            if (sc.calculation_type or "").strip().lower() == "formula"
        ]
        sorted_formula_sc = topological_sort_components(formula_sc)

        for sc in non_formula_sc + sorted_formula_sc:
            c = sc.component
            val = Decimal(str(sc.value or 0))
            calc_type_raw = (sc.calculation_type or "").strip()
            calc_type_lower = calc_type_raw.lower()
            c_type = c.type.capitalize() if c.type else "Earning"

            if calc_type_lower == "percentage":
                base_amount = calculated_map.get("basic") or (
                    base_salary_val * pro_rata_multiplier
                )
                amount = (
                    Decimal(str(base_amount)) * (val / Decimal("100.0"))
                ).quantize(Decimal("0.01"))
            elif calc_type_lower in ["per day", "per_day", "perday"]:
                amount = (val * Decimal(str(payable_days))).quantize(Decimal("0.01"))
            elif calc_type_lower in ["per hour", "per_hour", "perhour"]:
                amount = (val * Decimal(str(total_worked_hours))).quantize(Decimal("0.01"))
            elif calc_type_lower == "formula":
                formula_str = getattr(c, "formula", None) or c.calc_base or str(val)
                formula_vars = {k: v for k, v in calculated_map.items()}
                for k, v in calculated_map.items():
                    clean_k = str(k).replace(" ", "_").replace("-", "_")
                    formula_vars[clean_k] = v
                basic_val = calculated_map.get("basic") or (base_salary_val * pro_rata_multiplier)
                formula_vars["basic"] = basic_val
                formula_vars["basicsalary"] = basic_val
                formula_vars["basic_salary"] = basic_val
                formula_vars["base_salary"] = base_salary_val
                formula_vars["payable_days"] = payable_days
                formula_vars["working_days"] = Decimal(eligible_working_days)
                formula_vars["total_working_days"] = total_working_days_dec
                formula_vars["pro_rata_multiplier"] = pro_rata_multiplier
                formula_vars["worked_hours"] = total_worked_hours
                raw_evaluated = safe_eval(formula_str, formula_vars)
                amount = Decimal(str(raw_evaluated)).quantize(Decimal("0.01"))
                calculated_map[c.name.strip().lower()] = amount
            else:
                amount = (val * pro_rata_multiplier).quantize(Decimal("0.01"))

            item = {
                "component_id": c.id,
                "name": c.name,
                "type": c_type,
                "calc_type": sc.calculation_type,
                "calc_base": "Basic Salary" if calc_type_lower == "percentage" else None,
                "value": str(val),
                "amount": str(Decimal(str(amount))),
            }
            if c_type == "Earning":
                earnings_list.append(item)
            else:
                deductions_list.append(item)

    # Calculate Totals
    gross_earnings = sum(
        (Decimal(e["amount"]) for e in earnings_list), Decimal("0.00")
    ).quantize(Decimal("0.01"))
    total_deductions = sum(
        (Decimal(d["amount"]) for d in deductions_list), Decimal("0.00")
    ).quantize(Decimal("0.01"))
    net_salary = max(Decimal("0.00"), gross_earnings - total_deductions).quantize(
        Decimal("0.01")
    )

    # Calculate LOP (Unpaid Leave) deduction snapshot
    per_day_base = (
        (base_salary_val / total_working_days_dec).quantize(Decimal("0.01"))
        if total_working_days_dec > Decimal("0")
        else Decimal("0.00")
    )
    lop_amount = (unpaid_leaves * per_day_base).quantize(Decimal("0.01"))

    # Construct Component Breakdown JSON
    component_breakdown = {
        "working_days": total_working_days,
        "eligible_working_days": eligible_working_days,
        "effective_start": effective_start.strftime("%Y-%m-%d"),
        "effective_end": effective_end.strftime("%Y-%m-%d"),
        "present_days": float(full_day_present),
        "late_days": late_count,
        "half_days": float(half_days),
        "paid_leaves": float(paid_leaves),
        "unpaid_leaves": float(unpaid_leaves),
        "lop_deduction_amount": str(lop_amount),
        "payable_days": float(payable_days),
        "pro_rata_multiplier": str(pro_rata_multiplier),
        "earnings": earnings_list,
        "deductions": deductions_list,
        "gross_earnings": str(gross_earnings),
        "total_deductions": str(total_deductions),
        "net_salary": str(net_salary),
        "calculated_at": timezone.now().isoformat(),
    }

    # 6. Database Persistence
    with transaction.atomic():
        if payroll_run is None:
            payroll_run, _ = PayrollRun.objects.get_or_create(
                school=staff.school,
                salary_month=month_start,
                defaults={"status": "Draft"},
            )

        payslip, _ = PayrollPayslip.objects.update_or_create(
            staff=staff,
            payroll_run=payroll_run,
            defaults={
                "present_days": full_day_present + (half_days * Decimal("0.5")),
                "paid_leaves": paid_leaves,
                "unpaid_leaves": unpaid_leaves,
                "gross_earnings": gross_earnings,
                "total_deductions": total_deductions,
                "net_salary": net_salary,
                "component_breakdown": component_breakdown,
            },
        )

        # Synchronize StaffSalaryPayment for full system backward compatibility
        salary_month_str = f"{year}-{month:02d}"
        payment_mode = (
            payment_data.get("payment_mode", "offline")
            if payment_data
            else "offline"
        )
        transaction_id = (
            payment_data.get("transaction_id", None) if payment_data else None
        )
        note = payment_data.get("note", "") if payment_data else ""
        receipt_num = f"SAL-{salary_month_str}-{staff.id}"

        # Build legacy snapshot
        legacy_snapshot = [
            {
                "component_id": e.get("component_id") or 0,
                "name": e["name"],
                "component_type": "earning",
                "calculation_type": e.get("calc_type", "Fixed").lower(),
                "value": e.get("value", "0.00"),
                "amount": e["amount"],
            }
            for e in earnings_list
        ] + [
            {
                "component_id": d.get("component_id") or 0,
                "name": d["name"],
                "component_type": "deduction",
                "calculation_type": d.get("calc_type", "Fixed").lower(),
                "value": d.get("value", "0.00"),
                "amount": d["amount"],
            }
            for d in deductions_list
        ]

        absent_days_count = max(0, total_working_days - int(payable_days))
        StaffSalaryPayment.objects.update_or_create(
            school=staff.school,
            staff=staff,
            salary_month=salary_month_str,
            defaults={
                "staff_name": staff.name,
                "staff_category": staff.category,
                "basic_salary": base_salary_val,
                "total_earnings": gross_earnings,
                "total_deductions": total_deductions,
                "working_days": total_working_days,
                "present_days": payable_days,
                "absent_days": absent_days_count,
                "half_days": int(half_days),
                "attendance_deduction": lop_amount,
                "component_snapshot": legacy_snapshot,
                "net_salary": net_salary,
                "paid_amount": net_salary,
                "payment_mode": payment_mode,
                "payment_status": "paid",
                "transaction_id": transaction_id,
                "note": note,
                "receipt_number": receipt_num,
            },
        )

    return {
        "status": "success",
        "payslip": payslip,
        "staff_id": staff.id,
        "staff_name": staff.name,
        "payable_days": float(payable_days),
        "net_salary": str(net_salary),
        "breakdown": component_breakdown,
    }


def generate_payroll_run(school, month, year, staff_id=None):
    """
    Triggers calculation for an entire school or a single staff member.
    Enforces lock checks, skips staff with Missing Punches, and returns summary.
    """
    month = int(month)
    year = int(year)
    month_start, _, _ = get_month_date_range(month, year)

    # Check lock
    payroll_run, _ = PayrollRun.objects.get_or_create(
        school=school,
        salary_month=month_start,
        defaults={"status": "Draft"},
    )

    if payroll_run.status == "Locked":
        raise ValidationError(
            f"Payroll run for {month_start.strftime('%B %Y')} is Locked. Recalculation is blocked."
        )

    # Determine staff queryset
    staff_qs = Staff.objects.filter(school=school, is_active=True)
    if staff_id:
        staff_qs = staff_qs.filter(id=staff_id)

    processed_list = []
    skipped_list = []

    for staff in staff_qs:
        res = generate_payslip(
            staff=staff,
            month=month,
            year=year,
            payroll_run=payroll_run,
            raise_on_missing_punch=False,
        )

        if res.get("status") == "success":
            processed_list.append(
                {
                    "staff_id": staff.id,
                    "staff_name": staff.name,
                    "payable_days": res["payable_days"],
                    "net_salary": res["net_salary"],
                }
            )
        else:
            skipped_list.append(
                {
                    "staff_id": staff.id,
                    "staff_name": staff.name,
                    "flag": res.get("flag", "Skipped"),
                    "reason": res.get("reason", "Unknown reason"),
                    "missing_punch_dates": res.get("missing_punch_dates", []),
                }
            )

    # Update payroll run counts
    payroll_run.total_processed = len(processed_list)
    payroll_run.generated_at = timezone.now()
    if payroll_run.status == "Draft":
        payroll_run.status = "Generated"
    payroll_run.save(update_fields=["total_processed", "generated_at", "status", "updated_at"])

    return {
        "payroll_run_id": payroll_run.id,
        "salary_month": f"{year}-{month:02d}",
        "status": payroll_run.status,
        "total_eligible_staff": staff_qs.count(),
        "total_processed": len(processed_list),
        "total_skipped": len(skipped_list),
        "processed": processed_list,
        "skipped": skipped_list,
    }
