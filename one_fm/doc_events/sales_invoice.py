import frappe


def before_submit_sales_invoice(doc, method):
    if doc.contracts:
        is_po_for_invoice = frappe.db.get_value('Contracts', doc.contracts, 'is_po_for_invoice')
        if is_po_for_invoice == 1 and not doc.po:
            frappe.throw('Please Attach Customer Purchase Order')

def set_print_settings_from_contracts(doc, method):
    if doc.contracts:
        contracts_print_settings = frappe.db.get_values('Contracts', doc.contracts, ['sales_invoice_print_format', 'sales_invoice_letter_head'], as_dict=True)
        if contracts_print_settings and len(contracts_print_settings) > 0:
            if contracts_print_settings[0].sales_invoice_print_format:
                doc.format = contracts_print_settings[0].sales_invoice_print_format
            if contracts_print_settings[0].sales_invoice_letter_head:
                doc.letter_head = contracts_print_settings[0].sales_invoice_letter_head