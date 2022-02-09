import frappe


@frappe.whitelist(allow_guest=True)
def warehouse_naming_series(doc, method):
    if doc.one_fm_project:
        name = "WRH"
        project_code = frappe.db.get_value('Project', doc.one_fm_project, 'one_fm_project_code')
        if not project_code:
            project_code = create_new_project_code(doc.one_fm_project)
        if project_code:
            name += '-'+project_code
        doc.name = name +'-'+doc.warehouse_code+'-'+doc.warehouse_name

def create_new_project_code(project_id):
    project_code = frappe.db.sql("select one_fm_project_code+1 from `tabProject` order by one_fm_project_code desc limit 1")
    if project_code:
        new_project_code = project_code[0][0]
    else:
        new_project_code = '1'
    frappe.db.set_value('Project', project_id, 'one_fm_project_code', str(int(new_project_code)).zfill(4))
    return str(int(new_project_code)).zfill(4)

@frappe.whitelist()
def before_insert_warehouse(doc, method):
    set_warehouse_code(doc)

def set_warehouse_code(doc):
    if doc.one_fm_project:
        query = """
            select
                warehouse_code+1
            from
                `tabWarehouse`
            where one_fm_project = '{0}'
            order by
                warehouse_code
            desc limit 1
        """
        new_warehouse_code = frappe.db.sql(query.format(doc.one_fm_project))
        if new_warehouse_code:
            new_warehouse_code_final = new_warehouse_code[0][0]
        else:
            new_warehouse_code_final = '1'
        doc.warehouse_code = str(int(new_warehouse_code_final)).zfill(4)

@frappe.whitelist()
def set_warehouse_contact_from_project(doc, method):
    if doc.one_fm_project and doc.one_fm_site:
        site = frappe.get_doc("Operations Site", doc.one_fm_site)
        # if site.site_poc:
        #     for poc in site.site_poc:
        #         if poc.poc:
        #             contact = frappe.get_doc('Contact', poc.poc)
        #             links = contact.append('links')
        #             links.link_doctype = doc.doctype
        #             links.link_name = doc.name
        #             contact.save(ignore_permissions=True)
        if site.address:
            address = frappe.get_doc('Address', site.address)
            links = address.append('links')
            links.link_doctype = doc.doctype
            links.link_name = doc.name
            address.save(ignore_permissions=True)
