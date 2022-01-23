# -*- coding: utf-8 -*-
# Copyright (c) 2020, omar jaber and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from datetime import date, datetime
import frappe
from frappe.model.document import Document
from frappe.utils import cstr,month_diff,today,getdate,date_diff,add_years

# maps
MONTH_MAP = {
	1:'Jan', 2:'Feb', 3:'Mar', 4:'Apr', 5:'May', 6:'Jun', 7:'Jul',
	8:'Aug', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dec'
}


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
@frappe.whitelist()
def generate_contract_invoice(doc, posting_date=None):
	"""
	Get employee attendance based on Employee Schedule
	Shift Type and Attendance
	"""
	try:
		# get date
		if not posting_date:
			posting_date = datetime.today().date()
		has_remaining_days = False
		if not (posting_date):
			posting_date = datetime.today().date().replace(day=int(doc.due_date) or 28)
		if(posting_date.month==datetime.today().month and
			posting_date.year==datetime.today().year):
			has_remaining_days = True

		start_date = posting_date.replace(day=1)
		end_date = frappe.utils.get_last_day(posting_date)
		last_day = end_date.day

		created_invoices = []
		# get sale items as sql tuple ('Pen', 'Book')
		sale_items = "("
		for c, i in enumerate(doc.items):
			if(len(doc.items)==c+1):
				sale_items+=f" '{i.item_code}'"
			else:
				sale_items+=f" '{i.item_code}',"
		sale_items += ")"

		# query parameters
		params = frappe._dict({
			'start_date':start_date,
			'remain_start_date': posting_date,
			'end_date':end_date,
			'project':doc.project,
			'sale_items': sale_items,
		})
		# check if invoice required in seprate sites
		if False: #(doc.invoice_type=='single'):
			invoice_items = []
			for i in doc.items:
				#  update params sale_item
				params.sale_item = i.item_code
				# loop through sale items and generate invoice
				attendance_present = len(get_attendance_present(params)) or 1
				days_off = len(get_holidays(params)) or 1
				if(has_remaining_days): #check if there are days upfront
					attendance_present += len(get_balance_schedule(params))
				total_engagement = (attendance_present) + (days_off)
				total_days = last_day * i.head_count
				if(total_engagement == total_days):
					amount = i.head_count*last_day
				elif (total_engagement > total_days):
					try:
						if(i.overtime_rate):
							amount += ((total_engagement-total_days)*i.overtime_rate)/i.rate
						else:
							amount += ((total_engagement-total_days)*i.rate*1.5)/i.rate
					except Exception as e:
						amount += ((total_engagement-total_days)*i.rate*1.5)/i.rate
				else:
					amount = i.head_count*last_day
					amount -= amount * (((total_engagement-total_days)/total_days)*-1)

				invoice_items.append({
					'item_code':i.item_code,
					'price_list_rate':i.price_list_rate,
					'rate':i.rate,
					'qty':amount,
					'days':amount,
					'description': f"Total man days for {MONTH_MAP[posting_date.month]}, {posting_date.year} is {amount/i.rate}",
					'monthly_rate':i.rate,
					'contracts_uom':i.uom,
				})
			created_invoices.append(make_invoice(frappe._dict({
				'contracts':doc,
				'invoice_items':invoice_items,
				'posting_date':posting_date,
				})))

		else:
			for site in get_sites(params):
				invoice_items = []
				params.site = site
				for i in doc.items:
					params.sale_item = i.item_code
					# loop through sale items and generate invoice
					attendance_present = len(get_attendance_present(params)) or 1
					days_off = len(get_holidays(params)) or 1
					if(has_remaining_days): #check if there are days upfront
						attendance_present += len(get_balance_schedule(params))
					total_engagement = (attendance_present) + (days_off)
					total_days = i.head_count*last_day

					print(total_engagement, total_days)
					if(total_engagement == total_days):
						amount = i.head_count*last_day
					elif (total_engagement > total_days):
						# consider overtime
						amount = i.head_count*last_day
						try:
							if(i.overtime_rate):
								amount += ((total_engagement-total_days)*i.overtime_rate)/i.rate
							else:
								amount += ((total_engagement-total_days)*i.rate*1.5)/i.rate
						except Exception as e:
							amount += ((total_engagement-total_days)*i.rate*1.5)/i.rate
					else:
						amount = i.head_count*last_day
						amount -= amount * (((total_engagement-total_days)/total_days)*-1)

					invoice_items.append({
						'item_code':i.item_code,
						'price_list_rate':i.price_list_rate,
						'rate':i.rate,
						'qty':amount,
						'days':amount,
						'description': f"Total man days for {MONTH_MAP[posting_date.month]}, {posting_date.year} is {amount/i.rate}",
						'site':site,
						'monthly_rate':i.rate,
						'contracts_uom':i.uom,
					})

				print(site, invoice_items)
				# make invoice
				created_invoices.append(make_invoice(frappe._dict({
					'contracts':doc,
					'invoice_items':invoice_items,
					'posting_date':posting_date,
					'title':site
					})))
		return created_invoices
	except Exception as e:
		frappe.log_error(str(e), 'Make monhtly contrcat invoice')
		frappe.throw(str(e))
	return []


def get_holidays(params):
	condition = " "
	if(params.site):
		condition += f'AND es.site="{params.site}"'
	query = frappe.db.sql(f"""
		SELECT DISTINCT(em.employee_id), em.name, h.holiday_date as holiday,
		em.holiday_list FROM `tabEmployee` em JOIN `tabHoliday` h
		ON h.parent=em.holiday_list JOIN `tabEmployee Schedule` es
		ON es.employee=em.name JOIN `tabPost Type` pt ON
		pt.name=es.post_type
		WHERE es.date BETWEEN '{params.start_date}' AND '{params.end_date}'
		AND h.holiday_date BETWEEN '{params.start_date}' AND '{params.end_date}'
		AND es.project="{params.project}" AND pt.sale_item="{params.sale_item}"
		{condition} ORDER by em.name;
	""", as_dict=1)
	return query

def get_attendance_present(params):
	condition = " "
	if(params.site):
		condition += f'AND es.site="{params.site}"'
	query =  frappe.db.sql(f"""
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
		WHERE pt.sale_item="{params.sale_item}"
		AND es.date BETWEEN '{params.start_date}' AND '{params.end_date}'
		AND es.project="{params.project}" AND at.attendance_date=es.date
		AND at.status='Present' {condition};
		""", as_dict=1)
	return query

def get_balance_schedule(params):
	condition = " "
	if(params.site):
		condition += f'AND es.site="{params.site}"'
	query = frappe.db.sql(f"""
		SELECT es.employee, es.employee_availability as available,
		es.date, es.post_type, es.site, pt.sale_item
		FROM `tabEmployee Schedule` es
		JOIN `tabPost Type` pt ON pt.name=es.post_type
		WHERE pt.sale_item="{params.sale_item}"
		AND es.date BETWEEN '{params.remain_start_date}' AND '{params.end_date}'
		AND es.project="{params.project}" AND es.employee_availability='Working'
		{condition}
	""", as_dict=1)
	return query

def get_sites(params):
	return [i.site for i in frappe.db.sql(f"""
		SELECT DISTINCT(es.site) as site
		FROM `tabEmployee Schedule` es JOIN
		`tabPost Type` pt ON pt.name=es.post_type
		WHERE es.date BETWEEN '{params.start_date}'
		 AND '{params.end_date}'
		AND es.project="{params.project}" AND
		pt.sale_item IN {params.sale_items}
	;""", as_dict=1)]

def make_invoice(kwargs):
	invoice = frappe.get_doc({
		'doctype':'Sales Invoice',
		'set_posting_time':1,
		'posting_date':kwargs.posting_date,
		'customer':kwargs.contracts.client,
		'contracts':kwargs.contracts.name,
		'due_date': frappe.utils.add_to_date(frappe.utils.today(), weeks=1),
		'update_stock':1,
		'items': kwargs.invoice_items,
		})
	if(kwargs.title):
		invoice.title = f"{kwargs.contracts.client}-{kwargs.title}"

	# save invoice
	invoice.insert(ignore_permissions=True)
	return invoice.name


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
