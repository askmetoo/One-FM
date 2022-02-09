import frappe
from fleet_management.doctype.vehicle_leasing_contract.vehicle_leasing_contract import update_leasing_cotract_with_vehicle_list


@frappe.whitelist(allow_guest=True)
def vehicle_naming_series(doc, method):
    name = 'VHL-'
    count = frappe.db.count('Vehicle')
    if not count or count <= 0:
        count = 1
    else:
        count += 1
    doc.name = name+str(int(count)).zfill(4)

def after_insert_vehicle(doc, method):
	if doc.vehicle_leasing_contract and doc.vehicle_leasing_details:
		lc = frappe.get_doc('Vehicle Leasing Contract', doc.vehicle_leasing_contract)
		update_leasing_cotract_with_vehicle_list(doc, lc)