import frappe
from frappe import _
from frappe.utils import date_diff


def validate_employee_attendance(self):
	employees_to_mark_attendance = []
	days_in_payroll, days_holiday, days_attendance_marked = 0, 0, 0

	for employee_detail in self.employees:
		days_holiday = self.get_count_holidays_of_employee(employee_detail.employee)
		days_attendance_marked, days_scheduled = self.get_count_employee_attendance(employee_detail.employee)

		days_in_payroll = date_diff(self.end_date, self.start_date) + 1
		if days_in_payroll != (days_holiday + days_attendance_marked) != (days_holiday + days_scheduled) :
			employees_to_mark_attendance.append({
				"employee": employee_detail.employee,
				"employee_name": employee_detail.employee_name
				})
	return employees_to_mark_attendance

def get_count_holidays_of_employee(self, employee):
	holidays = 0
	days = frappe.db.sql("""select count(*) from `tabEmployee Schedule` where
		employee=%s and date between %s and %s and employee_availability in ("Day Off", "Sick Leave", "Annual Leave", "Emergency Leave") """, (employee,
		self.start_date, self.end_date))
	if days and days[0][0]:
		holidays = days[0][0]
	return holidays

def get_count_employee_attendance(self, employee):
	scheduled_days = 0
	marked_days = 0
	roster = frappe.db.sql("""select count(*) from `tabEmployee Schedule` where
		employee=%s and date between %s and %s and employee_availability="Working" """,
		(employee, self.start_date, self.end_date))
	if roster and roster[0][0]:
		scheduled_days = roster[0][0]
	attendances = frappe.db.sql("""select count(*) from tabAttendance where
		employee=%s and docstatus=1 and attendance_date between %s and %s""",
		(employee, self.start_date, self.end_date))
	if attendances and attendances[0][0]:
		marked_days = attendances[0][0]
	return marked_days, scheduled_days

@frappe.whitelist()
def fill_employee_details(self):
	"""
	This Function fetches the employee details and updates the 'Employee Details' child table.

	Returns:
		list of active employees based on selected criteria
		and for which salary structure exists.
	"""
	self.set('employees', [])
	employees = self.get_emp_list()

	#Fetch Bank Details and update employee list
	set_bank_details(self, employees)

	if not employees:
		error_msg = _("No employees found for the mentioned criteria:<br>Company: {0}<br> Currency: {1}<br>Payroll Payable Account: {2}").format(
			frappe.bold(self.company), frappe.bold(self.currency), frappe.bold(self.payroll_payable_account))
		if self.branch:
			error_msg += "<br>" + _("Branch: {0}").format(frappe.bold(self.branch))
		if self.department:
			error_msg += "<br>" + _("Department: {0}").format(frappe.bold(self.department))
		if self.designation:
			error_msg += "<br>" + _("Designation: {0}").format(frappe.bold(self.designation))
		if self.start_date:
			error_msg += "<br>" + _("Start date: {0}").format(frappe.bold(self.start_date))
		if self.end_date:
			error_msg += "<br>" + _("End date: {0}").format(frappe.bold(self.end_date))
		frappe.throw(error_msg, title=_("No employees found"))

	for d in employees:
		self.append('employees', d)

	self.number_of_employees = len(self.employees)
	if self.validate_attendance:
		return self.validate_employee_attendance()

@frappe.whitelist()
def set_bank_details(self, employee_details):
	"""This Funtion Sets the bank Details of an employee. The data is fetched from Bank Account Doctype.

	Args:
		employee_details (dict): Employee Details Child Table.

	Returns:
		employee_details ([dict): Sets the bank account IBAN code and Bank Code.
	"""
	employee_missing_detail = []
	for employee in employee_details:
		try:
			bank_account = frappe.db.get_value("Bank Account",{"party":employee.employee},["iban","bank", "bank_account_no"])
			salary_mode = frappe.db.get_value("Employee", {'name': employee.employee}, ["salary_mode"])
			if bank_account:
				iban, bank, bank_account_no = bank_account
			else:
				iban, bank, bank_account_no = None, None, None

			if not salary_mode:
				employee_missing_detail.append(frappe._dict(
				{'employee':employee, 'salary_mode':'', 'issue':'No salary mode'}))
			elif(salary_mode=='Bank' and bank is None):
				employee_missing_detail.append(frappe._dict(
					{'employee':employee, 'salary_mode':salary_mode, 'issue':'No bank account'}))
			elif(salary_mode=="Bank" and bank_account_no is None):
				employee_missing_detail.append(frappe._dict(
					{'employee':employee, 'salary_mode':salary_mode, 'issue':'No account no.'}))
			employee.salary_mode = salary_mode
			employee.iban_number = iban or bank_account_no
			bank_code = frappe.db.get_value("Bank", {'name': bank}, ["bank_code"])
			employee.bank_code = bank_code
		except Exception as e:
			frappe.log_error(str(e), 'Payroll Entry')
			frappe.throw(str(e))

	# check for missing details, log and report
	if(len(employee_missing_detail)):
		missing_detail = [
			{
				'employee':i.employee.employee,
				'salary_mode':i.salary_mode,
				'issue': i.issue
			}
			for i in employee_missing_detail]

		if(frappe.db.exists({
			'doctype':"Missing Payroll Information",
			'payroll_entry': self.name
			})):
			fetch_mpi = frappe.db.sql(f"""
				SELECT name FROM `tabMissing Payroll Information`
				WHERE payroll_entry="{self.name}"
				ORDER BY modified DESC
				LIMIT 1
			;""", as_dict=1)
			mpi = frappe.get_doc('Missing Payroll Information', fetch_mpi[0].name)
			# delete previous table data
			frappe.db.sql(f"""
				DELETE FROM `tabMissing Payroll Information Detail`
				WHERE parent="{mpi.name}"
			;""")
			mpi.reload()
			for i in missing_detail:
				mpi.append('missing_payroll_information_detail', i)
			mpi.save(ignore_permissions=True)
			frappe.db.commit()
		else:
			mpi = frappe.get_doc({
				'doctype':"Missing Payroll Information",
				'payroll_entry': self.name,
				'missing_payroll_information_detail':missing_detail
			}).insert(ignore_permissions=True)
			frappe.db.commit()

		# generate html template to show to user screen
		message = frappe.render_template(
			'one_fm/api/doc_methods/templates/payroll/bank_issue.html',
			context={'employees':employee_missing_detail, 'mpi':mpi}
		)
		frappe.throw(_(message))
	return employee_details