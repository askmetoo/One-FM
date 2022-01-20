# -*- coding: utf-8 -*-
# Copyright (c) 2020, omar jaber and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import cstr,month_diff,today,getdate,date_diff,add_years

class Contracts(Document):
	def validate(self):
		self.calculate_contract_duration()

	def calculate_contract_duration(self):
		duration_in_days = date_diff(self.end_date, self.start_date)
		self.duration_in_days = cstr(duration_in_days)
		full_months = month_diff(self.end_date, self.start_date)
		years = int(full_months / 12)
		months = int(full_months % 12)
		if(years > 0):
			self.duration = cstr(years) + ' year'
		if(years > 0 and months > 0):
			self.duration += ' and ' + cstr(months) + ' month'
		if(years < 1 and months > 0):
			self.duration = cstr(months) + ' month'

	def on_cancel(self):
		frappe.throw("Contracts cannot be cancelled. Please try to ammend the existing record.")

@frappe.whitelist()
def get_contracts_asset_items(contracts):
	contracts_item_list = frappe.db.sql("""
		SELECT ca.item_code, ca.count as qty, ca.uom
		FROM `tabContract Asset` ca , `tabContracts` c
		WHERE c.name = ca.parent and ca.parenttype = 'Contracts'
		and c.frequency = 'Monthly'
		and ca.docstatus = 0 and ca.parent = %s order by ca.idx asc
	""", (contracts), as_dict=1)
	return contracts_item_list

@frappe.whitelist()
def get_contracts_items(contracts):
	contracts_item_list = frappe.db.sql("""
		SELECT ca.item_code,ca.head_count as qty
		FROM `tabContract Item` ca , `tabContracts` c
		WHERE c.name = ca.parent and ca.parenttype = 'Contracts'
		and ca.docstatus = 0 and ca.parent = %s order by ca.idx asc
	""", (contracts), as_dict=1)
	return contracts_item_list

@frappe.whitelist()
def insert_login_credential(url, user_name, password, client):
	password_management_name = client+'-'+user_name
	password_management = frappe.new_doc('Password Management')
	password_management.flags.ignore_permissions  = True
	password_management.update({
		'password_management':password_management_name,
		'password_category': 'Customer Portal',
		'url': url,
		'username':user_name,
		'password':password
	}).insert()

	frappe.msgprint(msg = 'Online portal credentials are saved into password management',
       title = 'Notification',
       indicator = 'green'
    )

	return 	password_management

#renew contracts by one year
def auto_renew_contracts():
	filters = {
		'end_date' : today(),
		'is_auto_renewal' : 1
	}
	contracts_list = frappe.db.get_list('Contracts', fields="name", filters=filters, order_by="start_date")
	for contract in contracts_list:
		contract_doc = frappe.get_doc('Contracts', contract)
		contract_doc.end_date = add_years(contract_doc.end_date, 1)
		contract_doc.save()
		frappe.db.commit()

# Monthly invoice
def get_attendance_data(doc):
	"""
	Get employee attendance based on Employee Schedule
	Shift Type and Attendance
	"""
	sale_items = "("
	for c, i in enumerate(doc.items):
		if(len(doc.items)==c+1):
			sale_items+=f" '{i.item_code}'"
		else:
			sale_items+=f" '{i.item_code}',"
	sale_items += ")"

	invoice_items = []
	for i in doc.items:
		attendance_present = len(get_attendance_present()) or 1
		days_off = len(get_holidays()) or 1

		total_engagement = (attendance_present) + (days_off)
		total_days = 30 * i.head_count
		if(total_engagement == total_days):
			amount = i.head_count*i.rate*30
		elif (total_engagement > total_days):
			amount = i.head_count*i.rate*30
			amount += amount * ((total_engagement-total_days)/total_days)
		else:
			amount = i.head_count*i.rate*30
			amount -= amount * (((total_engagement-total_days)/total_days)*-1)

		invoice_items.append({
			'item_code':i.item_code,
			'price_list_rate':i.price_list_rate,
			'rate':i.rate,
			'qty':i.head_count,
			'amount':amount
		})

	print(invoice_items)

	# items = [frappe._dict(
	# {'item_code':i.item_code,
	# 'days_off':i.days_off}) for i in doc.items]
	# results = {}
	# # employee_list = []
	# employee_dict = {}
	# # for i.item_code in items:
	# 	results[i.item_code] = []
	# 	for j in query:
	# 		if(j.sale_item==i.item_code):
	# 			if(j.employee in employee_list):
	# 				employee_dict[j.employee].append(j)
	# 			else:
	# 				employee_list.append(j.employee)
	# 				employee_dict[j.employee]=[j]
	# 	results[i.item_code]=employee_dict
	# 	employee_list = []
	# 	employee_dict = {}
	return []


def get_holidays():
	return frappe.db.sql(f"""
		SELECT DISTINCT(em.employee_id), em.name, h.holiday_date as holiday,
		em.holiday_list FROM `tabEmployee` em JOIN `tabHoliday` h
		ON h.parent=em.holiday_list JOIN `tabEmployee Schedule` es
		ON es.employee=em.name JOIN `tabPost Type` pt ON
		pt.name=es.post_type
		WHERE es.date BETWEEN '2021-11-01' AND '2021-11-31'
		AND h.holiday_date BETWEEN '2021-11-01' AND '2021-11-31'
		AND es.project='Head Office' AND pt.sale_item='SRV-SEC-000003-12H-A-26D'
		AND '2021-11-31' ORDER by em.name;
	""", as_dict=1)

def get_attendance_present():
	return frappe.db.sql(f"""
		SELECT es.name, es.employee, es.employee_availability as available,
		es.date, IFNULL(NULL, at.attendance_date) as at_date,
		IFNULL(NULL, at.status) as status,
		IFNULL(NULL, at.name) as at_name, at.working_hours,
		st.duration, IFNULL(NULL, at.in_time) as at_in_time,
		IFNULL(NULL, at.out_time) as at_out_time, es.post_type,
		es.site, pt.sale_item FROM `tabEmployee Schedule` es
		JOIN `tabPost Type` pt ON pt.name=es.post_type
		JOIN `tabAttendance` at ON at.employee=es.employee
		JOIN `tabShift Type` st ON st.name=es.shift_type
		WHERE pt.sale_item='SRV-SEC-000003-12H-A-26D'
		AND es.date BETWEEN '2021-11-01' AND '2021-11-31'
		AND es.project='Head Office' AND at.attendance_date=es.date
		AND at.status='Present';
		""", as_dict=1)
