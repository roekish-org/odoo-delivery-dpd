# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "delivery.dpd.pickup.mixin"]
