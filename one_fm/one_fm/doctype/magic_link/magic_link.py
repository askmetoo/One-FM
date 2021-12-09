# Copyright (c) 2021, one fm and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import decrypt, encrypt
from frappe.utils import get_url

class MagicLink(Document):
	pass

def get_encrypted_magic_link(magic_link):
	'''
		Method is used to encrypt the magic link
		args:
			magic_link: Magic Link ID (example: ML.0000001)
		return encrypted magic link id
	'''
	return encrypt(magic_link)

def get_magic_link(doctype, name, link_for):
	'''
		Method used to send the magic Link to the Job Applicant from Job Applicant doctype
		args:
			doctype: Reference Doctype name, from which the magic link created
			name: Reference Doctype ID, from which the magic link created
			link_for: The doctype for which the magic link is created (example: Career History)

		return Magic Link ID
	'''

	# Check if magic_link exisit for the given doctype and not expired
	magic_link = frappe.db.exists('Magic link',
		{'reference_doctype': doctype, 'reference_docname': name, 'expired': False, 'link_for': link_for})

	# If there is no magic link exist for the reference, then create a magic link
	if not magic_link:
		magic_link = create_magic_link(doctype, name, link_for)

	return magic_link

def create_magic_link(doctype, name, link_for):
	'''
		Method used to send the magic Link to the Job Applicant from Job Applicant doctype
		args:
			doctype: Reference Doctype name, from which the magic link created
			name: Reference Doctype ID, from which the magic link created
			link_for: The doctype for which the magic link is created (example: Career History)

		return Magic Link ID
	'''
	magic_link = frappe.new_doc('Magic Link')
	magic_link.reference_doctype = doctype
	magic_link.reference_docname = name
	magic_link.link_for = link_for
	magic_link.save(ignore_permissions=True)
	return magic_link.name

def authorize_magic_link(encrypted_magic_link, doctype, link_for):
	'''
		Method is used to check the magic ling exist or expired
		args:
			encrypted_magic_link: encrypted value of Magic Link ID
			doctype: Reference Doctype name, from which the magic link created
			link_for: The doctype for which the magic link is created (example: Career History)

		return Magic Link ID (example: ML.000001)
	'''
	decrypted_magic_link = False
	try:
		decrypted_magic_link = decrypt(encrypted_magic_link)
	except Exception as e:
		frappe.throw(_("Not Permitted ! Magic Link is Not exisit !!"), frappe.PermissionError)

	if decrypted_magic_link:
		magic_link_exist = frappe.db.exists('Magic Link',
			{'name': decrypted_magic_link, 'expired': False, 'reference_doctype': doctype, 'link_for': link_for})

		if magic_link_exist:
			return magic_link_exist
		else:
			frappe.throw(_("Not Permitted ! Magic Link is Expired or Not exisit!!"), frappe.PermissionError)

def send_magic_link(doctype, name, link_for, recipients, url_prefix, msg, subject):
	'''
	Method used to send the magic Link for link_for doctype to the doctype
	args:
		doctype: Reference Doctype name, from which the magic link created
		name: Reference Doctype ID, from which the magic link created
		link_for: The doctype for which the magic link is created (example: Career History)
		recipients: array of recipient email(s) (example: [jam@one-fm.com])
		url_prefix: prefix to the url (example: "/career_history?magic_link=")
		msg: Message content to the Recipients without the magic link
		subject: Subject of the email
	'''
	# Check if magic_link exisit for the Job Applicant and not expired
	magic_link = get_magic_link(doctype, name, link_for)
	if magic_link:
		# Encrypt the magic link benfore send
		encrypted_magic_link = get_encrypted_magic_link(magic_link)
		# Email Magic Link to the Recipients
		sender = frappe.get_value("Email Account", filters={"default_outgoing": 1}, fieldname="email_id") or None
		magic_link_url = get_url(url_prefix) + encrypted_magic_link
		msg += "<br/><a href='{0}'>Magic Link</a>".format(magic_link_url)
		frappe.sendmail(sender=sender, recipients=recipients, content=msg, subject=subject)
