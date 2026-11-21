# Mise en route du téléphone (iPhone 12, Safari)

Le téléphone ouvre une page web servie par le PC. Safari n'autorise la caméra et les capteurs de mouvement que sur une page **HTTPS** de confiance : il faut donc installer une seule fois le certificat de l'autorité locale du PC. Ce certificat est généré dans `.certs/`, qui n'est jamais commité.

## 1. Réseau
Le téléphone et le PC doivent être sur le **même réseau**. Si le Wi-Fi isole les appareils entre eux (fréquent en hackathon, la page ne se charge jamais), activez le **partage de connexion** de l'iPhone et connectez-y le PC.

## 2. Lancer le serveur
```bash
uv run python -m visionaid.apps.run_phone
```
Le terminal affiche les adresses `https://<ip>:8443/` et un QR code.

## 3. Installer le certificat (une seule fois par PC)
1. Sur l'iPhone, ouvrez dans **Safari** `http://<ip-du-pc>:8080/`, puis touchez « Télécharger le certificat ». Safari propose d'installer un profil : acceptez.
2. **Réglages → Général → VPN et gestion de l'appareil** → profil « VisionAId CA locale » → **Installer**.
3. **Réglages → Général → Informations → Réglages des certificats** → activez la **confiance totale** pour « VisionAId CA locale ».

Si l'adresse IP du PC change, le serveur réémet automatiquement son certificat avec la même autorité : rien à réinstaller.
Sur Android, la procédure est similaire : Paramètres → Sécurité → Chiffrement et identifiants → Installer un certificat → Certificat CA.

## 4. Démarrer la capture
1. Ouvrez `https://<ip-du-pc>:8443/` dans Safari, ou scannez le QR code.
2. Fixez le téléphone **sur le torse, en portrait, écran vers vous** (caméra arrière vers l'avant).
3. Touchez **Démarrer**, puis acceptez l'accès aux **mouvements** et à la **caméra**.
4. Vérifiez que :
   - le PC reçoit au moins 15 images/s ;
   - l'IMU dépasse 50 Hz ;
   - l'âge des images reste stable ;
   - la bulle du niveau est verte (téléphone bien vertical).

L'écran reste allumé grâce au verrou d'écran (Safari ≥ 16.4). Avec une version plus ancienne, désactivez le verrouillage automatique.

## Dépannage
| Symptôme | Cause probable | Solution |
|---|---|---|
| « Page non sécurisée » | page ouverte en `http://` | utiliser `https://…:8443/` |
| Avertissement de certificat | confiance totale non activée | étape 3.3 |
| La page ne charge pas | Wi-Fi isolant, pare-feu macOS | partage de connexion ; autoriser Python dans Réglages Système → Réseau → Pare-feu |
| IMU « absente » | permission des mouvements refusée | Réglages → Safari → Mouvement et orientation, puis recharger |
| Images figées | page masquée ou écran verrouillé | garder Safari au premier plan |
| « Cette connexion n'est pas privée » alors que le certificat est installé | le Mac a changé de réseau (Wi-Fi ↔ partage de connexion) et le certificat ne couvre pas la nouvelle adresse | le serveur le réémet tout seul en quelques secondes (message « Adresse réseau changée » dans le terminal) : recharger la page avec la **nouvelle** adresse affichée |
| « Connexion au serveur impossible » en partage de connexion | adresse du Wi-Fi utilisée alors que le Mac est sur le partage de connexion (adresse en 172.20.10.x), ou Chrome sans accès au réseau local | utiliser l'adresse en `172.20.10.x` affichée par le terminal ; pour Chrome : Réglages → Chrome → Réseau local activé |
| « Votre iPhone n'est pas connecté à Internet » en partage de connexion 5G | réseau **IPv6 seul** (Orange 5G…) : le Mac n'a qu'une IPv4 de traduction `192.0.0.2`, injoignable | serveur à jour (écoute IPv6) : ouvrir `https://<nom-du-mac>.local:8443/` (première adresse affichée) ou une adresse IPv6 entre crochets |
| Le téléphone n'atteint jamais le Mac | le téléphone de la page n'est pas sur le **même réseau** que le Mac (il est en 5G directe) | le plus simple : le Mac se connecte au partage de connexion **de l'iPhone qui filme** ; sinon les deux appareils sur le même partage ou le même Wi-Fi |
| Chrome sur iPhone | Chrome utilise les certificats d'iOS | installer le certificat **avec Safari** (étape 3), puis Chrome fonctionne aussi |
