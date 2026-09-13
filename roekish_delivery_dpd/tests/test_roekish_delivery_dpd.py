# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

CARRIER_MODULE = "odoo.addons.roekish_delivery_dpd.models.delivery_carrier"

PUDO_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<RESPONSE>
  <QUALITY>5</QUALITY>
  <REQUEST_ID>1</REQUEST_ID>
  <PUDO_ITEMS>
    <PUDO_ITEM active="true">
      <PUDO_ID>P12345</PUDO_ID>
      <NAME>TABAC DE LA GARE</NAME>
      <ADDRESS1>1 RUE DE LA GARE</ADDRESS1>
      <ADDRESS2></ADDRESS2>
      <ZIPCODE>69001</ZIPCODE>
      <CITY>LYON</CITY>
      <DISTANCE>210</DISTANCE>
    </PUDO_ITEM>
    <PUDO_ITEM active="true">
      <PUDO_ID>P12346</PUDO_ID>
      <NAME>EPICERIE DU MARCHE</NAME>
      <ADDRESS1>3 PLACE DU MARCHE</ADDRESS1>
      <ZIPCODE>69001</ZIPCODE>
      <CITY>LYON</CITY>
      <DISTANCE>640</DISTANCE>
    </PUDO_ITEM>
  </PUDO_ITEMS>
</RESPONSE>"""

PUDO_ERROR_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<RESPONSE>
  <REQUEST_ID>1</REQUEST_ID>
  <ERROR code="327">Personal security key is required and must be completed.</ERROR>
</RESPONSE>"""


class FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP %s" % self.status_code)


class TestDeliveryDpd(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.partner_id.write(
            {
                "street": "26 rue George Sand",
                "zip": "75016",
                "city": "Paris",
                "country_id": cls.env.ref("base.fr").id,
                "phone": "+33 1 23 45 67 89",
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "DPD", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "DPD Test",
                "delivery_type": "dpd",
                "product_id": cls.product.id,
                "dpd_product": "DPD_Classic",
                "dpd_customer_id": "123456",
                "dpd_agency_id": "077",
                "dpd_pricing_method": "grid",
            }
        )
        cls.relay_carrier = cls.env["delivery.carrier"].create(
            {
                "name": "DPD Relais Test",
                "delivery_type": "dpd",
                "product_id": cls.product.id,
                "dpd_product": "DPD_Relais",
                "dpd_customer_id": "123456",
                "dpd_agency_id": "077",
                "dpd_pricing_method": "grid",
            }
        )
        cls.predict_carrier = cls.env["delivery.carrier"].create(
            {
                "name": "DPD Predict Test",
                "delivery_type": "dpd",
                "product_id": cls.product.id,
                "dpd_product": "DPD_Predict",
                "dpd_customer_id": "123456",
                "dpd_agency_id": "077",
                "dpd_pricing_method": "grid",
            }
        )
        cls.env["delivery.dpd.tariff"].create(
            [
                {
                    "carrier_id": cls.carrier.id,
                    "zone": "FR",
                    "max_weight": 1.0,
                    "price": 6.55,
                },
                {
                    "carrier_id": cls.carrier.id,
                    "zone": "FR",
                    "max_weight": 5.0,
                    "price": 14.10,
                },
                {
                    "carrier_id": cls.carrier.id,
                    "zone": "EU1",
                    "max_weight": 2.0,
                    "price": 16.50,
                },
            ]
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _create_order(self, carrier, weight=1.2, partner_vals=None):
        """A confirmable sale order with one storable line."""
        vals = {
            "name": "Ship To",
            "street": "27 Rue Henri Rolland",
            "zip": "69100",
            "city": "Villeurbanne",
            "phone": "+33 6 12 34 56 78",
            "email": "shipto@example.com",
            "country_id": self.env.ref("base.fr").id,
        }
        vals.update(partner_vals or {})
        partner = self.env["res.partner"].create(vals)
        product = self.env["product.product"].create(
            {"name": "Boxed", "is_storable": True, "weight": weight}
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "carrier_id": carrier.id,
                "order_line": [
                    (0, 0, {"product_id": product.id, "product_uom_qty": 1})
                ],
            }
        )

    def _create_delivery(self, carrier, **kwargs):
        order = self._create_order(carrier, **kwargs)
        order.action_confirm()
        picking = order.picking_ids[:1]
        self.assertTrue(picking, "a delivery order should have been created")
        return picking

    # ------------------------------------------------------------------
    # zones and rating
    # ------------------------------------------------------------------
    def test_zone_mapping(self):
        get_zone = self.carrier._dpd_get_zone
        self.assertEqual(get_zone(self.env.ref("base.fr")), "FR")
        self.assertEqual(get_zone(self.env.ref("base.mc")), "FR")
        self.assertEqual(get_zone(self.env.ref("base.de")), "EU1")
        self.assertEqual(get_zone(self.env.ref("base.be")), "EU1")
        self.assertEqual(get_zone(self.env.ref("base.es")), "EU2")
        self.assertEqual(get_zone(self.env.ref("base.uk")), "EU2")
        self.assertEqual(get_zone(self.env.ref("base.us")), "INT")
        self.assertEqual(get_zone(self.env["res.country"]), "FR")

    def test_grid_rate_bracket(self):
        self.assertEqual(self.carrier._dpd_grid_rate("FR", 0.8), 6.55)
        self.assertEqual(self.carrier._dpd_grid_rate("FR", 3.0), 14.10)
        self.assertIsNone(self.carrier._dpd_grid_rate("FR", 40.0))
        self.assertIsNone(self.carrier._dpd_grid_rate("INT", 1.0))

    def test_rate_shipment_success(self):
        order = self._create_order(self.carrier)
        res = self.carrier.dpd_rate_shipment(order)
        self.assertTrue(res["success"])
        self.assertEqual(res["price"], 14.10)

    def test_rate_shipment_no_bracket(self):
        order = self._create_order(
            self.carrier, partner_vals={"country_id": self.env.ref("base.us").id}
        )
        res = self.carrier.dpd_rate_shipment(order)
        self.assertFalse(res["success"])
        self.assertTrue(res["error_message"])

    def test_rate_shipment_base_on_rule(self):
        carrier = self.env["delivery.carrier"].create(
            {
                "name": "DPD Rules",
                "delivery_type": "dpd",
                "product_id": self.product.id,
                "dpd_pricing_method": "base_on_rule",
                "price_rule_ids": [
                    (
                        0,
                        0,
                        {
                            "variable": "weight",
                            "operator": ">=",
                            "max_value": 0.0,
                            "list_base_price": 7.5,
                        },
                    )
                ],
            }
        )
        res = carrier.dpd_rate_shipment(self._create_order(carrier))
        self.assertTrue(res["success"])
        self.assertEqual(res["price"], 7.5)

    # ------------------------------------------------------------------
    # pickup relays
    # ------------------------------------------------------------------
    def test_is_pickup_compute(self):
        classic_order = self._create_order(self.carrier)
        relay_order = self._create_order(self.relay_carrier)
        self.assertFalse(classic_order.dpd_is_pickup)
        self.assertTrue(relay_order.dpd_is_pickup)

    def test_demo_pickup_points(self):
        # No Pickup key -> demonstrative relays, so the flow stays testable.
        points = self.carrier._dpd_search_pickup_points("75001", "Paris", "FR", 1.0)
        self.assertEqual(len(points), 3)
        self.assertEqual(points[0]["zip"], "75001")
        self.assertTrue(all(p.get("code") for p in points))

    def test_pickup_wizard_from_sale(self):
        order = self._create_order(
            self.relay_carrier, partner_vals={"zip": "69001", "city": "Lyon"}
        )
        wizard = (
            self.env["delivery.dpd.pickup.wizard"]
            .with_context(default_sale_id=order.id)
            .create({"zip": "69001"})
        )
        self.assertEqual(wizard.carrier_id, self.relay_carrier)
        wizard.action_search()
        self.assertTrue(wizard.line_ids)
        wizard.line_ids[0].action_select()
        self.assertTrue(order.dpd_pickup_point_code)
        self.assertEqual(order.dpd_pickup_point_city, "Lyon")

    def test_pickup_ws_as_plain_user_and_error_code(self):
        # A DPD *user* (not administrator) must be able to search relays even
        # though the key field is manager-only, and a MyPudo <ERROR> node must
        # surface as an error.
        user = self.env["res.users"].create(
            {
                "name": "Ops",
                "login": "ops_dpd",
                "group_ids": [
                    (6, 0, [self.env.ref("roekish_delivery_dpd.group_dpd_user").id])
                ],
            }
        )
        self.carrier.sudo().dpd_pudo_key = "k3y"
        carrier = self.carrier.with_user(user)
        with patch(CARRIER_MODULE + ".requests.get") as get:
            get.return_value = FakeResponse(PUDO_ERROR_XML)
            with self.assertRaises(UserError) as ctx:
                carrier._dpd_search_pickup_points("75001", "Paris", "FR", 1.0)
            self.assertIn("327", str(ctx.exception))

            get.return_value = FakeResponse(PUDO_XML)
            points = carrier._dpd_search_pickup_points("69001", "Lyon", "FR", 1.0)
        _, kwargs = get.call_args
        self.assertEqual(kwargs["params"]["key"], "k3y")
        self.assertEqual(kwargs["params"]["carrier"], "EXA")
        self.assertEqual(kwargs["params"]["zipCode"], "69001")
        self.assertEqual(kwargs["params"]["weight"], "1000")
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]["code"], "P12345")
        self.assertEqual(points[0]["street"], "1 RUE DE LA GARE")
        self.assertEqual(points[0]["distance"], 210.0)

    def test_pickup_propagates_to_delivery_on_confirm(self):
        order = self._create_order(self.relay_carrier)
        order.write(
            {
                "dpd_pickup_point_code": "P12345",
                "dpd_pickup_point_name": "Tabac Lyon",
                "dpd_pickup_point_city": "Lyon",
            }
        )
        order.action_confirm()
        picking = order.picking_ids[:1]
        self.assertEqual(picking.dpd_pickup_point_code, "P12345")
        self.assertEqual(picking.dpd_pickup_point_name, "Tabac Lyon")
        payload = self.relay_carrier._dpd_build_payload(picking)
        self.assertEqual(payload["service"]["pickupLocationId"], "P12345")
        self.assertEqual(payload["service"]["product"], "DPD_Relais")

    # ------------------------------------------------------------------
    # labels
    # ------------------------------------------------------------------
    def test_payload(self):
        self.carrier.sudo().write({"dpd_login": "user", "dpd_password": "pw"})
        picking = self._create_delivery(self.carrier)
        payload = self.carrier._dpd_build_payload(picking)
        self.assertEqual(
            payload["auth"], {"login": "user", "password": "pw", "isTest": False}
        )
        service = payload["service"]
        self.assertEqual(service["customerCountry"], "250")
        self.assertEqual(service["customerId"], "123456")
        self.assertEqual(service["agencyId"], "077")
        self.assertEqual(service["notifications"], "No")
        self.assertEqual(service["reference1"], picking.sale_id.name)
        self.assertNotIn("pickupLocationId", service)
        self.assertEqual(payload["parcels"][0]["weight"], 1.2)
        self.assertEqual(payload["from_address"]["phone"], "+33 1 23 45 67 89")
        self.assertEqual(payload["to_address"]["country"], "FR")

    def test_predict_forces_notification_and_requires_mobile(self):
        picking = self._create_delivery(self.predict_carrier)
        payload = self.predict_carrier._dpd_build_payload(picking)
        self.assertEqual(payload["service"]["notifications"], "Predict")
        picking = self._create_delivery(
            self.predict_carrier, partner_vals={"phone": "01 23 45 67 89"}
        )
        with self.assertRaises(UserError) as ctx:
            self.predict_carrier._dpd_build_payload(picking)
        self.assertIn("mobile", str(ctx.exception))

    def test_relais_requires_pickup_point(self):
        picking = self._create_delivery(self.relay_carrier)
        with self.assertRaises(UserError) as ctx:
            self.relay_carrier._dpd_build_payload(picking)
        self.assertIn("Pickup relay", str(ctx.exception))

    def test_send_shipping_mocked(self):
        # Prove label handling end to end against roulier's normalized output
        # (shape of the dpd_fr_soap decoder), no account.
        picking = self._create_delivery(self.carrier)
        fake_response = {
            "parcels": [
                {
                    "id": 1,
                    "reference": picking.name,
                    "tracking": {"number": "250123456789012", "url": "", "partner": ""},
                    "label": {
                        "data": base64.b64encode(b"%PDF-label").decode(),
                        "type": "PDF",
                        "name": "label 1",
                    },
                }
            ],
            "annexes": [],
        }
        with patch(CARRIER_MODULE + ".roulier") as roulier_mock:
            roulier_mock.get.return_value = fake_response
            result = self.carrier.dpd_send_shipping(picking)
        args, _ = roulier_mock.get.call_args
        self.assertEqual(args[0], "dpd_fr_soap")
        self.assertEqual(args[1], "get_label")
        self.assertEqual(result[0]["tracking_number"], "250123456789012")
        self.assertEqual(result[0]["exact_price"], 14.10)
        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", "stock.picking"), ("res_id", "=", picking.id)]
        )
        self.assertEqual(len(attachment), 1)
        self.assertTrue(attachment.name.endswith(".pdf"))

    def test_send_shipping_without_roulier_fails_closed(self):
        picking = self._create_delivery(self.carrier)
        with patch(CARRIER_MODULE + ".roulier", None):
            with self.assertRaises(UserError) as ctx:
                self.carrier.dpd_send_shipping(picking)
        self.assertIn("roulier", str(ctx.exception))

    def test_send_shipping_error_is_masked(self):
        self.carrier.sudo().write({"dpd_login": "user", "dpd_password": "S3cret!"})
        picking = self._create_delivery(self.carrier)
        with patch(CARRIER_MODULE + ".roulier") as roulier_mock:
            roulier_mock.get.side_effect = Exception(
                "Invalid credentials S3cret! <car:password>S3cret!</car:password>"
            )
            with self.assertRaises(UserError) as ctx:
                self.carrier.dpd_send_shipping(picking)
        message = str(ctx.exception)
        self.assertIn("DPD rejected", message)
        self.assertNotIn("S3cret!", message)

    # ------------------------------------------------------------------
    # fail-closed guards
    # ------------------------------------------------------------------
    def test_check_shipment_rejects_zero_weight(self):
        picking = self._create_delivery(self.carrier, weight=0.0)
        with self.assertRaises(UserError) as ctx:
            self.carrier._dpd_check_shipment(picking)
        self.assertIn("weight", str(ctx.exception))

    def test_check_shipment_rejects_incomplete_address(self):
        picking = self._create_delivery(
            self.carrier, partner_vals={"zip": False, "city": False}
        )
        with self.assertRaises(UserError) as ctx:
            self.carrier._dpd_check_shipment(picking)
        self.assertIn("incomplete", str(ctx.exception))

    def test_check_shipment_requires_contract_and_sender_phone(self):
        picking = self._create_delivery(self.carrier)
        self.carrier.dpd_agency_id = False
        with self.assertRaises(UserError) as ctx:
            self.carrier._dpd_check_shipment(picking)
        self.assertIn("agency code", str(ctx.exception))
        self.carrier.dpd_agency_id = "077"
        self.env.company.partner_id.phone = False
        with self.assertRaises(UserError) as ctx:
            self.carrier._dpd_check_shipment(picking)
        self.assertIn("phone", str(ctx.exception))

    def test_payload_falls_back_to_env_company(self):
        # A shared carrier (no company) must still send a sender address.
        self.carrier.company_id = False
        picking = self._create_delivery(self.carrier)
        payload = self.carrier._dpd_build_payload(picking)
        self.assertEqual(
            payload["from_address"]["name"], self.env.company.partner_id.name
        )

    # ------------------------------------------------------------------
    # tracking, cancellation, secrets, connection test
    # ------------------------------------------------------------------
    def test_tracking_link_uses_first_reference(self):
        picking = self.env["stock.picking"].new(
            {"carrier_tracking_ref": "250111, 250222"}
        )
        link = self.carrier.dpd_get_tracking_link(picking)
        self.assertIn("trace.dpd.fr/fr/trace/250111", link)
        self.assertNotIn("250222", link)

    def test_cancel_shipment_clears_reference(self):
        picking = self._create_delivery(self.carrier)
        picking.carrier_tracking_ref = "250111"
        self.carrier.dpd_cancel_shipment(picking)
        self.assertFalse(picking.carrier_tracking_ref)

    def test_mask_secrets(self):
        self.carrier.sudo().write({"dpd_password": "S3cret!", "dpd_pudo_key": "k3y"})
        masked = self.carrier._dpd_mask_secrets(
            "pw=S3cret! key=k3y <password>S3cret!</password>"
        )
        self.assertNotIn("S3cret!", masked)
        self.assertNotIn("k3y", masked)
        self.assertIn("<password>****</password>", masked)

    def test_test_connection_requires_credentials(self):
        with self.assertRaises(UserError):
            self.carrier.action_dpd_test_connection()
        self.carrier.sudo().write({"dpd_login": "user", "dpd_password": "pw"})
        with self.assertRaises(UserError) as ctx:
            self.carrier.action_dpd_test_connection()
        self.assertIn("Pickup", str(ctx.exception))

    def test_test_connection(self):
        self.carrier.sudo().write(
            {"dpd_login": "user", "dpd_password": "pw", "dpd_pudo_key": "k3y"}
        )
        with patch(CARRIER_MODULE + ".requests.get") as get:
            get.return_value = FakeResponse(PUDO_XML)
            action = self.carrier.action_dpd_test_connection()
        self.assertIn("2", action["params"]["message"])
