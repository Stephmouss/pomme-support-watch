# Apple Support Watch

Apple Support Watch surveille les sitemaps officiels d’Apple Support en anglais
américain et en français. Il publie quatre flux RSS : nouvelles fiches et
fiches modifiées pour chaque langue. Les versions successives des articles sont
conservées en Markdown et les changements disposent d’une page de comparaison.

## Flux publiés

- `feeds/en-us-new.xml`
- `feeds/en-us-updated.xml`
- `feeds/fr-fr-new.xml`
- `feeds/fr-fr-updated.xml`

Une fois GitHub Pages activé, les URLs sont de la forme :

```text
https://COMPTE.github.io/NOM-DU-DEPOT/feeds/en-us-new.xml
```

## Fonctionnement

Le workflow GitHub Actions s’exécute aux minutes 17 et 47 de chaque heure. Il :

1. découvre les sitemaps `ac` depuis les index Apple ;
2. compare les URL et les champs `lastmod` avec l’état précédent ;
3. extrait le contenu éditorial des fiches nouvelles ou modifiées ;
4. normalise ce contenu en Markdown et calcule un diff ;
5. met à jour les snapshots, les pages HTML et les quatre flux ;
6. enregistre les changements dans Git et déploie `public/` avec GitHub Pages.

La première exécution initialise la liste des fiches sans créer des milliers
d’alertes. Les snapshots sont ensuite constitués progressivement, en donnant
la priorité aux documents modifiés récemment.

## Installation sur GitHub

1. Créer un dépôt **public** et y pousser ce projet.
2. Dans **Settings > Actions > General > Workflow permissions**, autoriser
   **Read and write permissions**.
3. Dans **Settings > Pages > Build and deployment**, sélectionner
   **GitHub Actions** comme source.
4. Ouvrir **Actions > Apple Support Watch**, puis lancer **Run workflow**.
5. Attendre le premier déploiement et ajouter les quatre URLs à Feedbin.

Aucun secret et aucun service extérieur ne sont nécessaires.

## Développement local

Python 3.11 ou plus récent est recommandé.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m apple_support_watch run --dry-run
```

Pour une exécution réelle locale :

```bash
python -m apple_support_watch run
```

## Configuration

Les paramètres sont dans `config/sources.json`. Les principales valeurs sont :

- `bootstrap_batch_size` : nombre de snapshots initiaux créés par passage ;
- `audit_batch_size` : nombre de fiches contrôlées même sans nouveau `lastmod` ;
- `removal_confirmations` : nombre de constats avant de signaler un retrait ;
- `feed_item_limit` : nombre maximal d’entrées dans chaque flux.

La variable d’environnement `SITE_URL` remplace automatiquement l’URL locale
par celle de GitHub Pages dans le workflow.

## Limites

- Les workflows programmés GitHub peuvent subir un retard.
- Une refonte du HTML d’Apple peut nécessiter d’adapter l’extracteur.
- Les snapshots, les diffs et les flux sont publics.
- Ce projet n’est ni affilié à Apple ni approuvé par Apple.
- La licence MIT couvre le code du projet, pas les contenus provenant d’Apple.
