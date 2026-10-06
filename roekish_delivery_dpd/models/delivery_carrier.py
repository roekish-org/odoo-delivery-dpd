# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
import logging
import re

import requests
from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .demo_label import (
    demo_tracking_number,
    is_demo_tracking,
    partner_lines,
    render_demo_label,
)

_logger = logging.getLogger(__name__)

try:
    from roulier import roulier
except ImportError:  # pragma: no cover - roulier is an optional dependency
    roulier = None
    _logger.debug("Cannot `import roulier`; DPD label generation disabled.")

# roulier carrier id and action used for DPD France labels (e-Station SOAP
# web service, "eprintwebservice").
ROULIER_CARRIER = "dpd_fr_soap"
ROULIER_LABEL_ACTION = "get_label"
# DPD France "Pickup" relay network web service (MyPudo), queried over HTTP GET.
PICKUP_URL = "https://mypudo.pickup-services.com/mypudo/mypudo.asmx/GetPudoList"
PICKUP_TIMEOUT = 30
# ISO 3166-1 numeric code of France, expected by e-Station as customer country.
DPD_CUSTOMER_COUNTRY = "250"
# Customer number as printed on DPD contracts: "21260" or "238-21260"
# (agency code, dash, customer number).
CUSTOMER_RE = re.compile(r"^(?:(\d+)-)?(\d+)$")
# DPD Predict notifies the recipient by SMS: a mobile number is required.
MOBILE_RE = re.compile(r"^(?:\+336|\+337|00336|00337|06|07)\d{8}$")

# ISO alpha-2 country sets used to map a destination to a DPD zone, following the
# DPD France "Zoning Europe" printed on its 2026 contracts (Euro 1 to Euro 5).
FR_COUNTRY_CODES = {"FR", "MC"}
EU1_COUNTRY_CODES = {"BE", "DE", "LU", "NL"}
EU2_COUNTRY_CODES = {"AT", "CH", "CZ", "ES", "GB", "IT", "LI", "PL", "PT"}
EU3_COUNTRY_CODES = {"AD", "DK", "EE", "HR", "HU", "IE", "LT", "LV", "SE", "SI", "SK"}
EU4_COUNTRY_CODES = {"BG", "FI", "GR", "NO", "RO"}
EU5_COUNTRY_CODES = {"BA", "RS"}
# Grids written before Euro 3-5 existed priced those countries as Euro 2: a zone
# without any line of its own falls back to these.
ZONE_FALLBACK = {"EU3": "EU2", "EU4": "EU2", "EU5": "EU2"}


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("dpd", "DPD France")],
        ondelete={"dpd": "set default"},
    )
    dpd_login = fields.Char(
        string="e-Station login",
        groups="roekish_delivery_dpd.group_dpd_manager",
        help="User id of the DPD France e-Station web service account.",
    )
    dpd_password = fields.Char(
        string="e-Station password",
        groups="roekish_delivery_dpd.group_dpd_manager",
        help="Password of the DPD France e-Station web service account. "
        "Readable only by DPD administrators.",
    )
    dpd_customer_id = fields.Char(
        string="Customer number",
        help="DPD France customer number printed on your contract, e.g. 21260 "
        "or 238-21260 (agency code, dash, customer number).",
    )
    dpd_agency_id = fields.Char(
        string="Agency code",
        help="Code of the DPD France agency collecting your parcels (3 digits).",
    )
    dpd_test_mode = fields.Boolean(
        string="Test environment",
        help="Send label requests to the e-Station test environment instead "
        "of production.",
    )
    dpd_demo_label = fields.Boolean(
        string="Demo labels",
        help="Generate a specimen PDF label with a fake DEMO tracking number "
        "instead of calling DPD: no shipment is created and nothing is "
        "billed. For demonstrations and training only; untick before "
        "shipping real parcels.",
    )
    dpd_pudo_key = fields.Char(
        string="Pickup search key",
        groups="roekish_delivery_dpd.group_dpd_manager",
        help="Key of the DPD France Pickup (MyPudo) relay search web service. "
        "DPD does not issue one per contract: use the key shipped with DPD "
        "France's official e-commerce modules, or ask your DPD agency. "
        "Required to list real Pickup relays. Readable only by DPD "
        "administrators.",
    )
    dpd_pudo_carrier = fields.Char(
        string="Pickup carrier code",
        default="EXA",
        help="Carrier code sent to the Pickup relay search (EXA for DPD France).",
    )
    dpd_product = fields.Selection(
        selection=[
            ("DPD_Classic", "DPD CLASSIC (business delivery)"),
            ("DPD_Predict", "DPD Predict (home delivery, SMS time slot)"),
            ("DPD_Relais", "DPD Relais (Pickup relay delivery)"),
        ],
        string="DPD product",
        default="DPD_Classic",
        help="DPD France product sent to the label web service.",
    )
    dpd_notifications = fields.Selection(
        selection=[
            ("No", "None"),
            ("AutomaticSMS", "Automatic SMS"),
            ("AutomaticMail", "Automatic email"),
        ],
        string="Recipient notification",
        default="No",
        help="Notification requested from DPD for CLASSIC and Relais parcels. "
        "Predict parcels always use the Predict SMS notification.",
    )
    dpd_label_format = fields.Selection(
        selection=[
            ("PDF", "PDF"),
            ("PDF_A6", "PDF A6"),
            ("ZPL", "ZPL (label printer)"),
            ("PNG", "PNG"),
        ],
        string="Label format",
        default="PDF",
    )
    dpd_pricing_method = fields.Selection(
        selection=[
            ("grid", "DPD tariff grid"),
            ("base_on_rule", "Odoo pricing rules"),
        ],
        string="Pricing method",
        default="grid",
        help="How the delivery price is computed:\n"
        "- DPD tariff grid: weight x destination zone lines defined on this "
        "carrier.\n"
        "- Odoo pricing rules: the standard rule-based pricing engine.",
    )
    dpd_fuel_surcharge = fields.Float(
        string="Fuel surcharge (%)",
        help="Percentage added to the tariff grid price (DPD bills it at the foot "
        "of the invoice). Grid pricing only.",
    )
    dpd_parcel_fee = fields.Float(
        string="Fixed fees per parcel",
        help="Amount added to every parcel after the fuel surcharge, e.g. the "
        "security contribution and the responsible logistics contribution of "
        "your contract. Grid pricing only.",
    )
    dpd_volumetric_divisor = fields.Integer(
        string="Volumetric divisor",
        help="When set (DPD uses 5000), the billed weight is the greater of the "
        "real weight and the volumetric weight: volume in cm3 / divisor, from the "
        "product volumes. Leave 0 when your contract does not apply volumetric "
        "billing.",
    )
    dpd_tariff_ids = fields.One2many(
        "delivery.dpd.tariff",
        "carrier_id",
        string="DPD tariff grid",
    )
    dpd_delay_min = fields.Integer(
        string="Delivery days min",
        help="Shortest delivery time announced by DPD, in working days "
        "after hand-over. Applies to every destination unless a tariff grid "
        "line overrides it. Leave 0 when unknown.",
    )
    dpd_delay_max = fields.Integer(
        string="Delivery days max",
        help="Longest delivery time announced by DPD, in working days "
        "after hand-over. Applies to every destination unless a tariff grid "
        "line overrides it. Leave 0 when unknown.",
    )

    @api.constrains("dpd_customer_id", "dpd_agency_id")
    def _check_dpd_contract_numbers(self):
        # e-Station reads the agency code and the customer number as two
        # integers and rejects anything else with an opaque "Input string
        # was not in a correct format" SOAP fault.
        for carrier in self:
            customer = (carrier.dpd_customer_id or "").strip()
            agency = (carrier.dpd_agency_id or "").strip()
            match = CUSTOMER_RE.match(customer)
            if customer and not match:
                raise ValidationError(
                    self.env._(
                        "The DPD customer number must look like 21260 or "
                        "238-21260, as printed on your contract (got "
                        "'%s').",
                        customer,
                    )
                )
            if agency and not agency.isdigit():
                raise ValidationError(
                    self.env._(
                        "The DPD agency code must contain digits only (got " "'%s').",
                        agency,
                    )
                )
            if match and match.group(1) and agency and match.group(1) != agency:
                raise ValidationError(
                    self.env._(
                        "The agency code %(agency)s does not match the one in "
                        "customer number %(customer)s.",
                        agency=agency,
                        customer=customer,
                    )
                )

    def _dpd_contract_numbers(self):
        """Return (agency code, customer number) as sent to e-Station.

        "238-21260" carries the agency code: it fills an empty agency field.
        """
        self.ensure_one()
        agency = (self.dpd_agency_id or "").strip()
        match = CUSTOMER_RE.match((self.dpd_customer_id or "").strip())
        if not match:
            return agency, ""
        return agency or match.group(1) or "", match.group(2)

    # ------------------------------------------------------------------
    # Rating
    # ------------------------------------------------------------------
    def dpd_rate_shipment(self, order):
        """Return a delivery quote for ``order`` (sale.order).

        On success the dict also carries ``delay_min`` and ``delay_max``
        (working days, 0 when unknown) so carriers can be compared on cost
        and speed. See ``_dpd_with_delay``.
        """
        self.ensure_one()
        zone = self._dpd_get_zone(order.partner_shipping_id.country_id)
        weight = self._dpd_billed_weight(order)
        # Extension point for a live DPD rating endpoint. DPD France exposes
        # none, so this returns None and we fall back to the configured
        # pricing method. Any override MUST fail closed (return None) when
        # the endpoint is unavailable.
        price = self._dpd_get_live_price(order)
        if price is None and self.dpd_pricing_method == "base_on_rule":
            return self._dpd_with_delay(
                self.base_on_rule_rate_shipment(order), zone, weight
            )
        if price is None:
            price = self._dpd_grid_rate(zone, weight)
            if price is not None:
                price = self._dpd_apply_surcharges(price)
        if price is None:
            return {
                "success": False,
                "price": 0.0,
                "error_message": self.env._(
                    "No DPD tariff matches this destination and weight. "
                    "Add a matching line to the tariff grid of carrier '%s'.",
                    self.name,
                ),
                "warning_message": False,
            }
        return self._dpd_with_delay(
            {
                "success": True,
                "price": price,
                "error_message": False,
                "warning_message": False,
            },
            zone,
            weight,
        )

    def _dpd_billed_weight(self, order):
        """Real weight, or the volumetric weight when greater and enabled."""
        self.ensure_one()
        weight = order._get_estimated_weight()
        if self.dpd_volumetric_divisor > 0:
            volume_m3 = sum(
                line.product_id.volume * line.product_uom_qty
                for line in order.order_line
                if line.product_id and not line.is_delivery
            )
            weight = max(weight, volume_m3 * 1_000_000 / self.dpd_volumetric_divisor)
        return weight

    def _dpd_apply_surcharges(self, price):
        """Grid price + fuel surcharge (%) + fixed fees per parcel."""
        self.ensure_one()
        price = price * (1 + (self.dpd_fuel_surcharge or 0.0) / 100.0)
        return self.env.company.currency_id.round(price + (self.dpd_parcel_fee or 0.0))

    def _dpd_get_live_price(self, order):
        """Hook for a future DPD live-pricing web call.

        DPD France does not expose a rating API today, so this returns None
        and pricing falls back to the tariff grid or Odoo rules. Override to
        plug a real endpoint; keep it fail-closed.
        """
        return None

    def _dpd_grid_line(self, zone, weight):
        """Return the first tariff grid line covering ``zone`` and ``weight``.

        A Euro 3-5 zone with no line at all uses the Euro 2 lines (grids made
        before those zones existed)."""
        self.ensure_one()
        Tariff = self.env["delivery.dpd.tariff"]
        if not zone:
            return Tariff
        if zone in ZONE_FALLBACK and not Tariff.search_count(
            [("carrier_id", "=", self.id), ("zone", "=", zone)], limit=1
        ):
            zone = ZONE_FALLBACK[zone]
        return Tariff.search(
            [
                ("carrier_id", "=", self.id),
                ("zone", "=", zone),
                ("max_weight", ">=", weight),
            ],
            order="max_weight asc",
            limit=1,
        )

    def _dpd_grid_rate(self, zone, weight):
        """Look up the price for ``zone`` and ``weight`` in the tariff grid.

        Returns the price (company currency) or None when no bracket matches.
        """
        line = self._dpd_grid_line(zone, weight)
        return line.price if line else None

    def _dpd_get_delay(self, zone, weight):
        """Announced delivery time for a shipment, as (min, max) working days.

        The tariff grid line covering the shipment overrides the carrier
        values; 0 means unknown.
        """
        self.ensure_one()
        line = self.env["delivery.dpd.tariff"]
        if self.dpd_pricing_method == "grid":
            line = self._dpd_grid_line(zone, weight)
        return (
            line.delay_min or self.dpd_delay_min,
            line.delay_max or self.dpd_delay_max,
        )

    def _dpd_with_delay(self, res, zone, weight):
        """Add the delivery time to a successful quote.

        ``delay_min`` / ``delay_max`` (working days, 0 = unknown) let a caller
        compare carriers on cost and speed. The readable sentence rides
        ``warning_message``, which the shipping wizard displays and the sale
        order stores as ``delivery_message``; an existing warning is kept.
        """
        if not res.get("success"):
            return res
        delay_min, delay_max = self._dpd_get_delay(zone, weight)
        res.update(delay_min=delay_min, delay_max=delay_max)
        if not res.get("warning_message"):
            res["warning_message"] = self._dpd_delay_message(delay_min, delay_max)
        return res

    @api.model
    def _dpd_delay_message(self, delay_min, delay_max):
        """Human-readable delivery time, False when unknown."""
        if delay_min and delay_max and delay_min != delay_max:
            return self.env._(
                "Delivery in %(min)s to %(max)s working days.",
                min=delay_min,
                max=delay_max,
            )
        days = delay_max or delay_min
        if days == 1:
            return self.env._("Delivery in 1 working day.")
        if days:
            return self.env._("Delivery in %s working days.", days)
        return False

    @api.model
    def _dpd_get_zone(self, country):
        """Map a destination country to a DPD pricing zone."""
        code = country.code if country else None
        if not code or code in FR_COUNTRY_CODES:
            return "FR"
        if code in EU1_COUNTRY_CODES:
            return "EU1"
        for zone, codes in (
            ("EU2", EU2_COUNTRY_CODES),
            ("EU3", EU3_COUNTRY_CODES),
            ("EU4", EU4_COUNTRY_CODES),
            ("EU5", EU5_COUNTRY_CODES),
        ):
            if code in codes:
                return zone
        return "INT"

    # ------------------------------------------------------------------
    # Shipping (label generation)
    # ------------------------------------------------------------------
    def dpd_send_shipping(self, pickings):
        """Generate a DPD label for each picking."""
        self.ensure_one()
        return [self._dpd_send_one(picking) for picking in pickings]

    def _dpd_send_one(self, picking):
        self.ensure_one()
        if self.dpd_demo_label:
            self._dpd_check_shipment(picking)
            return self._dpd_send_demo(picking)
        if roulier is None:
            raise UserError(
                self.env._(
                    "The Python library 'roulier' is required to generate "
                    "DPD labels. Install it with: pip install roulier"
                )
            )
        payload = self._dpd_build_payload(picking)
        try:
            result = roulier.get(ROULIER_CARRIER, ROULIER_LABEL_ACTION, payload)
        except Exception as exc:
            _logger.exception("DPD label generation failed")
            raise UserError(
                self.env._(
                    "DPD rejected the shipment for %(picking)s:\n%(error)s",
                    picking=picking.name,
                    error=self._dpd_mask_secrets(str(exc)),
                )
            ) from exc

        tracking_number = self._dpd_attach_labels(picking, result)
        return {
            "exact_price": self._dpd_price_for_picking(picking),
            "tracking_number": tracking_number or False,
        }

    def _dpd_send_demo(self, picking):
        """Attach a specimen label instead of calling DPD.

        The shipment data is still validated by the caller, only the
        carrier call is skipped.
        """
        self.ensure_one()
        tracking = demo_tracking_number(picking)
        company = self.company_id or self.env.company
        weight = picking.shipping_weight or picking.weight or 0.0
        details = [
            self.env._("Weight: %s kg", round(weight, 3)),
            self.env._(
                "Reference: %s",
                picking.sale_id.name or picking.origin or picking.name,
            ),
        ]
        if self.dpd_product == "DPD_Relais":
            details.append(
                self.env._("Pickup relay: %s", picking.dpd_pickup_point_code)
            )
        product = dict(
            self._fields["dpd_product"]._description_selection(self.env)
        ).get(self.dpd_product, "")
        pdf = render_demo_label(
            heading=self.env._("DEMO LABEL - NOT VALID FOR SHIPPING"),
            watermark=self.env._("SPECIMEN"),
            carrier="%s - %s" % (self.name, product),
            sections=[
                (self.env._("From"), partner_lines(company.partner_id)),
                (self.env._("To"), partner_lines(picking.partner_id)),
                (self.env._("Shipment"), details),
            ],
            tracking=tracking,
            footer=self.env._("Demo mode: no shipment was created at the carrier."),
        )
        picking.message_post(
            body=self.env._("Demo label %s: no shipment was created at DPD.", tracking),
            attachments=[
                ("%s_%s.pdf" % (picking.name.replace("/", "_"), tracking), pdf)
            ],
        )
        return {
            "exact_price": self._dpd_price_for_picking(picking),
            "tracking_number": tracking,
        }

    def _dpd_attach_labels(self, picking, result):
        """Attach every returned label to the picking, return 1st tracking."""
        parcels = result.get("parcels") or []
        tracking_numbers = []
        for parcel in parcels:
            tracking = (parcel.get("tracking") or {}).get("number")
            if tracking:
                tracking_numbers.append(tracking)
            label = parcel.get("label") or {}
            data = label.get("data")
            if not data:
                continue
            filename = "%s_%s.%s" % (
                picking.name.replace("/", "_"),
                tracking or parcel.get("id", ""),
                (label.get("type") or "pdf").lower().replace("pdf_a6", "pdf"),
            )
            picking.message_post(
                body=self.env._("DPD label %s", tracking or ""),
                attachments=[(filename, base64.b64decode(data))],
            )
        # e-Station also returns the shipment summary (EPRINTATTACHMENT).
        base = picking.name.replace("/", "_")
        attachments = [
            (
                "%s_summary_%s.%s"
                % (
                    base,
                    index,
                    (annex.get("type") or "pdf").lower().replace("pdf_a6", "pdf"),
                ),
                base64.b64decode(annex["data"]),
            )
            for index, annex in enumerate(result.get("annexes") or [], 1)
            if annex.get("data")
        ]
        if attachments:
            picking.message_post(
                body=self.env._("DPD shipment summary"),
                attachments=attachments,
            )
        return ",".join(tracking_numbers)

    def _dpd_price_for_picking(self, picking):
        """Best-effort delivery price for the confirmation of a shipment."""
        self.ensure_one()
        zone = self._dpd_get_zone(picking.partner_id.country_id)
        weight = picking.shipping_weight or picking.weight or 0.0
        price = self._dpd_grid_rate(zone, weight)
        return price if price is not None else 0.0

    def _dpd_build_payload(self, picking):
        """Build the roulier payload for one picking.

        The exact schema is validated by roulier at call time against the
        installed library version; keys below follow the dpd_fr_soap encoder.
        """
        self.ensure_one()
        self._dpd_check_shipment(picking)
        # Credentials are manager-only fields; read them with sudo so the
        # label flow works for any user allowed to ship. They never leave
        # the server.
        creds = self.sudo()
        company = self.company_id or self.env.company
        weight = picking.shipping_weight or picking.weight or 0.0
        agency_id, customer_id = self._dpd_contract_numbers()
        service = {
            "product": self.dpd_product,
            "labelFormat": self.dpd_label_format,
            "shippingDate": fields.Date.context_today(picking),
            "customerCountry": DPD_CUSTOMER_COUNTRY,
            "customerId": customer_id,
            "agencyId": agency_id,
            "notifications": (
                "Predict"
                if self.dpd_product == "DPD_Predict"
                else self.dpd_notifications
            ),
            "reference1": picking.sale_id.name or picking.origin or picking.name,
            "reference2": picking.name,
        }
        if self.dpd_product == "DPD_Relais":
            service["pickupLocationId"] = picking.dpd_pickup_point_code
        return {
            "auth": {
                "login": creds.dpd_login or "",
                "password": creds.dpd_password or "",
                "isTest": bool(self.dpd_test_mode),
            },
            "service": service,
            "parcels": [{"weight": weight, "reference": picking.name}],
            "from_address": self._dpd_convert_address(company.partner_id),
            "to_address": self._dpd_convert_address(picking.partner_id),
        }

    def _dpd_check_shipment(self, picking):
        """Fail closed, with a clear message, before calling DPD.

        e-Station rejects zero-weight parcels, incomplete addresses, Relais
        parcels without a relay and Predict parcels without a mobile number
        with opaque codes, so validate the obvious cases up front.
        """
        weight = picking.shipping_weight or picking.weight or 0.0
        if weight <= 0:
            raise UserError(
                self.env._(
                    "Set a shipping weight on %s before generating a DPD label.",
                    picking.name,
                )
            )
        if not self.dpd_demo_label and not all(self._dpd_contract_numbers()):
            raise UserError(
                self.env._(
                    "Fill the DPD customer number and agency code on carrier "
                    "'%s' before generating labels.",
                    self.name,
                )
            )
        partner = picking.partner_id
        missing = [
            partner._fields[name].string
            for name in ("street", "zip", "city", "country_id")
            if not partner[name]
        ]
        if missing:
            raise UserError(
                self.env._(
                    "The delivery address of %(picking)s is incomplete "
                    "(missing: %(fields)s).",
                    picking=picking.name,
                    fields=", ".join(missing),
                )
            )
        if self.dpd_product == "DPD_Relais" and not picking.dpd_pickup_point_code:
            raise UserError(
                self.env._(
                    "Choose a Pickup relay on %s before generating a DPD "
                    "Relais label.",
                    picking.name,
                )
            )
        if self.dpd_product == "DPD_Predict":
            mobile = re.sub(r"[\s.\-()]", "", partner.phone or "")
            if not MOBILE_RE.match(mobile):
                raise UserError(
                    self.env._(
                        "DPD Predict requires a French mobile number on the "
                        "recipient %s (06..., 07..., +336... or +337...).",
                        partner.display_name,
                    )
                )
        company = self.company_id or self.env.company
        if not company.partner_id.phone:
            raise UserError(
                self.env._(
                    "DPD requires a phone number on the sender: set it on "
                    "company %s.",
                    company.name,
                )
            )

    def _dpd_mask_secrets(self, text):
        """Redact the account password and Pickup key from any message."""
        self.ensure_one()
        if not text:
            return text
        creds = self.sudo()
        for secret in (creds.dpd_password, creds.dpd_pudo_key):
            if secret:
                text = text.replace(secret, "****")
        # Also redact a <password>...</password> XML node, if echoed back.
        return re.sub(
            r"(<(?:car:)?password>).*?(</(?:car:)?password>)",
            r"\1****\2",
            text,
            flags=re.DOTALL,
        )

    @api.model
    def _dpd_convert_address(self, partner):
        """Convert a res.partner to the address dict roulier expects."""
        return {
            "company": partner.commercial_company_name or "",
            "name": partner.name or "",
            "street1": partner.street or "",
            "street2": partner.street2 or "",
            "city": partner.city or "",
            "zip": partner.zip or "",
            "country": partner.country_id.code or "",
            "phone": partner.phone or "",
            "email": partner.email or "",
        }

    # ------------------------------------------------------------------
    # Connectivity test (go-live check)
    # ------------------------------------------------------------------
    def action_dpd_test_connection(self):
        """Ping DPD with the configured credentials.

        With a Pickup key, checks that it is accepted, using the company
        address as a non-destructive relay query. The key is optional.
        Label credentials themselves can only be validated by generating a
        label (use the test environment for that).
        """
        self.ensure_one()
        creds = self.sudo()
        if not (creds.dpd_login and creds.dpd_password):
            raise UserError(
                self.env._(
                    "Fill the e-Station login and password before testing "
                    "the connection."
                )
            )
        if not creds.dpd_pudo_key:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("DPD"),
                    "message": self.env._(
                        "No Pickup search key: relay search is off, type relay "
                        "IDs by hand. Labels are checked on the first "
                        "shipment (use the test environment)."
                    ),
                    "type": "info",
                    "sticky": False,
                },
            }
        company_partner = (self.company_id or self.env.company).partner_id
        points = self._dpd_call_pickup_ws(
            company_partner.zip or "75001",
            company_partner.city or "Paris",
            company_partner.country_id.code or "FR",
            1.0,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("DPD"),
                "message": self.env._(
                    "Connection successful, %s Pickup relays returned.",
                    len(points),
                ),
                "type": "success",
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    # Pickup relays
    # ------------------------------------------------------------------
    def _dpd_search_pickup_points(self, zipcode, city, country_code, weight):
        """Return a list of Pickup relays near ``zipcode``.

        Each item is a dict: code, name, street, zip, city, distance.
        With demo labels on, demonstrative relays are returned so a demo
        never calls DPD. Otherwise the live web service is queried, which
        needs the Pickup key: fake relays would be refused on a real label.
        """
        self.ensure_one()
        if self.dpd_demo_label:
            return self._dpd_demo_pickup_points(zipcode, city)
        if not self.sudo().dpd_pudo_key:
            raise UserError(
                self.env._(
                    "No Pickup search key on carrier '%s': relay search is "
                    "unavailable. Type the relay ID directly in the Pickup "
                    "relay ID field (find it on dpd.fr, 'Trouver un relais').",
                    self.name,
                )
            )
        return self._dpd_call_pickup_ws(zipcode, city, country_code, weight)

    def _dpd_call_pickup_ws(self, zipcode, city, country_code, weight):
        self.ensure_one()
        creds = self.sudo()
        today = fields.Date.context_today(self)
        params = {
            "carrier": self.dpd_pudo_carrier or "EXA",
            "key": creds.dpd_pudo_key or "",
            "address": "",
            "zipCode": zipcode or "",
            "city": city or "",
            "countrycode": country_code or "FR",
            "requestID": str(self.id),
            "date_from": today.strftime("%d/%m/%Y"),
            "max_pudo_number": "10",
            "max_distance_search": "",
            "weight": str(int((weight or 0) * 1000)) if weight else "",
            "category": "",
            "holiday_tolerant": "",
        }
        try:
            response = requests.get(PICKUP_URL, params=params, timeout=PICKUP_TIMEOUT)
            response.raise_for_status()
            root = etree.fromstring(response.content)
        except Exception as exc:
            _logger.exception("DPD Pickup search failed")
            raise UserError(
                self.env._(
                    "DPD Pickup search failed:\n%s",
                    self._dpd_mask_secrets(str(exc)),
                )
            ) from exc
        # MyPudo answers HTTP 200 with an <ERROR code="..."> node on a bad
        # key or bad input, so it must be checked explicitly.
        error = root.find("ERROR")
        if error is not None:
            raise UserError(
                self.env._(
                    "DPD refused the Pickup search (code %(code)s): %(msg)s",
                    code=error.get("code", ""),
                    msg=self._dpd_mask_secrets(error.text or ""),
                )
            )
        points = []
        for item in root.iterfind("PUDO_ITEMS/PUDO_ITEM"):
            points.append(
                {
                    "code": item.findtext("PUDO_ID", "") or "",
                    "name": item.findtext("NAME", "") or "",
                    "street": item.findtext("ADDRESS1", "") or "",
                    "zip": item.findtext("ZIPCODE", "") or "",
                    "city": item.findtext("CITY", "") or "",
                    "distance": float(item.findtext("DISTANCE", "0") or 0),
                }
            )
        return points

    @api.model
    def _dpd_demo_pickup_points(self, zipcode, city):
        zipcode = zipcode or "75001"
        city = city or "Paris"
        return [
            {
                "code": "P10001",
                "name": "Pickup Tabac Presse %s" % city,
                "street": "1 rue de la Gare",
                "zip": zipcode,
                "city": city,
                "distance": 150.0,
            },
            {
                "code": "P10002",
                "name": "Pickup Epicerie %s" % city,
                "street": "12 avenue des Colis",
                "zip": zipcode,
                "city": city,
                "distance": 380.0,
            },
            {
                "code": "P10003",
                "name": "Pickup Station consigne",
                "street": "3 place du Marche",
                "zip": zipcode,
                "city": city,
                "distance": 610.0,
            },
        ]

    # ------------------------------------------------------------------
    # Tracking & cancellation
    # ------------------------------------------------------------------
    def dpd_get_tracking_link(self, picking):
        self.ensure_one()
        ref = (picking.carrier_tracking_ref or "").split(",")[0].strip()
        if is_demo_tracking(ref):
            return False
        return "https://trace.dpd.fr/fr/trace/%s" % ref

    def dpd_cancel_shipment(self, pickings):
        """Clear the tracking reference.

        e-Station exposes no label-cancellation web service: an unused label
        is simply never scanned. Reset Odoo state and remind the user.
        """
        self.ensure_one()
        for picking in pickings:
            picking.message_post(
                body=self.env._(
                    "DPD tracking reference cleared in Odoo. If the parcel "
                    "was already handed over, contact your DPD agency."
                )
            )
            picking.carrier_tracking_ref = False
        return True
