# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models

# DPD France pricing zones, as in the "Zoning Europe" of DPD France contracts.
# Rates are negotiated per contract: enter your own grid.
DPD_ZONES = [
    ("FR", "France (metropolitan, Monaco)"),
    ("EU1", "Euro 1 (Germany, Belgium, Luxembourg, Netherlands)"),
    ("EU2", "Euro 2 (Austria, Spain, UK, Italy, Liechtenstein, Poland, Portugal, Czechia, Switzerland)"),
    ("EU3", "Euro 3 (Andorra, Croatia, Denmark, Estonia, Hungary, Ireland, Latvia, Lithuania, Slovakia, Slovenia, Sweden)"),
    ("EU4", "Euro 4 (Bulgaria, Finland, Greece, Norway, Romania)"),
    ("EU5", "Euro 5 (Bosnia, Serbia)"),
    ("INT", "Intercontinental (rest of the world)"),
]


class DeliveryDpdTariff(models.Model):
    _name = "delivery.dpd.tariff"
    _description = "DPD Tariff Grid Line"
    _order = "carrier_id, zone, max_weight"

    carrier_id = fields.Many2one(
        "delivery.carrier",
        string="Carrier",
        required=True,
        ondelete="cascade",
        index=True,
    )
    zone = fields.Selection(
        selection=DPD_ZONES,
        string="Zone",
        required=True,
    )
    max_weight = fields.Float(
        string="Weight up to (kg)",
        required=True,
        help="This line applies to shipments whose total weight is at or "
        "below this value, for the selected zone.",
    )
    price = fields.Float(
        string="Price",
        required=True,
        help="Delivery price charged to the customer, expressed in the "
        "carrier company currency.",
    )
    currency_id = fields.Many2one(
        related="carrier_id.company_id.currency_id",
        readonly=True,
    )
    delay_min = fields.Integer(
        string="Delivery days min",
        help="Shortest delivery time announced for this zone, in working days "
        "after hand-over. Leave 0 to use the carrier delivery time.",
    )
    delay_max = fields.Integer(
        string="Delivery days max",
        help="Longest delivery time announced for this zone, in working days "
        "after hand-over. Leave 0 to use the carrier delivery time.",
    )
