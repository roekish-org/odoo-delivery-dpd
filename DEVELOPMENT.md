# roekish_delivery_dpd: Development & Go-Live Guide

Odoo 19 delivery carrier for **DPD France**: DPD CLASSIC, DPD Predict and
DPD Relais (rating, labels through the e-Station web service, tracking,
Pickup relays). Owned by **ROEKISH**.

---

## 1. Requirements

- Docker and Docker Compose (v2).
- No local Python/Postgres needed, everything runs in containers.

The stack (`docker-compose.yml`): Postgres 16 + Odoo 19 with `roulier`
(labels) baked into the image (`docker/Dockerfile`).

---

## 2. Quick start

```bash
make init   # build the image + create the demo DB with the module & demo data
make up     # start Odoo  ->  http://localhost:8069   (login: admin / admin)
```

Other targets:

| Command | What it does |
|---|---|
| `make test` | Run the module test suite |
| `make shell` | Open an Odoo shell on the demo DB |
| `make logs` | Follow the Odoo logs |
| `make down` | Stop the stack |
| `make reset` | Drop the demo database (then `make init` to rebuild) |

The demo database is `dpd` (override with `make init DB=mydb`).

---

## 3. What the demo ships

Three ready-to-use carriers under *Inventory → Configuration → Shipping
Methods*, each with an indicative, editable grid:

- **DPD Predict**: home delivery with an SMS time slot, France grid.
- **DPD Relais**: Pickup relay delivery, France grid (drives the relay
  selector).
- **DPD CLASSIC Europe**: road export, Europe zone 1 and zone 2 grids.

DPD France publishes no public grid: the demo prices come from parcel
comparison sites (2026, taxes included) and are indicative only. Your users
**copy a carrier and edit its grid** with their negotiated contract rates.

---

## 4. Going live with a real DPD France account

1. Open the carrier (e.g. *DPD Predict*) → **DPD** tab.
2. **e-Station credentials**: enter the **login** and **password** of your
   e-Station web service account (readable only by DPD *Administrators*,
   see §6), your **customer number** (6 digits) and **agency code**
   (3 digits), both printed on your DPD contract.
3. Tick **Test environment** to send label requests to
   `e-station-testenv.cargonet.software` while validating, then untick it.
4. **Pickup relay search**: paste the **Pickup search key** given with your
   DPD Relais contract (the carrier code stays `EXA` for DPD France), then
   click **Test connection**: it queries the Pickup web service on your
   company address and reports success or the exact MyPudo error code.
5. Set the **DPD product** (CLASSIC, Predict or Relais), the **recipient
   notification** (none, automatic SMS or email; Predict always uses the
   Predict SMS) and the **label format** (PDF, PDF A6, ZPL, PNG).
6. Set **Integration Level = Get Rate and Create Shipment** so labels generate
   on delivery validation.
7. Make sure your **company address** is complete (street, ZIP, city, country,
   **phone**). It is the parcel sender, and e-Station requires its phone.

### Sender/recipient data
Addresses are built from `res.partner` (company for the sender, delivery
contact for the recipient). roulier appends `street2` to the street (70
characters) and the company name to the contact name (35 characters), as
e-Station has a single line for each. DPD Predict needs a French mobile
number on the recipient, DPD Relais needs a Pickup relay on the delivery.

### Labels & tracking
On delivery validation Odoo calls `roulier.get('dpd_fr_soap', 'get_label', …)`
with `product`, `customerId`, `agencyId`, `customerCountry` (250) and the
label format, attaches the returned label to the transfer, and stores the
parcel number in `carrier_tracking_ref`. The customer tracking link points to
`trace.dpd.fr/fr/trace/<number>`.

> The `roulier` label call is the version-sensitive external boundary.
> Validate it once against the e-Station test environment (see the go-live
> checklist in §8).

---

## 5. Pricing model

`dpd_rate_shipment` resolves a price in this order:

1. `_dpd_get_live_price(order)`: a fail-closed hook. DPD France exposes no
   live rating API, so it returns `None` by default. Override it to plug a
   real endpoint (e.g. a third-party aggregator) without touching the rest.
2. **Pricing method = Tariff grid** → looks up `(zone, weight)` in the
   carrier's grid. Zone is derived from the destination country
   (`_dpd_get_zone`).
3. **Pricing method = Odoo rules** → falls back to the standard
   `base_on_rule` engine (rules editable on the same tab).

Prices are expressed in the carrier company currency.

Zone → country mapping lives in `models/delivery_carrier.py`
(`FR_COUNTRY_CODES`, `EU1_COUNTRY_CODES`, `EU2_COUNTRY_CODES`, everything else
is `INT`). **The Europe split is a representative one**: align it with the
zoning of your DPD CLASSIC Europe contract before finalizing international
pricing.

---

## 6. Access rights

A dedicated **DPD Delivery** privilege (Settings → Users) with two groups:

- **User**: generate labels, track parcels, pick Pickup relays (implies
  *Inventory / User*).
- **Administrator**: configure carriers, credentials and tariff grids
  (implies *User* + *Inventory / Administrator*).

On install, the main administrator (`base.user_admin`) is added to
**Administrator** automatically (via `post_init_hook`) so the module is usable
out of the box. Assign the groups to your other users under *Settings → Users*.

Security notes:
- Credential fields (`dpd_login`, `dpd_password`, `dpd_pudo_key`) are locked
  to **Administrator** at the ORM level, and a plain user reading them gets an
  `AccessError`. The label and relay flows read them with `sudo`, so any DPD
  user can ship.
- All carrier/library error messages pass through a secret masker that redacts
  the password, the Pickup key and any `<password>` XML node.
- A global record rule isolates tariff grids per company.

---

## 7. Pickup relays

For DPD Relais carriers, a **Choose Pickup relay** button appears on the
**sale order** and the **delivery order**. It opens a wizard that searches
nearby relays and lets the user select one.

- With a Pickup key set → live MyPudo call
  (`GET mypudo.pickup-services.com/mypudo/mypudo.asmx/GetPudoList`, XML
  answer, `<ERROR code>` node surfaced as an error).
- Without a key → three clearly-labelled demo relays, so the flow is testable
  offline.

A relay chosen on the sale order **propagates to the delivery order** on
confirmation, and is sent to DPD as `pickupLocationId` on the label.

---

## 8. Go-live checklist

- [ ] `make init && make up`, log in, confirm the three demo carriers load.
- [ ] Enter real e-Station credentials, customer number and agency code on a
      carrier; tick **Test environment**.
- [ ] Paste the Pickup key and click **Test connection**.
- [ ] Replace demo grid lines with your contract tariffs; adjust the Europe
      zones to your contract.
- [ ] Generate one label on the test environment end-to-end (confirm a
      delivery with the carrier), check the PDF and the parcel number.
- [ ] Test one Pickup relay selection with the real key, then one DPD Relais
      label with that relay.
- [ ] For DPD Predict, check the recipient mobile number is filled.
- [ ] Untick **Test environment**.

---

## 9. Project layout

```
odoo-delivery-dpd/
├── docker-compose.yml        # Postgres + Odoo 19 stack
├── docker/                   # Dockerfile (roulier) + odoo.conf
├── Makefile                  # init / up / test / shell / reset
└── roekish_delivery_dpd/     # the Odoo module
    ├── models/               # carrier, tariff, pickup mixin, sale, picking
    ├── wizards/              # Pickup relay search wizard
    ├── views/                # carrier, sale order, picking forms
    ├── security/             # groups, privilege, ACLs, record rule
    ├── demo/                 # indicative 2026 tariff grids
    └── tests/                # rating, zones, relays, propagation, labels
```

The runtime dep (`roulier`) is imported lazily and is **not** declared as a
hard `external_dependency`: the module installs light and label generation
fails closed with a clear message if the library is missing.

---

## 10. Sandbox & verifying it works

### DPD France test access
- **e-Station**: DPD France provides a test environment
  (`e-station-testenv.cargonet.software`) reachable with the credentials of
  your contract; there is no public test account. Tick **Test environment**
  on the carrier to use it.
- **Pickup search**: the MyPudo web service answers without authentication
  but requires a personal key (error `327` otherwise); DPD France provides
  it with the DPD Relais offer, and its official e-commerce modules ship a
  shared key you can reuse.

### What is already verified (no account needed)
- `make test` runs the module suite (25 tests): zone mapping, grid and
  rule-based rating, tracking link, cancellation, secret masking, demo and
  offline relays, sale→delivery relay propagation, the MyPudo `<ERROR>`
  handling and non-administrator access to relay search (both with a mocked
  HTTP client), the fail-closed guards (missing library, zero weight,
  incomplete address, missing contract data, missing relay, missing mobile,
  missing sender phone, shared carrier without company), and a **mocked
  label generation** (`test_send_shipping_mocked`) that drives the real
  `send_shipping` code against roulier's response shape and asserts the label
  is attached and the parcel number stored.
- The **Pickup web service path is verified against the live MyPudo server**:
  a call without key answers `ERROR code="327"`, which we surface as an
  error (MyPudo returns errors in the body with HTTP 200, so this is checked
  explicitly).

### What still needs a real account
- Generating an actual label end-to-end (valid `roulier` `get_label` call on
  the test environment).
- Listing real Pickup relays (valid Pickup key).

### How to check a real account
1. Enter the Pickup key on a carrier → **Test connection**. Success means the
   key is accepted by MyPudo; an error shows the exact MyPudo code/message.
2. Tick **Test environment**, confirm a delivery with the carrier to generate
   one test label, and verify the parcel number and the attached label on the
   transfer.
