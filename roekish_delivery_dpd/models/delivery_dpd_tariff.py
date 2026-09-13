# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models

# DPD France pricing zones. DPD France publishes no public grid (rates are
# negotiated per contract), so the split below mirrors the usual DPD CLASSIC
# Europe zoning and is meant to be adjusted to your own contract.
DPD_ZONES = [
    ("FR", "France (metropolitan, Monaco)"),
    ("EU1", "Europe zone 1 (Germany, Belgium, Luxembourg, Netherlands)"),
    ("EU2", "Europe zone 2 (rest of Europe, United Kingdom, Switzerland)"),
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
