import frappe
from frappe import _
from frappe.utils import cstr


@frappe.whitelist()
def supplier_group_on_update(doc, method):
    """update series list"""
    if doc.abbr:
        set_options = frappe.get_meta('Supplier').get_field("naming_series").options+'\n'+'SUP-'+doc.abbr+'-.######'
        check_duplicate_naming_series(set_options)
        series_list = set_options.split("\n")

        # set in doctype
        set_series_for(doc, 'Supplier', series_list)

        # create series
        map(insert_naming_series, [d.split('.')[0] for d in series_list if d.strip()])
        frappe.db.set_value('Supplier Group', doc.name, 'supplier_naming_series', 'SUP-'+doc.abbr+'-.######')

        frappe.msgprint(_("Series Updated"))

def insert_naming_series(series):
    """insert series if missing"""
    if frappe.db.get_value('Series', series, 'name', order_by="name") == None:
        frappe.db.sql("insert into tabSeries (name, current) values (%s, 0)", (series))

def set_series_for(doc, doctype, ol):
    options = scrub_options_list(ol)

    # update in property setter
    prop_dict = {'options': "\n".join(options)}

    for prop in prop_dict:
        ps_exists = frappe.db.get_value("Property Setter",
            {"field_name": 'naming_series', 'doc_type': doctype, 'property': prop})

        if ps_exists:
            ps = frappe.get_doc('Property Setter', ps_exists)
            ps.value = prop_dict[prop]
            ps.save()
        else:
            ps = frappe.get_doc({
                'doctype': 'Property Setter',
                'doctype_or_field': 'DocField',
                'doc_type': doctype,
                'field_name': 'naming_series',
                'property': prop,
                'value': prop_dict[prop],
                'property_type': 'Text',
                '__islocal': 1
            })
            ps.save()

    frappe.clear_cache(doctype=doctype)

def check_duplicate_naming_series(set_options):
    parent = list(set(
        frappe.db.sql_list("""select dt.name
            from `tabDocField` df, `tabDocType` dt
            where dt.name = df.parent and df.fieldname='naming_series' and dt.name != 'Supplier'""")
        + frappe.db.sql_list("""select dt.name
            from `tabCustom Field` df, `tabDocType` dt
            where dt.name = df.dt and df.fieldname='naming_series' and dt.name != 'Supplier'""")
        ))
    sr = [[frappe.get_meta(p).get_field("naming_series").options, p] for p in parent]
    dt = frappe.get_doc("DocType", 'Supplier')
    options = scrub_options_list(set_options.split("\n"))
    for series in options:
        dt.validate_series(series)
        for i in sr:
            if i[0]:
                existing_series = [d.split('.')[0] for d in i[0].split("\n")]
                if series.split(".")[0] in existing_series:
                    frappe.throw(_("Series {0} already used in {1}").format(series,i[1]))

def scrub_options_list(ol):
    options = list(filter(lambda x: x, [cstr(n).strip() for n in ol]))
    return options
