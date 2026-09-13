# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "delivery.dpd.pickup.mixin"]

    def _action_confirm(self):
        res = super()._action_confirm()
        # Carry the chosen Pickup relay onto the delivery orders created at
        # confirmation, unless one was already set on the picking.
        for order in self:
            if not order.dpd_pickup_point_code:
                continue
            pickings = order.picking_ids.filtered(
                lambda p: p.dpd_is_pickup and not p.dpd_pickup_point_code
            )
            pickings.write(
                {
                    "dpd_pickup_point_code": order.dpd_pickup_point_code,
                    "dpd_pickup_point_name": order.dpd_pickup_point_name,
                    "dpd_pickup_point_street": order.dpd_pickup_point_street,
                    "dpd_pickup_point_zip": order.dpd_pickup_point_zip,
                    "dpd_pickup_point_city": order.dpd_pickup_point_city,
                }
            )
        return res
