import frappe
from frappe import _
from frappe.core.doctype.version.version import get_diff
from one_fm.utils import create_notification_log, get_employee_user_id


@frappe.whitelist()
def project_on_update(doc, method):
	doc_before_save = doc.get_doc_before_save()
	notify_poc_changes(doc, doc_before_save)

def notify_poc_changes(doc, doc_before_save):
	changes = get_diff(doc_before_save, doc, for_child=True)
	if not changes and changes.changed:
		return

	# Variables needed for notification
	project = doc.name
	modified_by = doc.modified_by
	subject = "{modified_by} made some changes to {project} POC.".format(project=project, modified_by=modified_by)
	message = ''

	if changes.row_changed:
		for change in changes.row_changed:
			message = message + "Details of {poc_name} modified.\n".format(poc_name=doc.poc[change[1]].poc)
	if changes.added:
		for change in changes.added:
			if(change[0] == "poc"):
				message = message + "{poc_name} has been added as a POC.\n".format(poc_name=change[1].poc)
	if changes.removed:
		for change in changes.removed:
			if(change[0] == "poc"):
				message = message + "{poc_name} has been removed as a POC.\n".format(poc_name=change[1].poc)
	
	recipients = get_recipients(doc)
	create_notification_log(_(subject), _(message), recipients, doc)

def get_recipients(doc):
		"""
			Get line managers. Site Supervisor, Project Manager, Operations Manager.
		"""
		project_manager_user = get_employee_user_id(doc.account_manager)
		operations_manager = frappe.get_list("Employee", {"designation": "Operations Manager"}, ignore_permissions=True)
		recipient_list = []

		for manager in operations_manager:
			manager_user = get_employee_user_id(manager.name)
			recipient_list.append(manager_user)
		recipient_list.append(project_manager_user)		
		return recipient_list

def validate_poc_list(doc, method):
    project_type = str(doc.project_type)
    if project_type.lower() == "external" and len(doc.poc) == 0:
        frappe.throw('POC list is mandatory for project type <b>External</b>')

def get_depreciation_expense_amount(doc, handler=""):
    from_asset_depreciation = frappe.db.sql("""select sum(ja.debit) as depreciation_amount 
            from `tabJournal Entry Account` ja,`tabJournal Entry` j 
            where j.name = ja.parent and ja.parenttype = 'Journal Entry'
            and ja.project = %s and ja.reference_type = 'Asset'
            and j.voucher_type = 'Depreciation Entry' and ja.docstatus = 1 """,(doc.name),as_dict = 1)[0]

    doc.total_depreciation_expense = from_asset_depreciation.depreciation_amount