from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
import io
import csv
from sqlalchemy.orm import Session
from app.models import User, AttendanceLog, Department


class PayrollService:
    @classmethod
    def compute_payroll(
        cls,
        db: Session,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        department_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculate role-based payroll, tracked work hours, overtime, and deductions
        for all active users within the specified date range.
        """
        today = date.today()
        if not start_date:
            # Default to 1st of current month
            s_date = date(today.year, today.month, 1)
        else:
            try:
                s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                s_date = date(today.year, today.month, 1)

        if not end_date:
            e_date = today
        else:
            try:
                e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                e_date = today

        s_dt = datetime.combine(s_date, time.min)
        e_dt = datetime.combine(e_date, time.max)

        # Query users
        u_query = db.query(User).filter(User.is_active == True)
        if department_id:
            u_query = u_query.filter(User.department_id == department_id)
        users = u_query.order_by(User.full_name.asc()).all()

        records = []
        total_payout = 0.0
        total_hours = 0.0
        total_overtime = 0.0
        total_days_worked = 0

        for user in users:
            logs = (
                db.query(AttendanceLog)
                .filter(
                    AttendanceLog.user_id == user.id,
                    AttendanceLog.timestamp >= s_dt,
                    AttendanceLog.timestamp <= e_dt,
                )
                .order_by(AttendanceLog.timestamp.asc())
                .all()
            )

            # Group logs by day
            days_map: Dict[date, List[AttendanceLog]] = {}
            for log in logs:
                d = log.timestamp.date()
                if d not in days_map:
                    days_map[d] = []
                days_map[d].append(log)

            days_count = len(days_map)
            user_reg_hours = 0.0
            user_ot_hours = 0.0
            late_days_count = 0

            for d, day_logs in days_map.items():
                in_punches = [l for l in day_logs if l.punch_type == "IN"]
                out_punches = [l for l in day_logs if l.punch_type == "OUT"]

                # Check if marked late on this day
                if any(l.status == "LATE" for l in day_logs):
                    late_days_count += 1

                if in_punches and out_punches:
                    first_in = in_punches[0].timestamp
                    last_out = out_punches[-1].timestamp
                    if last_out > first_in:
                        day_hrs = (last_out - first_in).total_seconds() / 3600.0
                    else:
                        day_hrs = 8.0
                elif in_punches:
                    # Single punch in - allocate standard 8-hour shift
                    day_hrs = 8.0
                else:
                    day_hrs = 4.0

                # Cap max reasonable daily hours to 16
                day_hrs = min(16.0, round(day_hrs, 2))

                if day_hrs > 8.0:
                    user_reg_hours += 8.0
                    user_ot_hours += (day_hrs - 8.0)
                else:
                    user_reg_hours += day_hrs

            user_total_hours = round(user_reg_hours + user_ot_hours, 1)
            hourly_rate = float(user.hourly_rate or 25.0)

            base_pay = round(user_reg_hours * hourly_rate, 2)
            ot_pay = round(user_ot_hours * hourly_rate * 1.5, 2)
            # Penalty: 0.5 hour wage per late mark
            late_deduction = round(late_days_count * (hourly_rate * 0.5), 2)
            net_pay = max(0.0, round(base_pay + ot_pay - late_deduction, 2))

            total_payout += net_pay
            total_hours += user_total_hours
            total_overtime += user_ot_hours
            total_days_worked += days_count

            dept_name = user.department.name if user.department else "General"
            designation = user.designation if hasattr(user, "designation") and user.designation else "Staff"

            records.append({
                "user_id": user.id,
                "user_code": user.user_code,
                "full_name": user.full_name,
                "role": user.role,
                "designation": designation,
                "department": dept_name,
                "hourly_rate": hourly_rate,
                "days_worked": days_count,
                "regular_hours": round(user_reg_hours, 1),
                "overtime_hours": round(user_ot_hours, 1),
                "total_hours": user_total_hours,
                "late_marks": late_days_count,
                "base_pay": base_pay,
                "overtime_pay": ot_pay,
                "deductions": late_deduction,
                "net_pay": net_pay,
                "status": "APPROVED" if days_count > 0 else "NO_LOGS",
            })

        return {
            "period": {
                "start_date": s_date.strftime("%Y-%m-%d"),
                "end_date": e_date.strftime("%Y-%m-%d"),
                "label": f"{s_date.strftime('%d %b %Y')} – {e_date.strftime('%d %b %Y')}",
            },
            "summary": {
                "total_employees": len(users),
                "total_payout": round(total_payout, 2),
                "total_hours": round(total_hours, 1),
                "total_overtime": round(total_overtime, 1),
                "total_days_worked": total_days_worked,
                "average_payout": round(total_payout / len(users), 2) if users else 0.0,
            },
            "records": records,
        }

    @classmethod
    def export_payroll_csv(cls, payroll_data: Dict[str, Any]) -> io.BytesIO:
        """Export computed payroll data to CSV stream."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header info
        writer.writerow(["FRAS ENTERPRISE — PAYROLL & COMPENSATION REPORT"])
        writer.writerow(["Pay Period:", payroll_data["period"]["label"]])
        writer.writerow(["Total Employees:", payroll_data["summary"]["total_employees"]])
        writer.writerow(["Total Gross Payout:", f"${payroll_data['summary']['total_payout']:,.2f}"])
        writer.writerow([])

        # Table columns
        writer.writerow([
            "Employee Code",
            "Full Name",
            "Designation",
            "Department",
            "Role",
            "Rate ($/hr)",
            "Days Worked",
            "Regular Hours",
            "Overtime Hours",
            "Total Hours",
            "Late Marks",
            "Base Pay ($)",
            "Overtime Pay ($)",
            "Deductions ($)",
            "Net Payout ($)",
            "Status",
        ])

        for r in payroll_data["records"]:
            writer.writerow([
                r["user_code"],
                r["full_name"],
                r["designation"],
                r["department"],
                r["role"],
                f"${r['hourly_rate']:.2f}",
                r["days_worked"],
                r["regular_hours"],
                r["overtime_hours"],
                r["total_hours"],
                r["late_marks"],
                f"${r['base_pay']:.2f}",
                f"${r['overtime_pay']:.2f}",
                f"${r['deductions']:.2f}",
                f"${r['net_pay']:.2f}",
                r["status"],
            ])

        stream = io.BytesIO(output.getvalue().encode("utf-8"))
        stream.seek(0)
        return stream
