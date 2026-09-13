# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class DpdPickupMixin(models.AbstractModel):
    """Pickup relay holder shared by sale.order and stock.picking."""

    _name = "delivery.dpd.pickup.mixin"
    _description = "DPD Pickup relay holder"

    dpd_pickup_point_code = fields.Char(string="Pickup relay ID", copy=False)
    dpd_pickup_point_name = fields.Char(string="Pickup relay", copy=False)
    dpd_pickup_point_street = fields.Char(string="Pickup relay street", copy=False)
    dpd_pickup_point_zip = fields.Char(string="Pickup relay ZIP", copy=False)
    dpd_pickup_point_city = fields.Char(string="Pickup relay city", copy=False)
    dpd_is_pickup = fields.Boolean(
        string="DPD Relais delivery",
        compute="_compute_dpd_is_pickup",
        help="The selected carrier delivers to a DPD Pickup relay.",
    )

    @api.depends("carrier_id")
    def _compute_dpd_is_pickup(self):
        for rec in self:
            carrier = rec.carrier_id
            rec.dpd_is_pickup = (
                carrier.delivery_type == "dpd" and carrier.dpd_product == "DPD_Relais"
            )

    def action_dpd_choose_pickup_point(self):
        self.ensure_one()
        default_key = (
            "default_picking_id" if self._name == "stock.picking" else "default_sale_id"
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Choose a Pickup relay"),
            "res_model": "delivery.dpd.pickup.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {default_key: self.id},
        }
