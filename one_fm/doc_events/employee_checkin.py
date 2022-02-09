import frappe
from frappe import _
from frappe.utils import get_datetime, cstr, cint
from erpnext.hr.doctype.shift_assignment.shift_assignment import get_employee_shift_timings, get_actual_start_end_datetime_of_shift
from one_fm.utils import create_notification_log, haversine, get_employee_user_id
from datetime import timedelta


def employee_checkin_validate(doc, method):
	try:
		perm_map = {
			"IN" : "Arrive Late",
			"OUT": "Leave Early"
		}
		existing_perm = None
		checkin_time = get_datetime(doc.time)
		shift_actual_timings = get_actual_start_end_datetime_of_shift(doc.employee, get_datetime(doc.time), True)
		prev_shift, curr_shift, next_shift = get_employee_shift_timings(doc.employee, get_datetime(doc.time))
		if curr_shift:
			existing_perm = frappe.db.exists("Shift Permission", {"date": curr_shift.start_datetime.strftime('%Y-%m-%d'), "employee": doc.employee, "permission_type": perm_map[doc.log_type], "workflow_state": "Approved"})
			assignment, shift_type = frappe.get_value("Shift Assignment", {"employee": doc.employee, "start_date": curr_shift.start_datetime.date(), "shift_type": curr_shift.shift_type.name}, ["shift", "shift_type"])
			doc.operations_shift = assignment
			doc.shift_type = shift_type
	
		if shift_actual_timings[0] and shift_actual_timings[1]:
			if existing_perm:
				perm_doc = frappe.get_doc("Shift Permission", existing_perm)
				permitted_time = get_datetime(perm_doc.date) + (perm_doc.arrival_time if doc.log_type == "IN" else perm_doc.leaving_time)
				if doc.log_type == "IN" and (checkin_time <= permitted_time and checkin_time >= curr_shift.start_datetime):
					doc.time = 	curr_shift.start_datetime
					doc.skip_auto_attendance = 0
					doc.shift_permission = existing_perm
				elif doc.log_type == "OUT" and (checkin_time >= permitted_time and checkin_time <= curr_shift.start_datetime):
					doc.time = 	curr_shift.end_datetime
					doc.skip_auto_attendance = 0
					doc.shift_permission = existing_perm
	except Exception as e:
		frappe.throw(e)

@frappe.whitelist()
def checkin_after_insert(doc, method):
	print("CALLED CHECKIN AFTER INSERT")
	# These are returned according to dates. Time is not taken into account
	prev_shift, curr_shift, next_shift = get_employee_shift_timings(doc.employee, get_datetime(doc.time))
	
	# In case of back to back shift
	if doc.shift_type:
		shift_doc = frappe.get_doc("Shift Type", doc.shift_type)
		curr_shift = frappe._dict({
			'actual_start': doc.shift_actual_start,
			'actual_end': doc.shift_actual_end, 
			'end_datetime': doc.shift_end, 
			'start_datetime': doc.shift_start, 
			'shift_type': shift_doc
		})
	# print("72", prev_shift.end_datetime, curr_shift.end_datetime, next_shift.end_datetime)
	if curr_shift:
		shift_type = frappe.get_doc("Shift Type", curr_shift.shift_type.name)
		supervisor_user = get_notification_user(doc, doc.employee)
		distance, radius = validate_location(doc)
		message_suffix = _("Location logged is inside the site.") if distance <= radius else _("Location logged is {location}m outside the site location.").format(location=cstr(cint(distance)- radius))

		if doc.log_type == "IN" and doc.skip_auto_attendance == 0:
			#EARLY: Checkin time is before [Shift Start - Variable Checkin time] 
			#if get_datetime(doc.time) < get_datetime(curr_shift.actual_start):
			#	time_diff = get_datetime(curr_shift.start_datetime) - get_datetime(doc.time)
			#	hrs, mins, secs = cstr(time_diff).split(":")
			#	early = "{hrs} hrs {mins} mins".format(hrs=hrs, mins=mins) if cint(hrs) > 0 else "{mins} mins".format(mins=mins)
			#	subject = _("{employee} has checked in early by {early}. {location}".format(employee=doc.employee_name, early=early, location=message_suffix))
			#	message = _("{employee} has checked in early by {early}. {location}".format(employee=doc.employee_name, early=early, location=message_suffix))
			#	for_users = [supervisor_user]
			#	create_notification_log(subject, message, for_users, doc)

			# ON TIME
			#elif get_datetime(doc.time) >= get_datetime(doc.shift_actual_start) and get_datetime(doc.time) <= (get_datetime(doc.shift_start) + timedelta(minutes=shift_type.late_entry_grace_period)):
			#	subject = _("{employee} has checked in on time. {location}".format(employee=doc.employee_name, location=message_suffix))
			#	message = _("{employee} has checked in on time. {location}".format(employee=doc.employee_name, location=message_suffix))
			#	for_users = [supervisor_user]
			#	create_notification_log(subject, message, for_users, doc)

			# LATE: Checkin time is after [Shift Start + Late Grace Entry period]
			if get_datetime(doc.time) > (get_datetime(doc.shift_start) + timedelta(minutes=shift_type.late_entry_grace_period)):
				time_diff = get_datetime(doc.time) - get_datetime(doc.shift_start)
				hrs, mins, secs = cstr(time_diff).split(":")
				delay = "{hrs} hrs {mins} mins".format(hrs=hrs, mins=mins) if cint(hrs) > 0 else "{mins} mins".format(mins=mins)
				subject = _("{employee} has checked in late by {delay}. {location}".format(employee=doc.employee_name, delay=delay, location=message_suffix))
				message = _("{employee_name} has checked in late by {delay}. {location} <br><br><div class='btn btn-primary btn-danger late-punch-in' id='{employee}_{date}_{shift}'>Issue Penalty</div>".format(employee_name=doc.employee_name,shift=doc.operations_shift, date=cstr(doc.time), employee=doc.employee, delay=delay, location=message_suffix))
				for_users = [supervisor_user]
				create_notification_log(subject, message, for_users, doc)

		elif doc.log_type == "IN" and doc.skip_auto_attendance == 1:
			subject = _("Hourly Report: {employee} checked in at {time}. {location}".format(employee=doc.employee_name, time=doc.time, location=message_suffix))
			message = _("Hourly Report: {employee} checked in at {time}. {location}".format(employee=doc.employee_name, time=doc.time, location=message_suffix))
			for_users = [supervisor_user]
			create_notification_log(subject, message, for_users, doc)

		elif doc.log_type == "OUT":
			# Automatic checkout
			if not doc.device_id:
				from one_fm.api.tasks import send_notification
				subject = _("Automated Checkout: {employee} forgot to checkout.".format(employee=doc.employee_name))
				message = _('<a class="btn btn-primary" href="/desk#Form/Employee Checkin/{name}">Review check out</a>&nbsp;'.format(name=doc.name))
				for_users = [supervisor_user]
				print("124", doc.employee, supervisor_user)
				send_notification(subject, message, for_users)
			#EARLY: Checkout time is before [Shift End - Early grace exit time] 
			elif doc.device_id and get_datetime(doc.time) < (get_datetime(curr_shift.end_datetime) - timedelta(minutes=shift_type.early_exit_grace_period)):
				time_diff = get_datetime(curr_shift.end_datetime) - get_datetime(doc.time)
				hrs, mins, secs = cstr(time_diff).split(":")
				early = "{hrs} hrs {mins} mins".format(hrs=hrs, mins=mins) if cint(hrs) > 0 else "{mins} mins".format(mins=mins)
				subject = _("{employee} has checked out early by {early}. {location}".format(employee=doc.employee_name, early=early, location=message_suffix))
				message = _("{employee_name} has checked out early by {early}. {location} <br><br><div class='btn btn-primary btn-danger early-punch-out' id='{employee}_{date}_{shift}'>Issue Penalty</div>".format(employee_name=doc.employee_name, shift=doc.operations_shift, date=cstr(doc.time), employee=doc.employee_name, early=early, location=message_suffix))
				for_users = [supervisor_user]
				create_notification_log(subject, message, for_users, doc)

			# ON TIME
			#elif doc.device_id and get_datetime(doc.time) <= get_datetime(doc.shift_actual_end) and get_datetime(doc.time) >= (get_datetime(doc.shift_end) - timedelta(minutes=shift_type.early_exit_grace_period)):
			#	subject = _("{employee} has checked out on time. {location}".format(employee=doc.employee_name, location=message_suffix))
			#	message = _("{employee} has checked out on time. {location}".format(employee=doc.employee_name, location=message_suffix))
			#	for_users = [supervisor_user]
			#	create_notification_log(subject, message, for_users, doc)

			# LATE: Checkin time is after [Shift End + Variable checkout time]
			#elif doc.device_id and get_datetime(doc.time) > get_datetime(doc.shift_actual_end):
			#	time_diff = get_datetime(doc.time) - get_datetime(doc.shift_end)
			#	hrs, mins, secs = cstr(time_diff).split(":")
			#	delay = "{hrs} hrs {mins} mins".format(hrs=hrs, mins=mins) if cint(hrs) > 0 else "{mins} mins".format(mins=mins)
			#	subject = _("{employee} has checked out late by {delay}. {location}".format(employee=doc.employee_name, delay=delay, location=message_suffix))
			#	message = _("{employee} has checked out late by {delay}. {location}".format(employee=doc.employee_name, delay=delay, location=message_suffix))
			#	for_users = [supervisor_user]
			#	create_notification_log(subject, message, for_users, doc)
	else:
		# When no shift assigned, supervisor of active shift of the nearest site is sent a notification about unassigned checkin.
		location = doc.device_id
		# supervisor = get_closest_location(doc.time, location)
		reporting_manager = frappe.get_value("Employee", {"user_id": doc.owner}, "reports_to")
		supervisor = get_employee_user_id(reporting_manager)
		if supervisor:
			subject = _("{employee} has checked in on an unassigned shift".format(employee=doc.employee_name))
			message = _("{employee} has checked in on an unassigned shift".format(employee=doc.employee_name))
			for_users = [supervisor]
			create_notification_log(subject, message, for_users, doc)

def get_notification_user(doc, employee=None):
	"""
		Shift > Site > Project > Reports to
	"""
	operations_shift = frappe.get_doc("Operations Shift", doc.operations_shift)
	print(operations_shift.supervisor, operations_shift.name)
	if operations_shift.supervisor:
		supervisor = get_employee_user_id(operations_shift.supervisor)
		if supervisor != doc.owner:
			return supervisor
	
	operations_site = frappe.get_doc("Operations Site", operations_shift.site)
	print(operations_site.account_supervisor, operations_site.name)
	if operations_site.account_supervisor:
		account_supervisor = get_employee_user_id(operations_site.account_supervisor)
		if account_supervisor != doc.owner:
			return account_supervisor
	
	if operations_site.project:
		project = frappe.get_doc("Project", operations_site.project)
		print(project.account_manager, project.name)
		if project.account_manager:
			account_manager = get_employee_user_id(project.account_manager)
			if account_manager != doc.owner:
				return account_manager
	reporting_manager = frappe.get_value("Employee", {"name": employee}, "reports_to")
	print("191", employee, doc.owner, reporting_manager)
	return get_employee_user_id(reporting_manager)

def validate_location(doc):
	checkin_lat, checkin_lng = doc.device_id.split(",") if doc.device_id else (0, 0)
	site_name = frappe.get_value("Operations Shift", doc.operations_shift, "site")
	site_location = frappe.get_value("Operations Site", site_name, "site_location")
	site_lat, site_lng, radius = frappe.get_value("Location", site_location, ["latitude","longitude", "geofence_radius"] )
	distance =  haversine(site_lat, site_lng, checkin_lat, checkin_lng)
	return distance, radius