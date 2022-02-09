import frappe


@frappe.whitelist(allow_guest=True)
def validate_get_item_group_parent(doc, method):
    # first_parent = doc.parent_item_group
    # second_parent = frappe.db.get_value('Item Group', {"name": first_parent}, 'parent_item_group')
    #
    # if first_parent == 'All Item Groups' or second_parent == 'All Item Groups':
    #     doc.is_group = 1

    new_item_group_code = frappe.db.sql("select item_group_code+1 from `tabItem Group` where parent_item_group ='{0}' order by item_group_code desc limit 1".format(doc.parent_item_group))
    if new_item_group_code:
        new_item_group_code_final = new_item_group_code[0][0]
    else:
        new_item_group_code_final = '1'

    doc.item_group_code = str(int(new_item_group_code_final)).zfill(3)

@frappe.whitelist()
def after_insert_item_group(doc, method):
    if doc.parent_item_group and doc.parent_item_group != 'All Item Group':
        set_item_group_description_form_parent(doc)
    doc.save(ignore_permissions=True)

def set_item_group_description_form_parent(doc):
    parent = frappe.get_doc('Item Group', doc.parent_item_group)
    doc.is_fixed_asset = parent.is_fixed_asset
    if parent.is_fixed_asset and parent.asset_category and not doc.asset_category:
        doc.asset_category = parent.asset_category
    if not doc.one_fm_item_group_descriptions and parent.one_fm_item_group_descriptions:
        for desc in parent.one_fm_item_group_descriptions:
            item_group_description = doc.append('one_fm_item_group_descriptions')
            item_group_description.description_attribute = desc.description_attribute
            item_group_description.from_parent = True