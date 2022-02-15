from datetime import datetime, date
import calendar
import frappe
from frappe import _
from erpnext.hr.report.employee_leave_balance.employee_leave_balance import get_data as get_leave_balance
from one_fm.api.v1.utils import response


@frappe.whitelist()
def get_employee_shift(employee_id: str = None, date_type: str = 'month'):
    """
    Fetch employee information relating to
    leave_balance, shift, penalties and attendance
    """
    if not employee_id:
        return response("Bad Request", 400, None, "employee_id required.")

    if not isinstance(employee_id, str):
        return response("Bad Request", 400, None, "employee_id must be of type str.")

    if date_type.lower() not in ["month", "year"]:
        return response("Bad Request", 400, None, "Invalid date_type. Accepted date_type: 'month', 'year'")

    try:
        # prepare dates
        today = datetime.today()
        _start = today.replace(day=1).date()
        _end = today.replace(day = calendar.monthrange(today.year, today.month)[1]).date()
        if(date_type=='year'):
            _start = date(today.year, 1, 31)
            _end = date(today.year, 12, 31)
        
        employee = frappe.get_doc('Employee', employee_id)
        shift_assignment =  frappe.db.get_list('Shift Assignment',
            filters=[
                    ['employee', '=', employee.name],
                ],
                fields=['name', 'employee', 'site', 'shift_type'],
                order_by='modified desc',
                limit=1,
            )
        
        if len(shift_assignment) == 0:
            return response("Resource Not Found", 404, None, "No shift found for {employee}".format(employee=employee.name))
        
        shift_location = frappe.get_doc('Location', shift_assignment[0].site)
        shift_type = frappe.get_doc('Shift Type', shift_assignment[0].shift_type)
        days_worked = frappe.db.get_list('Attendance',
        filters=[
                ['employee', '=', employee.name],
                ['status', '=', 'Present'],
                ['attendance_date', 'BETWEEN', [_start, _end]],
        ],
        fields=['COUNT(*) as count', 'name', 'employee', 'status', 'attendance_date'],
        order_by='modified desc',
        )[0].count
        penalties = frappe.db.sql(f"""
            SELECT COUNT(*) as count, pi.name, pie.employee_id
            FROM `tabPenalty Issuance Employees` pie
            JOIN `tabPenalty Issuance` pi ON pie.parent=pi.name
            WHERE pie.employee_id="{employee.name}" AND pi.docstatus=1
            AND pi.issuing_time BETWEEN "{_start} 00:00:00" AND "{_end} 23:59:59";
        """, as_dict=1)[0].count
        # get leav balance filters
        filters=frappe._dict({'from_date':_start, 'to_date':_end, 'employee':employee.name})
        leave_balance = sum([i.closing_balance for i in get_leave_balance(filters)])
        res = {
            'employee': employee.name,
            'leave_balance':leave_balance,
            'penalties': penalties,
            'days_worked':days_worked,
            'shift_time_from': shift_type.start_time,
            'shift_time_to': shift_type.end_time,
            'shift_location': shift_location.name,
            'shift_latitude_and_longitude': {
                'latitude': shift_location.latitude,
                'longitude': shift_location.longitude,
            }
        }

        return response("Success", 200, res)

    except Exception as error:
       response("Internal Server Error", 500, None, error)