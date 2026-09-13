# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class DpdPickupWizard(models.TransientModel):
    _name = "delivery.dpd.pickup.wizard"
    _description = "DPD Pickup relay search"

    # Exactly one target is set, depending on where the wizard was opened.
    picking_id = fields.Many2one("stock.picking", ondelete="cascade")
    sale_id = fields.Many2one("sale.order", ondelete="cascade")
    carrier_id = fields.Many2one("delivery.carrier")
    zip = fields.Char(string="ZIP code", required=True)
    city = fields.Char()
    country_id = fields.Many2one("res.country")
    weight = fields.Float(string="Weight (kg)")
    line_ids = fields.One2many(
        "delivery.dpd.pickup.line", "wizard_id", string="Pickup relays"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        if ctx.get("default_picking_id"):
            picking = self.env["stock.picking"].browse(ctx["default_picking_id"])
            partner = picking.partner_id
            res.setdefault("carrier_id", picking.carrier_id.id)
            res.setdefault("weight", picking.shipping_weight or picking.weight)
        elif ctx.get("default_sale_id"):
            order = self.env["sale.order"].browse(ctx["default_sale_id"])
            partner = order.partner_shipping_id
            res.setdefault("carrier_id", order.carrier_id.id)
            res.setdefault("weight", order._get_estimated_weight())
        else:
            partner = self.env["res.partner"]
        if partner:
            res.setdefault("zip", partner.zip)
            res.setdefault("city", partner.city)
            res.setdefault("country_id", partner.country_id.id)
        return res

    def action_search(self):
        self.ensure_one()
        self.line_ids.unlink()
        points = self.carrier_id._dpd_search_pickup_points(
            self.zip, self.city, self.country_id.code or "FR", self.weight
        )
        self.line_ids = [
            (
                0,
                0,
                {
                    "code": point.get("code"),
                    "name": point.get("name"),
                    "street": point.get("street"),
                    "zip": point.get("zip"),
                    "city": point.get("city"),
                    "distance": point.get("distance", 0.0),
                },
            )
            for point in points
        ]
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class DpdPickupLine(models.TransientModel):
    _name = "delivery.dpd.pickup.line"
    _description = "DPD Pickup relay candidate"
    _order = "distance, name"

    wizard_id = fields.Many2one(
        "delivery.dpd.pickup.wizard", required=True, ondelete="cascade"
    )
    code = fields.Char(string="Relay ID")
    name = fields.Char()
    street = fields.Char()
    zip = fields.Char(string="ZIP")
    city = fields.Char()
    distance = fields.Float(string="Distance (m)")

    def action_select(self):
        self.ensure_one()
        values = {
            "dpd_pickup_point_code": self.code,
            "dpd_pickup_point_name": self.name,
            "dpd_pickup_point_street": self.street,
            "dpd_pickup_point_zip": self.zip,
            "dpd_pickup_point_city": self.city,
        }
        target = self.wizard_id.picking_id or self.wizard_id.sale_id
        target.write(values)
        return {"type": "ir.actions.act_window_close"}
