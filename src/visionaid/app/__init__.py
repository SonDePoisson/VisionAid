"""Application de l'ordinateur : fenêtre de contrôle de VisionAId (commande `visionaid`).

L'aidant y prépare le logiciel, connecte le téléphone, teste le casque et lance le guidage.
Le guidage lui-même reste le graphe temps réel de `visionaid.apps.run_live`, lancé en
arrière-plan ; l'application le pilote par le serveur du téléphone (routes `/control`).
"""
