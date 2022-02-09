import frappe
from frappe.permissions import remove_user_permission


def employee_before_validate(doc, method):
	from erpnext.hr.doctype.employee.employee import Employee
	Employee.validate = employee_validate

def employee_validate(self):
	from erpnext.controllers.status_updater import validate_status
	validate_status(self.status, ["Active", "Court Case", "Absconding", "Left"])

	self.employee = self.name
	self.set_employee_name()
	self.validate_date()
	self.validate_email()
	self.validate_status()
	self.validate_reports_to()
	self.validate_preferred_email()
	if self.job_applicant:
		self.validate_onboarding_process()

	if self.user_id:
		self.validate_user_details()
	else:
		existing_user_id = frappe.db.get_value("Employee", self.name, "user_id")
		if existing_user_id:
			remove_user_permission(
				"Employee", self.name, existing_user_id)