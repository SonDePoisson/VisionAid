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

## Applications installables (Mac, Windows, Linux)

Le workflow GitHub Actions **Applications** (`.github/workflows/applications.yml`) fabrique :

| Système | Fichier | Installation |
|---|---|---|
| macOS (Apple Silicon) | `VisionAId-<version>-macos-arm64.dmg` | glisser VisionAId dans Applications |
| Windows (x64) | `VisionAId-<version>-windows-x64-setup.exe` (+ `.zip` portable) | installateur, sans droits administrateur |
| Linux (x86_64) | `VisionAId-<version>-linux-x86_64.AppImage` (+ `.tar.gz`) | `chmod +x` puis lancer |

Le lancer : onglet **Actions** → **Applications** → **Run workflow** (fichiers dans les
« artifacts » du run), ou pousser une étiquette de version, qui crée aussi un brouillon de
*release* avec les trois fichiers :

```bash
git tag v0.1.0
```

```bash
git push origin v0.1.0
```

Chaque version est vérifiée avant d'être publiée (`packaging/smoke_test.py`) : chargement des
bibliothèques lourdes (`--self-test`), puis démarrage du guidage avec un faux téléphone et arrêt.
Les modèles (~2,6 Go) ne sont pas dans l'installateur : l'application les télécharge au premier
lancement, comme depuis les sources. Le journal de l'application installée est dans
`logs/visionaid.log` du dossier de l'utilisateur.

**Désinstaller.** Tout ce que l'application installée écrit, modèles compris, est dans un seul
dossier de l'utilisateur : `~/Library/Application Support/VisionAId` (Mac), `%APPDATA%\VisionAId`
(Windows), `~/.local/share/visionaid` (Linux). La désinstallation supprime le programme et ce
dossier :

| Système | Comment |
|---|---|
| macOS | double-cliquer **Désinstaller VisionAId** (dans le .dmg, à côté de l'application) |
| Windows | menu Démarrer → **Désinstaller VisionAId**, ou Paramètres → Applications ; version portable : `Désinstaller VisionAId.bat` dans son dossier |
| Linux | `./VisionAId-<version>-linux-x86_64.AppImage --uninstall` (supprime aussi l'AppImage) |

Lancé depuis les sources (`uv run visionaid`), rien ne change : les modèles restent dans les caches
habituels (`~/.cache/huggingface`, `~/.cache/torch`), partagés avec les autres outils.

Fabriquer localement, pour le système de la machine (résultat dans `dist/`) :

```bash
make package
```

Notes :
- **macOS** : sans certificat Apple, l'application est signée « ad hoc » ; au premier lancement,
  clic droit → **Ouvrir** (ou `xattr -dr com.apple.quarantine /Applications/VisionAId.app`).
  Pour une application signée et notarisée, ajouter les secrets du dépôt
  `MACOS_CERTIFICATE` (certificat Developer ID .p12 en base64), `MACOS_CERTIFICATE_PASSWORD`,
  `MACOS_CODESIGN_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD`. Les Mac Intel ne
  sont pas pris en charge (PyTorch ne les fournit plus).
- **Windows** : sans signature de code, SmartScreen avertit au premier lancement (« Informations
  complémentaires » → « Exécuter quand même »). La fenêtre utilise WebView2, présent sur
  Windows 10/11.
- **Linux** : PyTorch sans CUDA (calcul sur le processeur). Pas de moteur de fenêtre embarqué :
  l'interface s'ouvre dans le navigateur par défaut.

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
