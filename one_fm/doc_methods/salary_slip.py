import frappe
from frappe import _
from frappe.utils import cstr
from frappe.utils import cint, flt, date_diff, cstr


def get_holidays_for_employee(self, start_date, end_date):
	holidays = frappe.db.sql_list("""
	select distinct date from `tabEmployee Schedule` 
	where
		employee=%s and 
		date between %s and %s 
		and employee_availability in ("Day Off", "Sick Leave", "Annual Leave", "Emergency Leave") """,
	(self.employee, self.start_date, self.end_date))

	holidays = [cstr(i) for i in holidays]

	return holidays

def get_leave_details(self, joining_date=None, relieving_date=None, lwp=None, for_preview=0):
	if not joining_date:
		joining_date, relieving_date = frappe.get_cached_value("Employee", self.employee,
			["date_of_joining", "relieving_date"])

	working_days = date_diff(self.end_date, self.start_date) + 1
	if for_preview:
		self.total_working_days = working_days
		self.payment_days = working_days
		return

	holidays = self.get_holidays_for_employee(self.start_date, self.end_date)
	actual_lwp = self.calculate_lwp(holidays, working_days)
	if not cint(frappe.db.get_value("HR Settings", None, "include_holidays_in_total_working_days")):
		working_days -= len(holidays)
		if working_days < 0:
			frappe.throw(_("There are more holidays than working days this month."))

	if not lwp:
		lwp = actual_lwp
	elif lwp != actual_lwp:
		frappe.msgprint(_("Leave Without Pay does not match with approved Leave Application records"))

	self.total_working_days = working_days
	self.leave_without_pay = lwp
	
	absent_days = frappe.db.sql("""select count(name) as absent from `tabAttendance` where employee=%s and status="Absent" and attendance_date between %s and %s """,
	(self.employee, self.start_date, self.end_date), as_dict=1)
	
	payment_days = flt(self.get_payment_days(joining_date, relieving_date)) - flt(lwp) - flt(absent_days[0].absent if len(absent_days) > 0 else 0)
	self.payment_days = payment_days > 0 and payment_days or 0