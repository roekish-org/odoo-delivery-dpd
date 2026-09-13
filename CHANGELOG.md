# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Ce projet suit le versionnage des modules Odoo (`19.0.x.y.z`).

## [19.0.1.1.0] - 2026-09-13

### Ajouté

- **Délai de livraison** annoncé, en jours ouvrés : champs min / max sur le
  transporteur, surcharge par zone sur les lignes de la grille tarifaire,
  valeurs de démo indicatives.
- Chaque cotation (`rate_shipment`) renvoie `delay_min` et `delay_max` avec
  le prix, pour choisir un transporteur sur le coût et le délai ; la phrase
  « Livraison en X à Y jours ouvrés » s'affiche dans l'assistant d'ajout de
  livraison et est conservée sur le devis.
- Tests du délai (grille, surcharge par zone, règles Odoo, point d'entrée
  générique).

## [19.0.1.0.0] - 2026-09-13

### Ajouté

- Type de transporteur `dpd` (DPD France) sur le framework de livraison natif
  d'Odoo, produits DPD CLASSIC, DPD Predict et DPD Relais.
- Tarification par grille DPD (zones FR, Europe 1, Europe 2, Intercontinental)
  ou par règles Odoo, avec un point d'extension `_dpd_get_live_price`.
- Génération d'étiquettes via `roulier` (web service e-Station, environnement
  de test ou production), numéro de suivi sur le bon de livraison, formats
  PDF, PDF A6, ZPL et PNG.
- Sélection de relais Pickup sur le devis et le bon de livraison, avec
  propagation à la confirmation (web service Pickup MyPudo, points de
  démonstration sans clé).
- Bouton de test de connexion (recherche Pickup sur l'adresse de la société).
- Lien de suivi DPD pour le client.
- Contrôles avant appel : poids nul, adresse incomplète, numéro client et
  code agence manquants, relais absent pour DPD Relais, mobile absent pour
  DPD Predict, téléphone expéditeur.
- Grilles indicatives 2026 en données de démonstration (Predict, Relais,
  CLASSIC Europe).
- Droits d'accès fins (groupes Utilisateur et Administrateur), masquage des
  secrets, isolation multi-société.
- Pile Docker de démonstration, suite de tests (25 tests), intégration
  continue.
