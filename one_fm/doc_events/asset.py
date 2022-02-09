import frappe


def after_insert_asset(doc,handler=""):
    doc.append("asset_transfer", {
        "purpose": "Receipt",
        "transfer_date": doc.purchase_date,
        "location": doc.location
    })
    doc.save()

def on_asset_submit(doc, handler=""):
    #it will execute if it is not an existing asset
    asset_movement = frappe.db.get_value("Asset Movement Item",
		filters={'parenttype': 'Asset Movement', 'asset': doc.name},
		fieldname = ['parent'])