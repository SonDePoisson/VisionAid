# VisionAId

Guidage sonore pour les personnes aveugles ou malvoyantes : un téléphone porté sur le torse filme
la pièce, l'ordinateur repère l'objet demandé (« je cherche ma gourde ») et guide la personne
jusqu'à lui par des sons dans un casque. Tout le calcul se fait sur l'ordinateur ; aucune image
n'est envoyée sur Internet.

## Utiliser l'application

```bash
uv run visionaid
```

La fenêtre VisionAId s'ouvre sur l'ordinateur (sans navigateur ; s'il n'y a pas de moteur de
fenêtre sur la machine, l'interface s'ouvre dans le navigateur).

1. **Préparation** (premier lancement seulement) : les modèles se téléchargent, avec la
   progression affichée. Il faut Internet une fois ; ensuite tout fonctionne hors ligne.
2. **Connecter le téléphone** : même Wi-Fi que l'ordinateur, scanner le code QR, accepter la
   connexion locale, puis toucher **Démarrer** sur le téléphone (caméra et micro autorisés une
   seule fois).
3. **Tester le casque** : un son à gauche, à droite, puis devant.
4. **Accueil** : **Démarrer le guidage**. L'objet est choisi à la voix sur le téléphone
   (« je cherche ma gourde », « où sont mes clés ») ou sur l'ordinateur.

Pendant le guidage, l'ordinateur affiche la distance et la direction du son ; le téléphone
montre un grand rond **Parler** et un bouton **Arrêter**. Les volumes de chaque son se règlent
dans **Sons** ; le **Mode avancé** donne la vue 3D (Rerun), l'enregistrement des sessions et les
outils de test du téléphone.

Options utiles :

| Option | Effet |
|---|---|
| `--browser` | ouvrir l'interface dans le navigateur plutôt que dans une fenêtre |
| `--fake-phone [vidéo]` | démonstration sans téléphone (motif, ou vidéo rejouée) |
| `--stub-models` | modèles factices (tests, démonstration rapide) |

Où sont les fichiers : lancé depuis ce dépôt, comme avant (`outputs/`, `.cache/`, `data/`) ;
installé comme logiciel, dans le dossier de l'utilisateur (`~/Library/Application Support/VisionAId`
sur Mac, `%APPDATA%\VisionAId` sous Windows, `~/.local/share/visionaid` sous Linux), ou dans
`$VISIONAID_HOME` s'il est défini.

## Développement

```bash
make setup
```

```bash
make test-fast
```

Les commandes historiques (direct en ligne de commande, rejeu de sessions, calibration,
diagnostic) sont décrites dans [COMMANDES.md](COMMANDES.md). Les choix techniques sont dans
[DECISIONS.md](DECISIONS.md) et l'avancement dans [PROGRESS.md](PROGRESS.md).

Polices fournies avec l'interface : Lexend et Atkinson Hyperlegible, sous licence SIL Open Font
License 1.1 (`src/visionaid/app/web/fonts/`).
