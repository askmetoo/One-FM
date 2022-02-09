import frappe
from frappe import _


def before_submit_purchase_receipt(doc, method):
    if not doc.one_fm_attach_delivery_note:
        frappe.throw(_('Please Attach Signed and Stamped Delivery Note'))
