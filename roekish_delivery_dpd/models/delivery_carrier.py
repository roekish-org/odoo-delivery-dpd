# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
import logging
import re

import requests
from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError

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
# DPD Predict notifies the recipient by SMS: a mobile number is required.
MOBILE_RE = re.compile(r"^(?:\+336|\+337|00336|00337|06|07)\d{8}$")

# ISO alpha-2 country sets used to map a destination to a DPD zone.
FR_COUNTRY_CODES = {"FR", "MC"}
# DPD CLASSIC Europe zone 1: the direct road neighbours.
EU1_COUNTRY_CODES = {"BE", "DE", "LU", "NL"}
# DPD CLASSIC Europe zone 2: the rest of the European road network.
EU2_COUNTRY_CODES = {
    "AT",
    "BG",
    "HR",
    "CY",
    "CZ",
    "DK",
    "EE",
    "FI",
    "GR",
    "HU",
    "IE",
    "IT",
    "LV",
    "LT",
    "MT",
    "PL",
    "PT",
    "RO",
    "SK",
    "SI",
    "ES",
    "SE",
    "GB",
    "CH",
    "NO",
    "LI",
    "IS",
    "AD",
}


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
        help="DPD France customer number (6 digits) printed on your contract.",
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
    dpd_pudo_key = fields.Char(
        string="Pickup search key",
        groups="roekish_delivery_dpd.group_dpd_manager",
        help="Key of the DPD France Pickup (MyPudo) relay search web service, "
        "provided with your DPD Relais contract. Readable only by DPD "
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
        weight = order._get_estimated_weight()
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

    def _dpd_get_live_price(self, order):
        """Hook for a future DPD live-pricing web call.

        DPD France does not expose a rating API today, so this returns None
        and pricing falls back to the tariff grid or Odoo rules. Override to
        plug a real endpoint; keep it fail-closed.
        """
        return None

    def _dpd_grid_line(self, zone, weight):
        """Return the first tariff grid line covering ``zone`` and ``weight``."""
        self.ensure_one()
        if not zone:
            return self.env["delivery.dpd.tariff"]
        return self.env["delivery.dpd.tariff"].search(
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
        if code in EU2_COUNTRY_CODES:
            return "EU2"
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
        service = {
            "product": self.dpd_product,
            "labelFormat": self.dpd_label_format,
            "shippingDate": fields.Date.context_today(picking),
            "customerCountry": DPD_CUSTOMER_COUNTRY,
            "customerId": self.dpd_customer_id or "",
            "agencyId": self.dpd_agency_id or "",
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
        if not (self.dpd_customer_id and self.dpd_agency_id):
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

        Checks that the e-Station endpoint answers and that the Pickup key
        is accepted, using the company address as a non-destructive query.
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
            raise UserError(
                self.env._("Fill the Pickup search key before testing the connection.")
            )
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
        When a Pickup key is set, the live DPD web service is queried;
        otherwise demonstrative relays are returned so the flow stays
        testable without an account.
        """
        self.ensure_one()
        if self.sudo().dpd_pudo_key:
            return self._dpd_call_pickup_ws(zipcode, city, country_code, weight)
        return self._dpd_demo_pickup_points(zipcode, city)

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
