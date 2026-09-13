<p align="center">
  <img src="docs/logo.svg" alt="roekish_delivery_dpd" width="480">
</p>

<h1 align="center">roekish_delivery_dpd</h1>

<p align="center">
  <strong>Expédiez avec DPD France depuis Odoo 19 : Predict, Relais, CLASSIC.</strong><br>
  Tarification, étiquettes, suivi, relais Pickup.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-AGPL--3.0-blue.svg" alt="Licence AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/Odoo-19.0-875A7B.svg" alt="Odoo 19.0">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB.svg" alt="Python 3.12">
  <a href="https://github.com/roekish-org/odoo-delivery-dpd/actions/workflows/ci.yml"><img src="https://github.com/roekish-org/odoo-delivery-dpd/actions/workflows/ci.yml/badge.svg?branch=19.0" alt="CI"></a>
  <img src="https://img.shields.io/badge/PRs-bienvenues-brightgreen.svg" alt="PRs bienvenues">
</p>

---

## Fonctionnalités

| | |
|---|---|
| **Tarification** | Prix calculé depuis une **grille tarifaire DPD** (poids × zone) ou les **règles de prix natives** d'Odoo. Point d'extension `_dpd_get_live_price` (fail-closed) pour un futur service de cotation. |
| **Délai de livraison** | Délai annoncé en **jours ouvrés** (min / max) réglé sur le transporteur, surchargeable par zone dans la grille. Renvoyé avec le prix par `rate_shipment` (`delay_min` / `delay_max`) et affiché dans l'assistant d'ajout de livraison, pour choisir un transporteur sur le coût et le délai. |
| **Étiquettes** | Génération d'étiquette DPD via [`roulier`](https://pypi.org/project/roulier/) sur le web service **e-Station** (production ou environnement de test) ; numéro de suivi enregistré sur le bon de livraison. |
| **Relais Pickup** | Recherche des relais proches (web service Pickup MyPudo), sélectionnable sur le **devis** et le **bon de livraison**, propagé à la validation. |
| **Suivi** | Lien de suivi DPD pour le client. |
| **Produits** | DPD CLASSIC, DPD Predict (créneau par SMS) et DPD Relais, avec notification SMS ou email au destinataire. |

Bâti sur le framework de livraison natif d'Odoo (`delivery` / `stock_delivery`).
Une **seule dépendance** de module ; `roulier` est importé à la demande et
**fail-closed** s'il manque. Le module reste léger et installable.

## Transporteurs et zones

Grilles indicatives 2026 fournies en démo, **éditables** par vos utilisateurs :
France, Europe zone 1 (Allemagne, Belgique, Luxembourg, Pays-Bas), Europe
zone 2 (reste de l'Europe, Royaume-Uni, Suisse), Intercontinental. Trois
transporteurs prêts à l'emploi :

`Predict` &nbsp; `Relais` &nbsp; `CLASSIC Europe`

DPD France ne publie pas de grille publique : les tarifs sont négociés par
contrat. Remplacez les grilles de démo par les vôtres.

## Installation

```bash
pip install roulier          # étiquettes DPD (e-Station)
```

Copiez `roekish_delivery_dpd/` dans votre `addons_path`, puis installez le
module depuis *Applications*. La tarification et la recherche de relais
fonctionnent **sans aucune librairie externe**.

> Déployez le module via l'`addons_path` uniquement (Odoo.sh ou On-Premise).
> *Applications > Importer un module* (zip) ne charge que les données, jamais
> les modèles Python : l'installation échoue dès la première référence à un
> modèle.

## Démo locale (Docker)

Pile Odoo 19 + PostgreSQL fournie pour tester immédiatement :

```bash
make init   # image + base de démo avec données
make up     # http://localhost:8069  (admin / admin)
make test   # suite de tests du module
```

## Sécurité

- Identifiants e-Station et clé Pickup réservés au groupe
  **Administrateur DPD** ; secrets masqués dans les messages d'erreur.
- Droits d'accès fins : groupes **Utilisateur** et **Administrateur** dédiés.
- Isolation multi-société sur les grilles tarifaires.

## Documentation

- [DEVELOPMENT.md](DEVELOPMENT.md) : mise en production, environnement de
  test e-Station, vérification, droits d'accès.
- [Wiki](https://github.com/roekish-org/odoo-delivery-dpd/wiki) :
  installation, configuration, grilles, relais Pickup, go-live.
- [roekish_delivery_dpd/README.rst](roekish_delivery_dpd/README.rst) : fiche du module.

Modules frères : [odoo-delivery-laposte](https://github.com/roekish-org/odoo-delivery-laposte)
(Colissimo, Delivengo) et
[odoo-delivery-mondialrelay](https://github.com/roekish-org/odoo-delivery-mondialrelay).

## Contribuer

Les contributions sont bienvenues. Lisez le
[guide de contribution](CONTRIBUTING.md) et le
[code de conduite](CODE_OF_CONDUCT.md). Ouvrez une *issue* pour discuter d'une
évolution, ou proposez une *pull request* sur la branche `19.0`.

## Licence

[AGPL-3.0](LICENSE). © 2026 [ROEKISH](https://github.com/roekish-org).
Maintenu par [alexis2m](https://github.com/alexis2m).
