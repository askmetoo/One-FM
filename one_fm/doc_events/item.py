import frappe
from frappe import _

def insert_naming_series(series):
    """insert series if missing"""
    if frappe.db.get_value('Series', series, 'name', order_by="name") == None:
        frappe.db.sql("insert into tabSeries (name, current) values (%s, 0)", (series))

@frappe.whitelist()
def validate_item(doc, method):
    final_description = doc.description
    if not doc.item_barcode:
        doc.item_barcode = doc.item_code
    if not doc.parent_item_group:
        doc.parent_item_group = "All Item Groups"
    doc.description = final_description

@frappe.whitelist()
def before_insert_item(doc, method):
    if not doc.item_id:
        set_item_id(doc)
    if not doc.item_code and doc.item_id:
        doc.item_code = get_item_code(doc.subitem_group, doc.item_group, doc.item_id)

def set_item_id(doc):
    next_item_id = "000000"
    item_id = get_item_id_series(doc.subitem_group, doc.item_group)
    if item_id:
        next_item_id = str(int(item_id)+1)
        for i in range(0, 6-len(next_item_id)):
            next_item_id = '0'+next_item_id
    doc.item_id = next_item_id

@frappe.whitelist()
def get_item_code(subitem_group = None ,item_group = None ,cur_item_id = None):
    item_code = ""
    if subitem_group:
        subitem_group_code = frappe.db.get_value('Item Group', subitem_group, 'one_fm_item_group_abbr')
        if subitem_group_code:
            item_code = subitem_group_code
        else:
            frappe.msgprint(_("Set Abbreviation for the Item Group {0}".format(subitem_group)),
                alert=True, indicator='orange')
        if item_group:
            item_group_code = frappe.db.get_value('Item Group', item_group, 'one_fm_item_group_abbr')
            if item_group_code:
                item_code = subitem_group_code+"-"+item_group_code
            else:
                frappe.msgprint(_("Set Abbreviation for the Item Group {0}".format(item_group)),
					alert=True, indicator='orange')
    item_code += ("-"+cur_item_id) if cur_item_id else ""
    return item_code

@frappe.whitelist(allow_guest=True)
def get_item_id_series(subitem_group, item_group):
    previous_item_id = frappe.db.sql("select item_id from `tabItem` where subitem_group='{0}' and item_group='{1}' order by item_id desc".format(subitem_group, item_group))
    if previous_item_id:
        item_group_abbr = frappe.db.get_value('Item Group', item_group, 'one_fm_item_group_abbr')
        if item_group_abbr:
            abbr_item_group_list = frappe.db.get_list('Item Group', {'one_fm_item_group_abbr': item_group_abbr})
            if abbr_item_group_list and len(abbr_item_group_list) > 1:
                item_id_list = []
                for abbr_item_group in abbr_item_group_list:
                    item_id = frappe.db.sql("select item_id from `tabItem` where item_group='{0}' order by item_id desc".format(abbr_item_group['name']))
                    if item_id:
                        item_id_list.append(item_id[0][0])
                return get_sorted_item_id(item_id_list)
        return previous_item_id[0][0]
    else:
        return '0000'

def get_sorted_item_id(item_id_list):
    max = item_id_list[0]
    for item_id in item_id_list:
        if item_id > max:
            max = item_id
    return max