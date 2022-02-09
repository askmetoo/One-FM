import frappe
from frappe import _

def bank_account_on_update(doc, method):
    update_onboarding_doc_for_bank_account(doc)

def update_onboarding_doc_for_bank_account(doc):
    if doc.onboard_employee:
        progress_wf_list = {'Draft': 0, 'Open Request': 30, 'Processing Bank Account Opening': 70,
            'Rejected by Accounts': 100, 'Active Account': 100}
        bank_account_status = 1
        if doc.workflow_state == 'Rejected by Accounts':
            bank_account_status = 2
        if doc.workflow_state in progress_wf_list:
            progress = progress_wf_list[doc.workflow_state]
        oe = frappe.get_doc('Onboard Employee', doc.onboard_employee)
        oe.bank_account = doc.name
        oe.bank_account_progress = progress
        oe.bank_account_docstatus = bank_account_status
        oe.bank_account_status = doc.workflow_state
        oe.account_name = doc.account_name
        oe.bank = doc.bank
        if oe.workflow_state == 'Duty Commencement':
            oe.workflow_state = 'Bank Account'
        oe.save(ignore_permissions=True)

def bank_account_on_trash(doc, method):
    if doc.onboard_employee:
        oe = frappe.get_doc('Onboard Employee', doc.onboard_employee)
        oe.bank_account = ''
        oe.bank_account_progress = 0
        oe.bank_account_docstatus = ''
        oe.bank_account_status = ''
        oe.account_name = doc.account_name
        oe.bank = doc.bank
        oe.save(ignore_permissions=True)

def validate_iban_is_filled(doc, method):
    if not doc.iban and doc.workflow_state == 'Active Account':
        frappe.throw(_("Please Set IBAN before you Mark Open the Bank Account"))