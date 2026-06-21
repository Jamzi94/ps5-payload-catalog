# Catalogue PS5 auto-update pour PS5 Payload Manager

Génère automatiquement un `payloads.json` qui pointe toujours vers la **dernière
release** de plusieurs dépôts GitHub de payloads, et le republie tout seul.

## URL à coller dans Payload Manager

Une fois le repo créé sous ton compte (`TON_PSEUDO`) :

```
https://raw.githubusercontent.com/TON_PSEUDO/ps5-payload-catalog/main/payloads.json
```

`raw.githubusercontent.com` renvoie déjà l'en-tête `Access-Control-Allow-Origin: *`,
donc aucune config CORS à faire.

> Dashboard → Settings (roue dentée) → Manage Sources → Add Source → coller l'URL → Add.

## Comment ça marche

1. `repos.json` liste les dépôts sources à suivre.
2. `build.py` interroge l'API GitHub `releases/latest` de chacun, récupère les
   assets `.elf` / `.bin`, et écrit `payloads.json`.
3. Le workflow `.github/workflows/build-catalog.yml` relance le build
   **toutes les 6 h** (cron) + à chaque modif de config, et commit le résultat.

## Installation (5 min)

1. Crée un repo **public** nommé `ps5-payload-catalog`.
2. Ajoute ces 4 fichiers en respectant l'arborescence :
   ```
   ps5-payload-catalog/
   ├── .github/workflows/build-catalog.yml
   ├── build.py
   ├── repos.json
   └── README.md
   ```
3. Onglet **Actions** → autorise les workflows si demandé →
   lance « Build PS5 payload catalog » → **Run workflow**.
4. Vérifie que `payloads.json` apparaît à la racine, puis colle l'URL `raw` ci-dessus.

## Ajouter / retirer un dépôt

Édite simplement `repos.json` :

```json
{
  "owner": "AUTEUR",
  "repo": "NOM_DU_REPO",
  "label": "Nom affiché"
}
```

Pousse la modif → le workflow se relance automatiquement.

## Options

Dans `repos.json` :

- `asset_extensions` : extensions considérées comme payloads (`.elf`, `.bin`, …).
- `compute_checksum` : mets `true` pour calculer le SHA-256 de chaque fichier
  (Payload Manager vérifie alors l'intégrité avant install). Plus lent car il
  télécharge chaque binaire à chaque build.

## Notes

- Un dépôt sans release `latest`, ou sans asset correspondant, est simplement
  ignoré (le build ne casse pas).
- `raw.githubusercontent.com` a un cache CDN de quelques minutes : après un
  update, laisse passer ~5 min avant que la nouvelle version soit visible côté PS5.
