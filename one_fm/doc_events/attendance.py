import frappe
from frappe import _
from frappe.utils import cstr, getdate, time_diff_in_hours
from erpnext.hr.utils import get_holidays_for_employee
from one_fm.utils import create_additional_salary


def update_shift_details_in_attendance(doc, method):
	if frappe.db.exists("Shift Assignment", {"employee": doc.employee, "start_date": doc.attendance_date}):
		site, project, shift, post_type, post_abbrv, roster_type = frappe.get_value("Shift Assignment", {"employee": doc.employee, "start_date": doc.attendance_date}, ["site", "project", "shift", "post_type", "post_abbrv", "roster_type"])
		frappe.db.sql("""update `tabAttendance`
			set project = %s, site = %s, operations_shift = %s, post_type = %s, post_abbrv = %s, roster_type = %s
			where name = %s """, (project, site, shift, post_type, post_abbrv, roster_type, doc.name))

def manage_attendance_on_holiday(doc, method):
    '''
        Method used to create compensatory leave request and additional salary for holiday attendance
        on_submit or on_cancel of attendance will trigger this method
        args:
            doc is attendance object
            method is the method from the hook (like on_submit)
        if method is "on_submit", then create and submit the compensatory leave request and additional salary
        if method is "on_cancel", then cancel the compensatory leave request and additional salary, that is created for the attendance
    '''

    # Get holiday list of dicts with `holiday_date` and `description`
    holidays = get_holidays_for_employee(doc.employee, doc.attendance_date, doc.attendance_date)

    # process compensatory leave request and additional salary if attendance status not equals "Absent" or "On Leave"
    if len(holidays) > 0 and doc.status not in ["Absent", "On Leave"]:
        salary_component = frappe.db.get_single_value('HR and Payroll Additional Settings', 'holiday_additional_salary_component')
        if not salary_component:
            frappe.throw(_("Please Contact HRD to configure Salary Component for Holiday Additional Salary !!"))

        # create and submit additional salary and compensatory leave request on attendance submit
        if method == 'on_submit':
            remark = _("Worked on {0}".format(holidays[0].description))
            leave_type = frappe.db.get_single_value('HR and Payroll Additional Settings', 'holiday_compensatory_leave_type')
            if not leave_type:
                frappe.throw(_("Please Contact HRD to configure Leave Type for Holiday Compensatory Leave Request !!"))

            if not is_site_allowance_exist_for_this_employee(doc.employee, doc.attendance_date):
                create_additional_salary_from_attendance(doc, salary_component, remark)
            create_compensatory_leave_request_from_attendance(doc, leave_type, remark)

        # cancel additional salary and compensatory leave request on attendance cancel
        if method == "on_cancel":
            cancel_additional_salary_from_attendance(doc, salary_component)
            cancel_compensatory_leave_request_from_attendance(doc)


def cancel_additional_salary_from_attendance(attendance, salary_component):
    exist_additional_salary = frappe.db.exists('Additional Salary', {
        'employee': attendance.employee,
        'payroll_date': attendance.attendance_date,
        'salary_component': salary_component,
        'docstatus': 1
    })
    if exist_additional_salary:
        frappe.get_doc('Additional Salary', exist_additional_salary).cancel()

def create_compensatory_leave_request_from_attendance(attendance, leave_type, reason):
    compensatory_leave_request = frappe.new_doc('Compensatory Leave Request')
    compensatory_leave_request.employee = attendance.employee
    compensatory_leave_request.work_from_date = attendance.attendance_date
    compensatory_leave_request.work_end_date = attendance.attendance_date
    if attendance.status == "Half Day":
        compensatory_leave_request.half_day = True
        compensatory_leave_request.half_day_date = attendance.attendance_date
    compensatory_leave_request.reason = reason
    compensatory_leave_request.leave_type = leave_type
    compensatory_leave_request.insert(ignore_permissions=True)
    compensatory_leave_request.submit()

def cancel_compensatory_leave_request_from_attendance(attendance):
    exist_compensatory_leave_request = frappe.db.exists('Compensatory Leave Request', {
        'employee': attendance.employee,
        'work_from_date': attendance.attendance_date,
        'work_end_date': attendance.attendance_date,
        'docstatus': 1
    })
    if exist_compensatory_leave_request:
        frappe.get_doc('Compensatory Leave Request', exist_compensatory_leave_request).cancel()

def is_site_allowance_exist_for_this_employee(employee, date):
    '''
        Check if site allowance exists for the employee in the date
        return bool
    '''
    # Get Employee Schedule for this employee and date
    employee_schedule = frappe.db.exists('Employee Schedule',
        {'employee': employee, 'date': date, 'employee_availability': 'Working'})
    if employee_schedule:
        # Get Operations Site from the Employee Schedule
        operations_site = frappe.db.get_value('Employee Schedule', employee_schedule, 'site')
        if operations_site:
            # Return include site allowance, then return true
            return frappe.db.get_value('Operations Site', operations_site, 'include_site_allowance')
    return False

def create_additional_salary_from_attendance(attendance, salary_component, notes=None):
    additional_salary = frappe.new_doc('Additional Salary')
    additional_salary.employee = attendance.employee
    additional_salary.payroll_date = attendance.attendance_date
    additional_salary.salary_component = salary_component
    additional_salary.notes = notes
    additional_salary.overwrite_salary_structure_amount = False
    additional_salary.amount = get_amount_for_additional_salary_for_holiday(attendance)
    if additional_salary.amount > 0:
        additional_salary.insert(ignore_permissions=True)
        additional_salary.submit()

def get_amount_for_additional_salary_for_holiday(attendance):
    '''
        Method used to get calculated additional salary amount for holiday attendance
        args:
            attendance is attendance object
    '''
    # Calculate hours worked from the time in and time out recorded in attendance
    hours_worked = 0
    if attendance.in_time and attendance.out_time:
        hours_worked = time_diff_in_hours(attendance.out_time, attendance.in_time)

    # Get basic salary from the employee doctype
    basic_salary = frappe.db.get_value('Employee', attendance.employee, 'one_fm_basic_salary')

    # Calculate basic hourly wage
    basic_hourly_wage = 0
    shift_hours = 8 # Default 8 hour shift
    if attendance.shift:
        shift_hours = frappe.db.get_value('Shift Type', attendance.shift, 'duration')
    if basic_salary and basic_salary > 0 and shift_hours:
        basic_hourly_wage = basic_salary / (30 * shift_hours) # Assuming 30 days month

    return hours_worked * basic_hourly_wage * 1.5 * 2


def create_additional_salary_for_overtime(doc, method):
	""" 
	This function creates an additional salary document for a given by specifying the salary component for overtime set in the HR and Payroll Additional Settings,
	by obtaining the details from Attendance where the roster type is set to Over-Time.
	
	The over time rate is fetched from the project which is linked with the shift the employee was working in.
	The over time rate is calculated by multiplying the number of hours of the shift with the over time rate for the project.

	In case of no overtime rate is set for the project, overtime rates are fetched from HR and Payroll Additional Settings.
	Amount is calucated and additional salary is created as:
	1. If employee has an existing basic schedule on the same day - working day rate is applied
	2. Working on a holiday of type "weekly off: - day off rate is applied.
	3. Working on a holiday of type non "weekly off" - public/additional holiday.   

	Args:
		doc: The attendance document

	"""
	roster_type_basic = "Basic"
	roster_type_overtime = "Over-Time"

	days_of_week = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

	# Check if attendance is for roster type: Over-Time
	if doc.roster_type == roster_type_overtime:

		payroll_date = cstr(getdate())

		# Fetch payroll details from HR and Payroll Additional Settings
		overtime_component = frappe.db.get_single_value("HR and Payroll Additional Settings", 'overtime_additional_salary_component')
		working_day_overtime_rate = frappe.db.get_single_value("HR and Payroll Additional Settings", 'working_day_overtime_rate')
		day_off_overtime_rate = frappe.db.get_single_value("HR and Payroll Additional Settings", 'day_off_overtime_rate')
		public_holiday_overtime_rate = frappe.db.get_single_value("HR and Payroll Additional Settings", 'public_holiday_overtime_rate')

		# Fetch project and duration of the shift employee worked in operations shift
		project, overtime_duration = frappe.db.get_value("Operations Shift", doc.operations_shift, ["project", "duration"])

		# Fetch overtime details from project
		project_has_overtime_rate, project_overtime_rate = frappe.db.get_value("Project", {'name': project}, ["has_overtime_rate", "overtime_rate"])

		# If project has a specified overtime rate, calculate amount based on overtime rate and create additional salary
		if project_has_overtime_rate:
			
			if project_overtime_rate > 0:
				amount = round(project_overtime_rate * overtime_duration, 3)
				notes = "Calculated based on overtime rate set for the project: {project}".format(project=project)
				
				create_additional_salary(doc.employee, amount, overtime_component, payroll_date, notes)
			
			else:
				frappe.throw(_("Overtime rate must be greater than zero for project: {project}".format(project=project)))

		# If no overtime rate is specified, follow labor law => (Basic Hourly Wage * number of worked hours * 1.5)
		else:
			# Fetch assigned shift, basic salary  and holiday list for the given employee
			assigned_shift, basic_salary, holiday_list = frappe.db.get_value("Employee", {'employee': doc.employee}, ["shift", "one_fm_basic_salary", "holiday_list"])
			
			if assigned_shift:
				# Fetch duration of the shift employee is assigned to
				assigned_shift_duration = frappe.db.get_value("Operations Shift", assigned_shift, ["duration"])

				if basic_salary and basic_salary > 0:
					# Compute hourly wage
					daily_wage = round(basic_salary/30, 3)
					hourly_wage = round(daily_wage/assigned_shift_duration, 3)

					# Check if a basic schedule exists for the employee and the attendance date
					if frappe.db.exists("Employee Schedule", {'employee': doc.employee, 'date': doc.attendance_date, 'employee_availability': "Working", 'roster_type': roster_type_basic}):
						
						if working_day_overtime_rate > 0:
							
							# Compute amount as per working day rate
							amount = round(hourly_wage * overtime_duration * working_day_overtime_rate, 3)
							notes = "Calculated based on working day rate => (Basic hourly wage) * (Duration of worked hours) * {working_day_overtime_rate}".format(working_day_overtime_rate=working_day_overtime_rate)
							
							create_additional_salary(doc.employee, amount, overtime_component, payroll_date, notes)
						
						else:
							frappe.throw(_("No Wroking Day overtime rate set in HR and Payroll Additional Settings."))

					# Check if attendance date falls in a holiday list
					elif holiday_list:

						# Pass last parameter as "False" to get weekly off days
						holidays_weekly_off = get_holidays_for_employee(doc.employee, doc.attendance_date, doc.attendance_date, False, False)

						# Pass last paramter as "True" to get non weekly off days, ie, public/additional holidays 
						holidays_public_holiday = get_holidays_for_employee(doc.employee, doc.attendance_date, doc.attendance_date, False, True)

						# Check for weekly off days length and if description of day off is set as one of the weekdays. (By default, description is set to a weekday name)
						if len(holidays_weekly_off) > 0 and holidays_weekly_off[0].description in days_of_week:
						
							if day_off_overtime_rate > 0:
								
								# Compute amount as per day off rate
								amount = round(hourly_wage * overtime_duration * day_off_overtime_rate, 3)
								notes = "Calculated based on day off rate => (Basic hourly wage) * (Duration of worked hours) * {day_off_overtime_rate}".format(day_off_overtime_rate=day_off_overtime_rate)

								create_additional_salary(doc.employee, amount, overtime_component, payroll_date, notes)
							
							else:
								frappe.throw(_("No Day Off overtime rate set in HR and Payroll Additional Settings."))

						# Check for weekly off days set to "False", ie, Public/additional holidays in holiday list
						elif len(holidays_public_holiday) > 0:
							
							if public_holiday_overtime_rate > 0:
								
								# Compute amount as per public holiday rate
								amount = round(hourly_wage * overtime_duration * public_holiday_overtime_rate, 3)
								notes = "Calculated based on day off rate => (Basic hourly wage) * (Duration of worked hours) * {public_holiday_overtime_rate}".format(public_holiday_overtime_rate=public_holiday_overtime_rate)

								create_additional_salary(doc.employee, amount, overtime_component, payroll_date, notes)
							
							else:
								frappe.throw(_("No Public Holiday overtime rate set in HR and Payroll Additional Settings."))
					else:
						frappe.throw(_("No basic Employee Schedule or Holiday List found for employee: {employee}".format(employee=doc.employee)))
				
				else:
					frappe.throw(_("Basic Salary not set for employee: {employee} in the employee record.".format(employee=doc.employee)))
			
			else:
				frappe.throw(_("Shift not set for employee: {employee} in the employee record.".format(employee=doc.employee)))
