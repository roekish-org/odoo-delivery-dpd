# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Ce projet suit le versionnage des modules Odoo (`19.0.x.y.z`).

## [19.0.1.4.0] - 2026-10-06

### Ajouté

- **Zonage Europe des contrats DPD France** : Euro 1 à Euro 5 (Euro 3 :
  Andorre, Croatie, Danemark, Estonie, Hongrie, Irlande, Lettonie, Lituanie,
  Slovaquie, Slovénie, Suède ; Euro 4 : Bulgarie, Finlande, Grèce, Norvège,
  Roumanie ; Euro 5 : Bosnie, Serbie). Une grille sans ligne Euro 3 à 5 garde
  ses prix Euro 2 pour ces pays.
- **Surcharge gasoil (%)** et **frais fixes par colis** (participation sûreté,
  contribution logistique…) ajoutés au prix de la grille.
- **Poids volumétrique** facultatif : volume des articles (cm³) / diviseur
  (5000 chez DPD), retenu s'il dépasse le poids réel.

### Modifié

- Chypre et Malte, absents du zonage DPD France, passent en Intercontinental.

## [19.0.1.3.1] - 2026-10-03

### Corrigé

- **N° client au format du contrat** : « 238-21260 » (code agence, tiret,
  n° client) est accepté. e-Station reçoit l'agence (238) et le n° client
  (21260) séparément ; l'agence complète un champ « Code agence » vide, et
  une agence contradictoire est refusée.
- **Clé de recherche Pickup facultative** : sans clé, le test de connexion
  n'échoue plus et l'identifiant du relais se saisit directement sur le devis
  ou le bon de livraison (recherche indisponible, message explicite).

## [19.0.1.3.0] - 2026-10-03

### Corrigé

- **N° client et code agence** : e-Station les lit comme des entiers et
  rejetait l'envoi avec une erreur SOAP opaque (« Input string was not in a
  correct format ») quand ils contenaient autre chose que des chiffres. Ils
  sont désormais contrôlés dès l'enregistrement du transporteur, avec un
  message clair, et les espaces autour sont retirés à l'envoi.
- **Relais Pickup** : sans clé de recherche, le module affichait des relais
  fictifs même en production, refusés ensuite sur l'étiquette. Les relais de
  démonstration sont réservés au mode « Étiquettes de démonstration » ; hors
  démo, l'absence de clé est signalée clairement. L'aide de la clé précise
  que DPD n'en délivre pas avec le contrat.

### Ajouté

- Le récapitulatif d'expédition renvoyé par e-Station (EPRINTATTACHMENT) est
  joint au bon de livraison avec l'étiquette.
- Test qui fait passer la charge utile par la validation réelle de roulier
  (sans appel réseau).

## [19.0.1.2.0] - 2026-10-03

### Ajouté

- **Étiquettes de démonstration** : case à cocher sur le transporteur.
  Activée, la validation d'un bon de livraison joint une étiquette PDF 10x15
  « SPÉCIMEN » générée localement (adresses, poids, référence, relais Pickup,
  code-barres) avec un faux numéro de suivi `DEMO…`, sans appel à e-Station :
  aucun envoi créé, rien de facturé, n° client et code agence non requis.
  Les autres contrôles du colis (poids, adresse, relais, mobile Predict,
  téléphone expéditeur) restent appliqués. Un bandeau signale le mode sur la
  fiche transporteur ; pas de lien de suivi pour les numéros `DEMO`.

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
