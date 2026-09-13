# Contribuer

Merci de votre intérêt. Ce module est ouvert aux contributions : correctifs,
grilles tarifaires, traductions, documentation.

## Avant de commencer

- Ouvrez une *issue* pour signaler un bug ou proposer une évolution avant
  d'écrire du code. On évite ainsi le travail en double.
- Les petites corrections (typo, doc) peuvent aller directement en *pull
  request*.

## Environnement de dev

La pile Docker fournie suffit :

```bash
make init   # image + base de démo
make up     # http://localhost:8069  (admin / admin)
make test   # tests du module
```

Détails dans [DEVELOPMENT.md](DEVELOPMENT.md).

## Règles de code

- Code, commentaires et messages de commit en **anglais**. Les textes visibles
  par le client restent en français.
- Style Odoo standard. Le dépôt utilise `pre-commit` (black, flake8) :

  ```bash
  pip install pre-commit && pre-commit install
  ```

- Toute nouvelle logique vient avec un test. `make test` doit passer.
- Gardez le module léger : pas de dépendance nouvelle sans raison, imports
  externes en *fail-closed*.

## Messages de commit

Convention *conventional commits*, à l'impératif :

```
feat(pickup): ajoute le tri des relais par distance
fix(rating): corrige la zone pour Monaco
```

Préfixes : `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## Pull requests

- Basez votre branche sur `19.0` et visez `19.0`.
- Une PR = un sujet. Décrivez le quoi et le pourquoi.
- La CI (tests + lint) doit être verte. Une revue est requise avant merge.

## Licence

En contribuant, vous acceptez que votre code soit publié sous
[AGPL-3.0](LICENSE).
