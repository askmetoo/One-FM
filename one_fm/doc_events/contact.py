import frappe


def accommodation_contact_update(doc, method):
	link_name = doc.get_link_for('Accommodation')
	if link_name and doc.one_fm_doc_contact_field:
		frappe.db.set_value('Accommodation', link_name, doc.one_fm_doc_contact_field, doc.name)
