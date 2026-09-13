# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Delivery Carrier DPD France",
    "version": "19.0.1.1.0",
    "summary": "Rate, ship and track parcels with DPD France: Predict, Relais, Classic",
    "author": "ROEKISH",
    "maintainers": ["alexis2m"],
    "website": "https://github.com/roekish-org/odoo-delivery-dpd",
    "category": "Inventory/Delivery",
    "license": "AGPL-3",
    "images": ["static/description/banner.png"],
    "depends": [
        "stock_delivery",
    ],
    "post_init_hook": "post_init_hook",
    # roulier (labels) is imported lazily and fails closed with a clear
    # message when missing, so it is NOT declared as a hard
    # external_dependency: the module stays installable and light. The
    # Pickup relay search only needs `requests` and `lxml`, shipped with Odoo.
    "data": [
        "security/roekish_delivery_dpd_security.xml",
        "security/ir.model.access.csv",
        "views/delivery_carrier_views.xml",
        "views/stock_picking_views.xml",
        "views/sale_order_views.xml",
        "wizards/pickup_wizard_views.xml",
    ],
    "demo": [
        "demo/roekish_delivery_dpd_demo.xml",
    ],
    "installable": True,
}
