===========================
Delivery Carrier DPD France
===========================

Rate, ship and track parcels with **DPD France** from Odoo 19: DPD CLASSIC,
DPD Predict and DPD Relais.

This module plugs into Odoo's native delivery framework (``delivery`` /
``stock_delivery``) and adds a ``dpd`` carrier type that can:

* **Rate** a shipment using a DPD tariff grid (weight by zone) or Odoo's
  rule-based pricing.
* **Ship**: generate a DPD label with the
  `roulier <https://pypi.org/project/roulier/>`_ library on the e-Station web
  service (production or test environment) and store the tracking number on
  the delivery order. Zero-weight parcels, incomplete addresses, missing
  contract data, a missing Pickup relay (DPD Relais) or a missing mobile
  number (DPD Predict) are rejected with a clear message before anything is
  sent.
* **Track**: expose the DPD tracking link to the customer.
* **Pickup relays**: search nearby Pickup relays through the DPD Pickup web
  service and select one on the sale order or the delivery order. A relay
  chosen on the order is carried onto the delivery at confirmation and sent
  to DPD on the label.
* **Test the connection** from the carrier form: the Pickup web service is
  queried with your key on the company address, and its error codes are
  surfaced.

Pricing
=======

DPD France does not expose a live rating API, so prices come from data you
control:

* **Tariff grid** *(default)*: weight brackets per zone, edited directly on
  the carrier. Zones: metropolitan France (with Monaco), Europe zone 1
  (Germany, Belgium, Luxembourg, Netherlands), Europe zone 2 (rest of Europe,
  United Kingdom, Switzerland) and Intercontinental.
* **Odoo pricing rules**: the standard ``base_on_rule`` engine.

Every quote also reports the announced **delivery time** in working days
(``delay_min`` / ``delay_max`` in the ``rate_shipment`` result, shown in the
shipping wizard). Set it on the carrier and override it per zone on the
tariff grid, then compare carriers on cost and speed.

``delivery.carrier._dpd_get_live_price`` is a fail-closed extension point.
Override it to plug a rating endpoint (for example a third-party aggregator)
without touching the rest of the flow.

Demo data ships three carriers with indicative 2026 public rates (Predict,
Relais, CLASSIC Europe). DPD rates are negotiated per contract: replace them
with yours.

Requirements
============

* Python ``roulier`` for DPD label generation.
* A DPD France e-Station account (login, password), your customer number and
  agency code, set on the carrier.
* For Pickup relay search: the key of the DPD Pickup web service, provided
  with a DPD Relais contract. The search is called with ``requests`` and
  ``lxml``, shipped with Odoo.

Rating and relay search work with no external library. ``roulier`` is
optional, imported on demand, and label generation fails closed with a clear
message if it is missing.

Deploy the module on the ``addons_path`` (Odoo.sh or On-Premise). The
*Apps > Import Module* zip upload is data-only: it never loads Python models,
so it fails on the first model reference. On Odoo Online (SaaS) Python
libraries cannot be installed either, so labels need Odoo.sh or On-Premise.

Configuration
=============

#. Go to *Inventory > Configuration > Shipping Methods*.
#. Create a shipping method with provider **DPD France**.
#. Fill the e-Station login and password, the customer number and the agency
   code, tick *Test environment* while validating, then fill the Pickup
   search key and click **Test connection**.
#. Choose the DPD product (CLASSIC, Predict, Relais), the recipient
   notification and the label format.
#. Choose a pricing method and fill the tariff grid (or the pricing rules).
#. Set *Integration Level* to **Get Rate and Create Shipment** to generate
   labels on delivery validation.
#. Make sure the company address is complete, with a phone number: it is
   the parcel sender.

Access rights
=============

A **DPD Delivery** privilege provides two groups: *User* (ship, track, pick
relays) and *Administrator* (configure carriers, credentials and grids).
Credentials and the Pickup key are readable by administrators only, secrets
are masked in error messages, and a record rule isolates tariff grids per
company. Sales users can pick a relay on quotations. The main administrator
is added to the *Administrator* group at install.

Credits
=======

Authors
-------

* ROEKISH

Contributors
------------

* Alexis Maison (`alexis2m <https://github.com/alexis2m>`_), ROEKISH

This module follows the design of the ROEKISH ``roekish_delivery_laposte``
module and relies on the ``dpd_fr_soap`` carrier of the ``roulier`` library
(Akretion, AGPL-3).

License
=======

AGPL-3. See ``LICENSE`` / http://www.gnu.org/licenses/agpl.html.
