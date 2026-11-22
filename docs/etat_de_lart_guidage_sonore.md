# État de l'art : le son pour guider les personnes aveugles et malvoyantes

*Phase de recherche (22/11/2026). Rien n'est encore codé. Ce document sert de base pour trouver des pistes innovantes pour VisionAid.*

> **Fiabilité des sources.** Les références marquées ✅ ont été retrouvées en ligne pendant cette recherche (en général l'abstract ou un résumé, pas toujours le texte complet). Celles marquées 📚 viennent de la littérature classique du domaine et n'ont pas été revérifiées : il faut contrôler les détails (chiffres, année) avant de les citer dans un rapport.

---

## 0. En bref (les 10 enseignements à retenir)

1. **Un son spatialisé demande moins d'effort qu'une consigne parlée** quand l'utilisateur est déjà occupé (traversée, conversation, mémoire). Sans charge cognitive, les deux font jeu égal. C'est le résultat le plus solide du domaine (Klatzky, Loomis et al. 2006).
2. **La voix reste meilleure pour le sens** (« porte », « escalier », « arrivé ») et pour apprendre vite. Les sons sont meilleurs pour la direction et l'ajustement continu. Les systèmes qui marchent sont **hybrides**.
3. **Les préférences varient beaucoup selon les personnes et leur expertise.** Il faut pouvoir régler la quantité d'information (Ahmetovic et al. 2019).
4. **Un son large bande (bruit, clic, son riche en harmoniques) se localise bien mieux qu'une sinusoïde pure.** Un balisage de type « sonar » a donné les meilleurs résultats chez Walker & Lindsay (2006).
5. **Un rayon de validation d'environ 1,5 m autour d'un point de passage** est un bon compromis. Trop petit, l'utilisateur dépasse le point puis le cherche ; trop grand, il coupe les virages.
6. **Le suivi des mouvements de tête compte plus qu'une HRTF personnalisée.** Il élimine presque toutes les confusions avant/arrière.
7. **Le casque ne doit pas boucher les oreilles.** Les personnes aveugles se servent du bruit de la circulation pour s'orienter et traverser. Conduction osseuse, écouteurs ouverts et mode transparence sont la norme ; la conduction osseuse localise presque aussi bien qu'un casque classique.
8. **Le tempo est le moyen le plus efficace de signaler l'urgence**, avant la hauteur (Edworthy, Hellier). Le « bip de radar de recul » est un modèle mental que tout le monde comprend.
9. **Un son continu fatigue et finit par être ignoré.** Les meilleurs systèmes se taisent quand tout va bien et ne signalent que les écarts.
10. **La « 8D audio » n'est pas une technique scientifique.** C'est un effet marketing (panoramique tournant + réverbération). Ce qu'il faut regarder, ce sont le binaural HRTF, l'ambisonie et le rendu paramétrique.

---

## 1. Voix ou sons : ce que disent les études

### 1.1 Charge cognitive : l'avantage du son spatialisé

- ✅ **Klatzky, Marston, Giudice, Golledge & Loomis (2006)**, *Cognitive load of navigating without vision when guided by virtual sound versus spatial language*, J. Exp. Psychol.: Applied 12(4), 223‑232. [PDF](https://umaine.edu/vemi/wp-content/uploads/sites/220/2016/06/Klatzky-etal2006-Cognitive-Load-of-Navigating-Without-Vision-jep-a.pdf)
  - Les participants suivent un chemin virtuel. Le guidage se fait soit par des mots (« gauche / droite / tout droit »), soit par un son virtuel placé dans la direction à suivre. Une tâche N‑back vibrotactile ajoute une charge mentale.
  - **Sans charge : pas de différence. Avec charge : avec le son virtuel, le trajet est plus court et plus rapide, et la tâche secondaire est mieux réussie.**
  - Explication : un son spatialisé se traite **directement par la perception**. Le langage doit d'abord être décodé, puis converti en direction.
- ✅ **Giudice et al. (2008)**, *Environmental learning without vision: effects of cognitive load on interface design*. [PDF](https://umaine.edu/vemi/wp-content/uploads/sites/220/2016/08/Giudice-etal2008-Environmental-Learning-without-Vision-Effects-of-Cognitive-Load-on-Interface-Design-vision08.pdf)
  - Avec un guidage par son spatialisé, la tâche secondaire **ne dégrade pas la carte mentale** du lieu. Avec un guidage par la voix, les erreurs de retour au point de départ augmentent nettement. Le son spatialisé est aussi plus rapide et plus précis.
- 📚 **Loomis, Golledge & Klatzky (1998)**, *Navigation system for the blind: auditory display modes and guidance*, Presence 7(2). C'est l'étude fondatrice du *Personal Guidance System* (UCSB). Le mode « son virtuel » y est plus rapide et plus apprécié que les modes vocaux.
- 📚 **Marston, Loomis, Klatzky, Golledge (2006)**, *Evaluation of spatial displays for navigation without sight*, ACM TAP. Les affichages spatiaux (son virtuel, pointeur haptique) l'emportent sur les consignes vocales.
- 📚 **Cadre théorique.** Selon la théorie des ressources multiples de **Wickens**, deux tâches se gênent davantage quand elles utilisent le même canal. Selon **Baddeley**, la mémoire de travail a une « boucle phonologique » pour le verbal et un « calepin visuo-spatial » pour l'espace. **La voix entre donc en concurrence avec la conversation, la réflexion et l'écoute des annonces**, alors qu'un son spatial passe par le canal spatial.

### 1.2 Sur le terrain, c'est plus nuancé

- ✅ **Mascetti, Picinali, Gerino, Ahmetovic, Bernareggi (2016)**, *Sonification of guidance data during road crossing for people with visual impairments or blindness*, IJHCS. [arXiv](https://arxiv.org/pdf/1506.07272)
  - L'étude compare deux modes sonifiés et un mode vocal pour s'aligner sur un passage piéton.
  - **Aucun mode n'est le meilleur pour tout le monde.** Plus des deux tiers des participants préfèrent un mode sonifié. En revanche, ils demandent souvent des **indices vocaux en renfort** et trouvent les sons **plus difficiles à décoder** que la voix.
  - ➜ À retenir : **le son pour la direction, la voix à la demande pour le sens.**
- ✅ **Ahmetovic, Avanzini, Baratè, Bernareggi, Ludovico, Mascetti et al.**
  - *Sonification of rotation instructions to support navigation of people with visual impairment*, PerCom 2019 ([dblp](https://dblp1.uni-trier.de/rec/conf/percom/AhmetovicABBGLM19.html)).
  - Puis la version longue IJHCS 2023, avec 9 participants malvoyants en conditions réelles ([PDF](https://ludovico.lim.di.unimi.it/download/papers/IJHCS2023.pdf)).
  - Ces travaux portent sur **comment sonifier une rotation** (tourner de X° sur place) et la marche en ligne droite. Ils sont très proches du problème « s'orienter vers l'objet » de VisionAid. **À lire en entier, c'est prioritaire.**
- ✅ **Ahmetovic, Guerreiro, Ohn-Bar, Kitani, Asakawa (2019)**, *Impact of Expertise on Interaction Preferences for Navigation Assistance of Visually Impaired Individuals*, W4A. [DOI 10.1145/3315002.3317561](https://doi.org/10.1145/3315002.3317561)
  - Les besoins en détail changent selon la personne et selon qu'elle connaît déjà le trajet. Les auteurs recommandent une **verbosité réglable** pour réduire les distractions.
  - Étude jumelle à IUI 2018, *Modeling Expertise in Assistive Navigation Interfaces for Blind People* : les utilisateurs progressent au fil des répétitions d'un même trajet.
- 📚 **NavCog (CMU, Asakawa)** : navigation intérieure par balises BLE, consignes vocales tour par tour. C'est la référence du guidage tout vocal.
- 📚 **Gaunet & Briffault (2005)** : comment formuler les consignes verbales pour des piétons aveugles. Les repères « en heures d'horloge » (« à 2 heures ») sont très utilisés en locomotion (instructeurs O&M).

### 1.3 Son ou vibration en présence de bruit

- ✅ **Bharadwaj, Shaw & Goldreich (2019)**, *Comparing Tactile to Auditory Guidance for Blind Individuals*, Frontiers in Human Neuroscience. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6930908)
  - 12 participants aveugles comparent une ceinture vibrante et des consignes auditives, avec et sans bruit de rue simulé.
  - Au calme, l'audio est meilleur. **Avec du bruit de rue, l'écart se réduit nettement** : la performance auditive chute davantage.
  - Résultats antérieurs : Gustafson-Pearce et al. (2007) trouvent moins d'erreurs en tactile dans le bruit ; Flores et al. (2015) trouvent le tactile plus lent.
  - ➜ **Une piste haptique en complément du son** (vibration du téléphone) devient intéressante dans les environnements bruyants.

### 1.4 Les sons de menu (earcons, icônes auditives, spearcons)

- 📚 **Earcons** (Blattner 1989, Brewster) : motifs musicaux abstraits. Ils sont expressifs mais **longs et frustrants à apprendre**.
- 📚 **Icônes auditives** (Gaver 1986) : sons du quotidien (porte, pas, eau). Elles sont **comprises sans apprentissage**.
- ✅ **Spearcons** (Walker, Nance & Lindsay 2006, ICAD) : un mot synthétisé puis **accéléré** jusqu'à ne plus être reconnu comme de la parole. Pour naviguer dans des menus, spearcons et voix font mieux qu'earcons et icônes auditives. Palladino & Walker (2007) montrent que les earcons sont nettement plus difficiles à apprendre. [core.ac.uk](https://core.ac.uk/download/4718939.pdf)
- ➜ Les spearcons sont un **compromis entre la voix et le son**. Exemple : « chaise » prononcé en 150 ms et spatialisé.

### 1.5 Synthèse comparative

| Critère | Voix | Son spatialisé | Sonification paramétrique (hauteur, tempo…) | Vibration |
|---|---|---|---|---|
| Apprentissage | immédiat | rapide | plus long | moyen |
| Charge cognitive sous double tâche | **élevée** | **faible** | faible à moyenne | faible |
| Précision angulaire | faible (« un peu à gauche ») | bonne avec suivi de tête | **très bonne** si un repère sonore indique la cible | moyenne |
| Information sur ce qu'il y a (sens) | **excellente** | nulle | nulle | nulle |
| Latence d'interprétation | 0,5 à 2 s | ~100 ms | ~100 ms | ~100 ms |
| Masque l'environnement | oui (débit continu) | peu, si sons courts | selon le timbre | **non** |
| Robustesse dans le bruit | moyenne | moyenne | moyenne | **bonne** |

---

## 2. Quels sons choisir : fréquences, timbre, rythme

### 2.1 Psychoacoustique de la localisation (bases)

- 📚 **ITD (différence de temps entre les oreilles)** : c'est l'indice dominant **sous ~1,5 kHz**.
- 📚 **ILD (différence de niveau entre les oreilles, effet d'ombre de la tête)** : c'est l'indice dominant **au-dessus de ~1,5 à 3 kHz**.
- 📚 **Indices spectraux du pavillon de l'oreille** (pour l'élévation et l'avant/arrière) : ils exigent de l'énergie **entre 4 et 16 kHz**.
- 📚 Conséquence : **une sinusoïde pure se localise mal**, surtout vers 2 à 4 kHz, où ni l'ITD ni l'ILD ne sont efficaces (Stevens & Newman 1936). Un **son large bande et transitoire** (clic, bruit filtré, attaque nette, son de percussion) fournit tous les indices à la fois.
- 📚 **Plus petit écart d'angle perçu** : environ 1 à 2° devant, plus de 10° sur les côtés. On perçoit donc mal les petits écarts latéraux, ce qui justifie l'« exagération des petits angles » déjà faite dans VisionAid ([director.py](../src/visionaid/audio/director.py)).
- ✅ **Walker & Lindsay (2006)**, *Navigation performance with a virtual auditory display: effects of beacon sound, capture radius, and practice*, Human Factors 48. [core.ac.uk](https://core.ac.uk/download/19562103.pdf)
  - **Le balisage de type sonar et un rayon de validation de 1,5 m forment la meilleure combinaison.**
  - Le bruit rose large bande et le « sonar ping » font mieux qu'un son pur.
  - L'entraînement améliore nettement les performances.

### 2.2 Ne pas couvrir le bruit ambiant

Pour un utilisateur aveugle, c'est **le critère n°1**. La circulation sert à s'aligner, à détecter un véhicule qui démarre et à savoir quand traverser.

- ✅ Les piétons aveugles détectent bien les véhicules au calme, mais mal dès qu'il y a un bruit de fond modéré. Les véhicules électriques aggravent le problème. Voir [PMC2814321](https://pmc.ncbi.nlm.nih.gov/articles/PMC2814321) et [PMC3046409](https://pmc.ncbi.nlm.nih.gov/articles/PMC3046409).
- ✅ Les utilisateurs de lecteurs d'écran portent souvent **un seul écouteur**. Peu utilisent la conduction osseuse ou le mode transparence (Ahmetovic et al. 2023, [PDF](https://iris.unito.it/bitstream/2318/2016332/1/ahmetovic2023enhancing.pdf)).
  - ⚠️ Problème pour la spatialisation binaurale : avec un seul écouteur, elle ne fonctionne plus. **Il faut un mode de secours mono**, où la direction est portée par la hauteur ou le rythme, pas par la stéréo.

**Pistes tirées de la psychoacoustique (📚, à valider par des tests) :**

| Principe | Justification |
|---|---|
| **Sons courts et rares** (50 à 200 ms, silence entre deux) plutôt que continus | Le masquage est temporel : un son bref laisse « respirer » l'écoute de l'environnement. |
| **Placer l'énergie entre ~1 et 4 kHz, sans grave fort** | Le bruit urbain est concentré sous 1 kHz (moteurs, roulement). Un indice entre 1 et 4 kHz ressort sans couvrir les graves qui portent l'information sur les véhicules. L'oreille est aussi la plus sensible vers 2 à 4 kHz. |
| **Garder des harmoniques ou un bruit aigu** (au-dessus de 4 kHz) pour la localisation | Voir 2.1 : les indices du pavillon sont nécessaires pour distinguer l'avant de l'arrière. |
| **Éviter la bande de la parole (300 Hz à 3 kHz) pour les sons de fond** | Pour ne pas gêner une conversation ni les annonces vocales. Compromis à trouver avec la ligne précédente. |
| **Volume adapté au bruit ambiant** (mesuré par le micro du téléphone) | Viser quelques dB au-dessus du seuil de masquage, pas plus. |
| **Baisser le guidage quand la voix parle (ducking)** | Hiérarchie claire : alerte > voix > guidage > ambiance. |
| **Timbres « naturels », peu agressifs** pour le guidage ; **timbres dissonants ou rugueux** réservés aux alertes | Recherche sur l'urgence perçue (ci-dessous) et sur la fatigue. |

### 2.3 Urgence, gêne et correspondances naturelles

- ✅ **Edworthy, Loxley & Dennis (1991)**, **Hellier, Edworthy & Dennis (1993)** et **Hellier & Edworthy (1999)**, sur l'urgence des alarmes. [Plymouth](https://researchportal.plymouth.ac.uk/en/publications/designing-urgency-into-auditory-warnings-using-pitch-speed-and-lo/)
  - L'urgence perçue augmente avec **le rythme de répétition (le levier le plus efficace)**, la hauteur et l'inharmonicité.
  - Certains paramètres augmentent l'urgence **sans trop augmenter la gêne**. C'est exactement ce qu'il faut viser pour un guidage qui dure des heures.
- ✅ **Suied, Susini & McAdams (2008)**, JEP: Applied : le temps de réaction dépend de l'urgence des alarmes. [PDF](https://www.mcgill.ca/mpcl/files/mpcl/suied_2008_jepappl.pdf)
- 📚 **Correspondances que l'on comprend sans apprentissage :**
  - aigu = haut (effet Pratt, utile pour l'élévation : marche, obstacle à hauteur de tête) ;
  - rapide = proche ou urgent (radar de recul) ;
  - fort = proche ;
  - consonant = bon cap, dissonant = écart (utilisé par Project Guideline).

### 2.4 Stratégies de sonification pour guider

- ✅ **Parseihian, Gondre, Aramaki, Ystad, Kronland-Martinet (2016)**, *Comparison and evaluation of sonification strategies for guidance tasks*, IEEE Trans. Multimedia (DOI 10.1109/TMM.2016.2531978). [PDF](https://typeset.io/pdf/comparison-and-evaluation-of-sonification-strategies-for-1dpfi7jxvq.pdf)
  - Les stratégies sont classées en trois familles : **basiques** (faire varier hauteur, volume, tempo…), **avec repère** (un son représente la cible et l'utilisateur fait converger le son courant vers lui) et **métaphoriques**.
  - **Les stratégies avec repère sont plus précises mais plus lentes.**
  - Pour percevoir la distance, **une sonification non spatiale fait mieux qu'une sonification spatiale**.
  - ➜ **La spatialisation sert à la direction, un paramètre (tempo, hauteur) sert à la distance.** C'est déjà ce que fait VisionAid avec l'espacement des notes. Ce papier le confirme.
- ✅ **Ziemer & Schultheis (2019)**, *A psychoacoustic auditory display for navigation*, J. Multimodal User Interfaces ([arXiv 1912.08609](https://arxiv.org/pdf/1912.08609.pdf)), puis l'extension 3D ([arXiv 1912.00766](https://web3.arxiv.org/pdf/1912.00766)).
  - Deux dimensions de l'espace sont codées par des **attributs sonores perceptivement indépendants** (par exemple battement ou rugosité pour un axe, brillance ou hauteur pour l'autre), **en mono**.
  - Le trajet est aussi court qu'avec la vision, mais plus lent. L'approche vient de la chirurgie guidée.
  - ➜ **Utile pour le mode mono avec un seul écouteur.**
- 📚 **Le « Geiger » ou radar de recul** (débit des bips proportionnel à la proximité) est le schéma le plus intuitif pour la distance. Apple l'utilise dans la « Détection des personnes » avec le LiDAR (bips plus rapides en approchant).

---

## 3. Le son dans l'espace : binaural, HRTF, ambisonie… et la « 8D »

### 3.1 Les techniques

| Technique | Principe | Pour un guidage au casque |
|---|---|---|
| **Panoramique stéréo** (gauche/droite en volume) | ILD seul | Simple, mais le son reste « dans la tête » et l'avant ne se distingue pas de l'arrière. |
| **« 8D audio »** | Panoramique qui tourne + réverbération + parfois un peu de HRTF, sur une musique | **Effet marketing, aucune étude ne l'évalue.** Aucun intérêt pour le guidage. |
| **Binaural paramétrique** (ITD Woodworth + ombre de tête Brown & Duda) | Modèle de tête sphérique | **C'est ce qu'utilise VisionAid** ([binaural.py](../src/visionaid/audio/binaural.py)). Léger et déterministe. Faible pour l'avant/arrière et l'élévation. |
| **Binaural HRTF générique** (KEMAR, CIPIC, base SOFA) | Convolution avec des réponses de tête mesurées | Ajoute les indices du pavillon, donc améliore avant/arrière et élévation. Outils : Steam Audio, Resonance Audio, 3D Tune-In Toolkit, Web Audio `PannerNode` en mode `HRTF`, Apple PHASE / AVAudioEnvironmentNode. |
| **HRTF personnalisée** | Mesure ou estimation à partir de photos de l'oreille (le « Spatial Audio personnalisé » d'Apple via la caméra TrueDepth) | Gain modeste quand la tête est suivie (voir 3.2). |
| **Ambisonie** (ordre 1 à 3), puis décodage binaural | Représentation de tout le champ sonore | Pratique pour une **scène complète** (plusieurs objets) et pour la rotation de tête. |
| **Rendu dynamique avec suivi de tête** | Le son reste fixé dans le monde quand la tête tourne | **Le facteur le plus important**, voir ci-dessous. |

### 3.2 Ce qui améliore vraiment la localisation

- ✅ **Le suivi de tête** est « fondamental » pour réduire les confusions avant/arrière et la sensation de son « dans la tête ». Il compte plus que la personnalisation de la HRTF (RWTH Aachen 2020 ; arXiv 2510.09161, 2025 : avec mouvements de tête, presque plus aucune confusion avant/arrière, quel que soit le rendu). [arXiv](https://arxiv.org/pdf/2510.09161)
- ✅ Une **HRTF générique bien choisie** fait presque aussi bien qu'une HRTF mesurée. La tête KEMAR est plutôt mauvaise : 17 % de confusions avant/arrière, contre environ 8 à 9 % (arXiv 2606.30114, 2026). [arXiv](https://arxiv.org/pdf/2606.30114)
- ✅ **Corriger le spectre d'une HRTF non personnalisée** réduit l'erreur de 22 % et les confusions avant/arrière jusqu'à 66 % (Ngan et al. 2010 ; So et al. 2011).
- 📚 **Un entraînement court** améliore durablement la localisation avec une HRTF qui n'est pas la sienne (Zahorik et al. 2006, effet conservé 4 mois).
- ➜ **Pour VisionAid :** le téléphone est porté sur le torse ou à la main, donc l'IMU donne le cap du corps, pas celui de la tête.
  - Les écouteurs avec capteur de mouvement (AirPods via `CMHeadphoneMotionManager`, certains Android) permettraient un **vrai suivi de tête**.
  - À défaut, encourager l'utilisateur à **« balayer en tournant le corps »** pour lever l'ambiguïté avant/arrière.

### 3.3 Conduction osseuse et écouteurs ouverts

- ✅ La localisation en conduction osseuse (vibreur devant l'oreille) est **comparable à celle d'un casque classique** (Human Factors 2015). Elle est moins bonne si le vibreur est placé derrière l'oreille. On observe aussi un effet d'« attraction » vers la direction du vibreur (Applied Ergonomics 2017, [PubMed 28237013](https://pubmed.ncbi.nlm.nih.gov/28237013/)).
- ✅ Avec SWAN en conduction osseuse, tous les participants réussissent les tâches, avec un léger temps d'adaptation ([Georgia Tech](https://repository.gatech.edu/entities/publication/d22df9f0-06df-4188-8e2b-f1efcc1567fc)).
- ✅ Il existe un dispositif de navigation binaural en conduction osseuse avec détection d'obstacles (Applied Sciences 2021, [MDPI](https://www.mdpi.com/2076-3417/11/8/3356)).
- ⚠️ La réponse en fréquence de la conduction osseuse est **irrégulière** : peu de graves, des résonances. **Il faut tester les sons de VisionAid sur un vrai casque à conduction osseuse** (Shokz…) et pas seulement au casque classique.

### 3.4 Distance perçue

- 📚 Les indices naturels sont le volume, le rapport entre son direct et réverbération, et le filtrage des aigus avec la distance. Au casque, la distance est **mal perçue** (Kolarik et al. 2016, revue). Voir aussi arXiv 2505.18020 (2025) sur la réverbération et la distance. Cela confirme Parseihian : **coder la distance par un paramètre** (tempo), pas par la spatialisation.

---

## 4. Systèmes et produits existants

### 4.1 Guidage et navigation

| Système | Type de son | Ce qu'on en retient |
|---|---|---|
| ✅ **Microsoft Soundscape** (2018‑2023, arrêté, **code ouvert MIT**) | Balise audio 3D en boucle placée sur une destination, annonces vocales spatialisées des lieux autour | Référence du « son ancré dans le monde ». Repris par **VoiceVista** (iOS) et *Soundscape Community*. [MS Research](https://www.microsoft.com/en-us/research/?p=605433) |
| ✅ **Google Project Guideline** (2020, **open source** en nov. 2023) | Un son devient plus fort et **plus dissonant dans l'oreille du côté où l'on dévie** ; d'autres fréquences annoncent un virage ; signal « STOP » si la ligne est perdue ; conduction osseuse | Très proche de la logique de VisionAid. Le **code et le simulateur 3D** sont publics. [Google Research](https://research.google/blog/open-sourcing-project-guideline-a-platform-for-computer-vision-accessibility-technology/) |
| ✅ **SWAN** (Georgia Tech, Walker) | Balises spatialisées non vocales, conduction osseuse | Base de recherche sur le choix des sons de balise et du rayon de validation. [SWAN 2.0](https://wirelessrerc.gatech.edu/sites/default/files/publications/walker_swan2-wirelessrerc-sot2021-proceedings-v16-withalttext.pdf) |
| ✅ **biped.ai** (Suisse, CES 2022) | Harnais avec caméras 3D sur 170°, **prédiction de trajectoire des obstacles**, alertes en audio spatial, conduction osseuse | Ne signale **que ce qui croise la trajectoire** (un vélo à 12 m sur la route, mais pas un objet proche sans risque). Une idée forte. [designboom](https://www.designboom.com/technology/biped-ai-copilot-blind-visually-impaired-people-ces-2022-01-10-2022/) |
| 📚 **BlindSquare, Lazarillo, Ariadne GPS** | Voix, plus quelques sons | Annonces de lieux GPS, très utilisées. |
| 📚 **Apple Loupe** (détection de personnes, de portes) | Bips de plus en plus rapides en approchant, plus la voix | Le modèle grand public du « radar de recul ». |
| 📚 **Seeing AI, Be My AI, Envision** | Voix (description par IA) | Pas de guidage continu, de la description. |
| 📚 **NavCog** (CMU) | Voix tour par tour | Référence du tout vocal en intérieur. |

### 4.2 Substitution sensorielle (« voir avec les oreilles »)

- 📚 **The vOICe** (Meijer 1992) : l'image est balayée de gauche à droite, la hauteur dans l'image donne la hauteur du son, la luminosité donne le volume. Très puissant, mais **des dizaines d'heures d'entraînement** (✅ environ 70 h dans un protocole publié) et un son continu **fatigant**.
- ✅ **EyeMusic** (Amedi) : même principe, mais en notes musicales, avec la **couleur codée par l'instrument**. Plus agréable à écouter ([Frontiers 2023](https://www.frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2023.1058617/pdf)).
- ✅ **Topo-Speech** (2023) : la position d'un objet est donnée par la voix spatialisée qui prononce son nom. Environ 74 % de réussite chez des aveugles **après une seule séance**. ➜ C'est une **fusion voix + espace** très prometteuse.
- ✅ **Effet du bruit ambiant sur ces dispositifs** : [HAL Sorbonne](https://hal.sorbonne-universite.fr/hal-02124943/file/) (*Multisensory Research*). Les performances baissent avec du bruit non pertinent.
- 📚 **Sound of Vision** (projet européen H2020, 2015‑2018) : caméra de profondeur, rendu **audio et haptique** de la scène, plusieurs modes de sonification.
- 📚 **Naviton** ✅ (Bujacz & Strumiłło) : sonification de la scène 3D, testée avec des aveugles.
- 📚 **Écholocation humaine** (Thaler, Daniel Kish) : les clics de langue donnent une perception riche de l'espace. Il existe des travaux sur l'**écholocation assistée** ou synthétique.

### 4.3 Revues à lire en priorité

1. ✅ **Bujacz & Strumiłło (2016)**, *Sonification: Review of Auditory Display Solutions in Electronic Travel Aids for the Blind*, Archives of Acoustics 41(3), 401‑414. [PDF](https://www.journals.pan.pl//Content/102689/PDF/aoa-2016-0040.pdf). **La revue de référence** sur notre sujet.
2. 📚 **Csapó, Wersényi, Nagy, Stockman (2015)**, *A survey of assistive technologies and applications for blind users on mobile platforms*, J. Multimodal User Interfaces.
3. 📚 **Dakopoulos & Bourbakis (2010)**, *Wearable obstacle avoidance electronic travel aids for blind: a survey*, IEEE SMC‑C.
4. 📚 **Hermann, Hunt, Neuhoff (2011)**, *The Sonification Handbook*. **Gratuit en ligne**, chapitres sur les earcons, les icônes auditives et la navigation.
5. ✅ *Spatial Knowledge via Auditory Information for Blind Individuals: Spatial Cognition Studies and the Use of Audio-VR*. [PMC9268803](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9268803/)
6. ✅ *Spatial navigation with horizontally spatialized sounds in early and late blind individuals*. [PMC7909643](https://pmc.ncbi.nlm.nih.gov/articles/PMC7909643/). Les différences entre aveugles précoces et tardifs comptent pour le choix des sons.
7. 📚 **Kolarik et al. (2016)**, *Auditory distance perception in humans: a review*, et sa revue sur l'écholocation.
8. ✅ Cadre de conception 2025 : *Cognitive Load-Aware Framework for Accessible Urban Mobility*. [MDPI](https://www.mdpi.com/2673-2688/7/6/206). Recommande un retour « sélectif, codé dans l'espace, calibré » plutôt que bavard.

### 4.4 Où trouver des témoignages d'utilisateurs

- **AppleVis** (forums et podcasts d'utilisateurs aveugles sur iOS, nombreux retours sur Soundscape et VoiceVista).
- **Liste de diffusion et communauté Soundscape Community**.
- **Podcasts « Double Tap » (AMI Audio) et « Eyes On Success »**.
- **Associations en France** : Fédération des Aveugles de France, **Valentin Haüy** (son pôle technologies), **Voir Ensemble**, et les **instructeurs en locomotion** (ARAMAV, centres de rééducation). Ce sont les meilleures sources pour organiser des entretiens.
- ➜ Recommandation : **10 à 15 entretiens courts** (aveugles précoces et tardifs, malvoyants, utilisateurs de chien guide ou de canne) avant de figer le design sonore.

---

## 5. Où en est VisionAid par rapport à cet état de l'art

| Choix actuel de VisionAid | Ce qu'en dit la littérature |
|---|---|
| Note spatialisée vers l'objectif, intervalle qui se réduit en approchant | ✅ Conforme : direction par la spatialisation, distance par le tempo (Parseihian 2016 ; radar de recul). |
| Exagération des petits angles | ✅ Justifié par le faible pouvoir de discrimination latérale. À rapprocher de l'« exagération des écarts » de Project Guideline. |
| Binaural paramétrique (Woodworth + Brown‑Duda), arrière assourdi | 🟡 Bonne base. Une HRTF mesurée (SOFA) et surtout le **suivi de tête** amélioreraient l'avant/arrière. |
| Son d'exploration distinct, plus doux | ✅ Conforme à la hiérarchie et à l'objectif de réduire la gêne. |
| Alerte grave, non spatialisée, répétée | 🟡 Un son **grave** passe mal en conduction osseuse et se confond avec le bruit de la circulation. L'urgence passe mieux par le **tempo** et la rugosité. À tester. |
| Arrivée : arpège ou voix « vous êtes arrivé » | ✅ Hybride voix + son, conforme. |
| Mode avec un seul écouteur | ❌ Absent. Beaucoup d'utilisateurs portent un seul écouteur. |
| Adaptation au bruit ambiant | ❌ Absente. |

---

## 6. Pistes innovantes pour VisionAid

Classées de la plus simple à la plus prospective. Chaque piste peut être testée avant d'être codée.

### A. Gérer l'attention

1. **Guidage par exception (« le silence = tout va bien »).** Quand le cap est bon, rien, ou un tic très discret au rythme des pas. Le son n'apparaît qu'en cas d'écart, d'obstacle ou d'arrivée. On réduit la fatigue et on libère l'écoute.
2. **Verbosité adaptative.** Le système commence avec voix + son, puis passe progressivement au son seul à mesure que l'utilisateur devient expert ou qu'il refait le même trajet (Ahmetovic 2018‑2019). Un bouton « Qu'est-ce que c'est ? » à la demande déclenche la voix (Mascetti 2016).
3. **Hiérarchie sonore stricte avec ducking**, sur le modèle de la radio aéronautique : alerte > voix > guidage > ambiance. Un seul message à la fois.
4. **Charge cognitive estimée** à partir de la vitesse de marche, des hésitations et du bruit ambiant. Quand la charge monte, on bascule sur le son spatialisé seul (Klatzky 2006).

### B. Rester audible sans couvrir l'environnement

5. **Placer les sons dans les « trous » du spectre ambiant.** Le micro du téléphone analyse le bruit (spectre par bandes de tiers d'octave). On décale le timbre ou le filtre du son de guidage dans les bandes les moins occupées, à l'image des oiseaux qui chantent dans les « niches acoustiques » laissées libres (hypothèse de Krause). **Piste peu explorée dans la littérature sur l'aide aux aveugles. Très innovante.**
6. **Volume adapté au masquage** : quelques dB au-dessus du seuil de masquage calculé, au lieu d'un volume fixe.
7. **Protéger les moments critiques.** Pendant une traversée (détectée ou déclarée), on coupe tout sauf les alertes, pour laisser l'écoute de la circulation intacte.
8. **Sons pensés pour la conduction osseuse** : énergie entre 1 et 4 kHz, pas de grave important, attaques nettes.

### C. Mieux coder l'espace

9. **Son ancré dans le monde avec suivi de tête** (AirPods, ou téléphone porté en pendentif) : le son reste fixé sur l'objet quand on tourne la tête. C'est le principal levier pour l'avant/arrière.
10. **Mode mono sans stéréo** pour l'utilisateur à un seul écouteur. Codage psychoacoustique « à la Ziemer » : un écart à gauche donne un battement lent, un écart à droite une brillance, le bon cap un son pur et consonant.
11. **Repère de cible (« strategy with reference »)** : un son de référence fixe représente la cible et le son courant « s'accorde » sur lui en tournant. La consonance donne le bon cap, comme on accorde une guitare. Plus précis selon Parseihian 2016, et utilisé sous forme de dissonance par Project Guideline.
12. **Élévation par la hauteur** pour les marches, les trottoirs et les obstacles à hauteur de tête (aigu = haut). Les caméras ne gèrent souvent que le plan horizontal.
13. **Doppler et tempo pour le temps avant collision** : un objet qui approche voit son rythme accélérer en fonction du **temps avant contact**, pas de la distance (approche de biped). On ne signale que les trajectoires qui croisent celle de l'utilisateur.

### D. Ajouter du sens sans voix bavarde

14. **Spearcons spatialisés** : « porte », « chaise », « escalier » en 150 à 250 ms, placés à l'endroit de l'objet (dans la lignée de Topo-Speech). On garde le sens en réduisant la durée par 3 ou 4.
15. **Icônes auditives par classe d'objet** : un léger grincement pour une porte, un tintement pour une tasse… Comprises sans apprentissage (Gaver). Combinables avec un timbre par catégorie (sur le modèle de l'instrument pour la couleur dans EyeMusic).
16. **Description par un modèle de langage, mais courte, à la demande et spatialisée** : « trois chaises, une table au fond à droite ». Cela complète le guidage, sans le remplacer.

### E. Sortir des sentiers battus

17. **Musique synchronisée avec la marche** : le podomètre de l'IMU cale le tempo du guidage sur la cadence des pas, et l'écart de cap modifie l'harmonie. Moins fatigant qu'une suite de bips. Il existe des travaux en rééducation (stimulation auditive rythmée), à explorer pour le guidage.
18. **Écholocation virtuelle** : un clic synthétique émis par l'utilisateur sur demande ; la scène 3D vue par la caméra renvoie des « échos » synthétiques (retard et filtrage selon la distance et la matière). On s'appuie sur une compétence que certains aveugles maîtrisent déjà (Thaler, Kish).
19. **« Lampe torche sonore »** : en pointant le téléphone, on entend ce qui se trouve dans le cône de la caméra (une sonification à la vOICe mais **limitée aux objets détectés**, donc peu bruyante).
20. **Son et vibration ensemble** : direction au son, alerte ou validation en vibration, pour les environnements bruyants (Bharadwaj 2019).
21. **Personnalisation par mini-jeux** : 2 minutes d'un jeu de localisation au premier lancement. On choisit la HRTF la mieux perçue parmi 5 à 10, on calibre l'exagération des angles et le volume, et on entraîne l'utilisateur (effet d'apprentissage démontré : Zahorik, Walker & Lindsay).

---

## 7. Propositions de mini-expériences (avant de coder)

| # | Question | Protocole léger |
|---|---|---|
| E1 | Voix ou son pour s'orienter vers un objet, avec une tâche secondaire (compter à rebours) | Reprendre l'idée de Klatzky 2006 : 8 à 10 sujets, mesurer le temps, l'erreur d'angle et la réussite de la tâche secondaire. |
| E2 | Quel timbre se localise le mieux **en conduction osseuse dans un bruit de rue** | 4 timbres (sinus, bruit filtré 1‑4 kHz, clic, note riche en harmoniques) × 8 directions. Mesurer l'erreur et les confusions avant/arrière. |
| E3 | Quelle gêne pour la détection des véhicules | Bruits de passage de véhicules enregistrés + guidage actif ou non. Mesurer le taux de détection. |
| E4 | Mode mono, un seul écouteur | Codage Ziemer contre panoramique. |
| E5 | Acceptabilité sur une longue durée | 20 min de marche, échelle NASA‑TLX et questionnaire de gêne. |

---

## 8. Approfondissement : sons fatigants ou non, sons pour malvoyants, fréquences

### 8.1 Ce qui rend un son fatigant ou désagréable

**Mesures psychoacoustiques de la gêne (Zwicker & Fastl)**
- ✅ Le modèle de *gêne psychoacoustique* combine quatre grandeurs ([Fastl, TUM](https://mediatum.ub.tum.de/download/1138438/1138438.pdf)) :
  - la **sonie** (volume perçu, ISO 532‑1/2) ;
  - l'**acuité** (*sharpness* : beaucoup d'énergie dans l'aigu ; elle ne pénalise qu'au-delà d'environ 1,75 acum) ;
  - la **rugosité** (modulation rapide, maximale vers 70 Hz) ;
  - la **force de fluctuation** (modulation lente, maximale vers 4 Hz).
- ✅ La **tonalité** (son pur ou sifflant) est absente du modèle de Zwicker. La NASA l'a ajoutée en 2024 parce qu'elle augmente fortement la gêne ([NASA TM‑20240003202](https://human-factors.arc.nasa.gov/publications/NASA-TM-20240003202June.pdf)).
- ➜ Ces grandeurs se **calculent** (bibliothèques MoSQITo, Python). On peut donc **noter objectivement chaque son de VisionAid** avant de le tester sur des personnes.

**Les sons « qui grincent »**
- 📚 **Kumar, Forster, Bailey & Griffiths (2008)**, *Mapping unpleasantness of sounds to their auditory representation*, JASA.
- 📚 **Kumar et al. (2012)**, *Features versus feelings*, J. Neurosci.
- Résultat de ces deux études : les sons jugés les plus désagréables (craie sur un tableau, crissement) concentrent leur énergie **entre ~2,5 et 5,5 kHz** et ont une **modulation temporelle entre ~1 et 16 Hz**.
- 📚 Halpern, Blake & Hillenbrand (1986) : enlever les aigus d'un grincement de craie **ne le rend pas moins désagréable**. Ce sont les fréquences moyennes (2 à 4 kHz) qui gênent.
- ⚠️ Cette zone recoupe celle où l'oreille est la plus sensible et qu'on recommande pour être audible (section 2.2). **Il faut de l'énergie vers 2 à 4 kHz, mais sans modulation rugueuse ni contenu « crissant ».** Un son harmonique, avec une attaque douce et une décroissance naturelle, convient ; un bruit grinçant modulé, non.

**Consonance et timbre**
- ✅ Marjieh et al. (2024, *Nature Communications*) montrent que le **timbre change les intervalles jugés agréables** : la consonance n'est pas seulement une question de rapports de fréquences. [PMC11258268](https://pmc.ncbi.nlm.nih.gov/articles/PMC11258268)
- ✅ Les sons à spectre **harmonique** (comme les instruments ou la voix) sont à la base de la sensation de consonance (Bowling & Purves, [PMC2885564](https://pmc.ncbi.nlm.nih.gov/articles/PMC2885564)).
- ✅ Pour des sinusoïdes, la **préférence baisse quand la fréquence moyenne monte**, pour tous les intervalles et tous les groupes testés ([arXiv 2510.01201](https://arxiv.org/pdf/2510.01201v1)).
- ➜ Pour le guidage de fond, il vaut mieux des **notes harmoniques plutôt médium** que des bips aigus purs.

**Répétition, habituation et « fatigue d'alarme »**
- ✅ Dans la recherche sur les alarmes médicales, **introduire de la variation dans le rythme** des sons réduit la gêne **sans nuire à leur reconnaissance** ([PMC3628049](https://pmc.ncbi.nlm.nih.gov/articles/PMC3628049)).
- ✅ Des **timbres d'instruments ou percussifs** restent plus utiles dans le vacarme et limitent la fatigue d'alarme ([Scientific American](https://www.scientificamerican.com/article/making-alarms-more-musical-can-save-lives/) ; thèse McMaster 2024, [Mattar](https://macsphere.mcmaster.ca/bitstream/11375/29792/1/Mattar_Maya_2024.pdf)).
- ✅ **N'importe quel son finit par être ignoré s'il se déclenche souvent à tort.** La fatigue dépend du *taux de fausses alertes* autant que du son lui-même.
- ➜ Pour VisionAid, la **fiabilité de la détection d'obstacles** compte donc autant que le choix du son d'alerte.

**Monotonie et durée d'écoute**
- ✅ Les utilisateurs aveugles décrivent une **fatigue mentale avec les voix « plates »** des lecteurs d'écran. Une narration plus expressive (VoxVista, 20 participants aveugles) améliore l'engagement et la compréhension ([Bragg CHI 2018 et travaux liés](https://wildlab.cs.washington.edu/Publications_files/Bragg_CHI2018.pdf), [ODU](https://digitalcommons.odu.edu/computerscience_fac_pubs/442)).
- ✅ Dans les centres de sécurité informatique, la **fatigue d'écoute** limite le temps pendant lequel on supporte une sonification. Un usage **ponctuel** paraît plus réaliste qu'une écoute continue ([arXiv 1807.06706](https://arxiv.org/pdf/1807.06706)).
- ✅ L'**esthétique** d'un affichage sonore joue un rôle direct dans la fatigue et la gêne, mais un son trop « musical » peut distraire de l'information ([arXiv 1311.5426](https://arxiv.org/pdf/1311.5426)).
- ✅ **vOICe (substitution sensorielle)** : très peu d'utilisateurs l'adoptent sur la durée, seulement une poignée d'experts. Les difficultés citées sont de **séparer plusieurs sons simultanés**, la surcharge dans les scènes encombrées et la longueur de l'entraînement ([SoundSight, JMUI 2021](https://link.springer.com/article/10.1007/s12193-021-00376-w) ; [Bertram & Stafford 2016](https://eprints.whiterose.ac.uk/101090/1/bertram16.pdf)).
- ➜ **Un son à la fois, quelques sources au maximum, des silences.**

**Règles de conception classiques des alarmes (📚, à vérifier)**
- **Patterson (1982, Civil Aviation Authority)** :
  - impulsions de **100 à 150 ms** avec **montée et descente de 20 à 30 ms**, pour éviter l'effet de sursaut ;
  - au moins **4 harmoniques entre 0,5 et 4 kHz** ;
  - niveau de **15 à 25 dB au-dessus du seuil de masquage**, pas davantage (au-delà, le son effraie et gêne).
- **ISO 7731** (signaux de danger) : composantes entre **500 et 2 500 Hz**, avec de l'énergie sous 1 500 Hz pour les personnes malentendantes. Le signal doit dépasser le seuil de masquage d'environ 13 dB par bande critique, ou 15 dB par tiers d'octave.
- **IEC 60601‑1‑8** (alarmes médicales) : fondamentale entre **150 et 1 000 Hz**, au moins 4 harmoniques entre 300 et 4 000 Hz.

### 8.2 Sons conçus pour les personnes aveugles : les feux sonores piétons

Ce sont les sons conçus pour des aveugles les plus normalisés et les plus testés. C'est une référence directe pour VisionAid.

- ✅ **Signal « traversez »** (norme américaine MUTCD, États) : **plusieurs fréquences, dominante à 880 Hz**, impulsions de 0,15 s répétées toutes les 0,15 s (8 à 10 tics par seconde). [Delaware](https://regulations.justia.com/states/delaware/title-2/2000/2400/2402/part-4/chapter-4e/section-4e-11)
- ✅ **Tonalité de repérage du bouton** (*locator tone*) :
  - **0,15 s au maximum, une fois par seconde** ;
  - **2 à 5 dB seulement au-dessus du bruit ambiant**, et **ajustée automatiquement au bruit** ;
  - audible uniquement à **2 à 4 m** ;
  - un fabricant utilise une onde carrée adoucie à 800 Hz ou un **clic de 50 ms**.
  - Sources : [walkinginfo.org](https://www.walkinginfo.org/aps/3-7), [Access Board](https://www.access-board.gov/files/research/APS-common-problems.pdf).
- ➜ **C'est exactement la philosophie recommandée plus haut** : un son bref, rare, juste au-dessus du bruit et qui s'adapte à lui. On peut s'en inspirer directement pour le « son de balise » de VisionAid.
- 📚 En France, les feux sonores sont déclenchés à la demande par une **télécommande universelle** (norme NF S 32‑002) et donnent un message vocal ou un son. C'est un bon exemple de **son à la demande** plutôt que permanent.

### 8.3 Fréquences : récapitulatif chiffré

| Zone de fréquence | Rôle / constat | Conséquence pour le design |
|---|---|---|
| **50–200 Hz** | Roulement des pneus, poids lourds, carrefours (✅ [JAES 2025](https://reference-global.com/2/v2/download/article/10.2478/jaes-2025-0037.pdf)). Mal restitué en conduction osseuse. | Ne pas y mettre d'information. |
| **300–1 000 Hz** | **Pic du bruit de circulation** mixte (✅ [Environment International 2019](https://doaj.org/article/50e5b3b2247e4595966c53766caf5bc0) : maximum moyen à 1 kHz). Indice ITD efficace. Feux piétons à 880 Hz. | Une fondamentale dans cette zone est audible et localisable, mais **en concurrence avec la circulation**. Il faut des harmoniques au-dessus. |
| **1–2 kHz** | Zone de transition ITD/ILD. Bande de la parole. | Bonne zone pour le **corps** d'un son de guidage, à baisser pendant la voix. |
| **2–4 kHz** | **Sensibilité maximale de l'oreille**. Zone la plus « désagréable » si le son est modulé ou rugueux (📚 Kumar). | Mettre des **harmoniques** ici pour l'audibilité, **sans rugosité**. Réserver la rugosité aux alertes. |
| **4–16 kHz** | **Indices du pavillon** : avant/arrière, élévation. **Première zone perdue avec l'âge** (presbyacousie). Conduction osseuse limitée. | Utile pour la localisation chez les jeunes. **Ne pas en dépendre seul**. |

- ✅ **Largeur de bande** : les stimuli **de plus d'une octave** se localisent le mieux (erreur d'environ 6 à 7°), quelle que soit leur fréquence centrale. Les sons purs donnent une **précision moindre et des écarts importants d'une personne à l'autre** ([Yost & Zhong, bande passante](https://www.bohrium.com/paper-details/sound-source-localization-identification-accuracy-bandwidth-dependencies/814683735180967936-582)).
- ✅ Un **train de clics à 100 Hz** devient **moins bien localisé au-delà d'environ 70 dB**, alors qu'un bruit large bande reste stable ([Georgia Tech](https://repository.gatech.edu/entities/publication/51cdb3b4-ceff-4839-b34a-1b34452643be)). Pour un clic répété rapidement, c'est surtout le **premier clic** qui donne la direction (effet de précédence, [PMC3254714](https://pmc.ncbi.nlm.nih.gov/articles/PMC3254714)).

### 8.4 Un point souvent oublié : beaucoup de malvoyants entendent aussi moins bien

- ✅ Chez les plus de 71 ans aux États-Unis (étude NHATS, avec tests objectifs), **22 % ont une double perte sensorielle** (vue et audition), et **59 % après 90 ans**. [PMC8601132](https://pmc.ncbi.nlm.nih.gov/articles/8601132)
- ✅ La combinaison la plus fréquente de troubles sensoriels est **audition + vision** (17 % dans la cohorte BLSA, 50 % dans ARIC). [PMC10922129](https://pmc.ncbi.nlm.nih.gov/articles/PMC10922129/)
- 📚 La malvoyance touche surtout des personnes âgées (DMLA, glaucome). La **presbyacousie** fait perdre d'abord les **aigus (au-dessus de 2 à 4 kHz)** et s'accompagne souvent d'un **recrutement** : les sons forts deviennent vite pénibles.
- ➜ Conséquences :
  1. ne pas coder une information importante **uniquement dans l'aigu** ;
  2. éviter les **volumes forts** et préférer un volume réglé sur le bruit ambiant ;
  3. permettre un **réglage de la courbe de fréquence** (ou s'appuyer sur les réglages d'accessibilité audio du téléphone) ;
  4. tenir compte des **aides auditives** (diffusion Bluetooth vers l'appareil auditif ; la spatialisation peut alors être faussée).

### 8.5 Recommandations concrètes pour les sons de VisionAid

| Paramètre | Recommandation | Base |
|---|---|---|
| Durée d'un son de guidage | 80 à 200 ms | Patterson, feux piétons |
| Enveloppe | Attaque 10 à 30 ms, décroissance naturelle (type percussion ou pincé), jamais de bord net | Patterson ; évite les clics et le sursaut |
| Spectre | Fondamentale 400 à 1 000 Hz + harmoniques jusqu'à 4 à 8 kHz (largeur de plus d'une octave) | Localisation large bande ; robuste à la presbyacousie et à la conduction osseuse |
| Rugosité / modulation | Aucune pour le guidage ; **réservée aux alertes** | Zwicker/Fastl ; Kumar ; urgence (Edworthy) |
| Niveau | 3 à 10 dB au-dessus du bruit ambiant mesuré, plafonné | Feux piétons (2 à 5 dB) ; Patterson (au maximum 15 à 25 dB pour les alertes) |
| Répétition | Pas de son continu. Rythme lié à la distance. **Silence quand le cap est bon** | Fatigue d'écoute ; habituation |
| Variation | Légères variations de timbre, de hauteur ou de rythme d'un son à l'autre | Alarmes médicales : moins de gêne, reconnaissance intacte |
| Hauteur | Médium plutôt qu'aigu pour le fond | Préférence décroissante avec la fréquence (sinusoïdes) |
| Alerte | Plus rapide, plus rugueuse ou dissonante, mais brève. Le grave seul est à éviter (masqué par la circulation, mal rendu en conduction osseuse) | Edworthy ; JAES 2025 |
| Évaluation | Calcul automatique de sonie, acuité, rugosité et tonalité (MoSQITo) + NASA‑TLX + questionnaire de gêne après 20 min | Zwicker/Fastl ; NASA 2024 |

---

## 9. Ce que font les produits existants avec la voix et le son (novembre 2026)

> Sources : sites des fabricants, presse tech, forums d'utilisateurs (AppleVis). Les forums donnent des **témoignages**, pas des mesures. Les fonctions changent vite, il faut revérifier avant de citer.

### 9.1 Les lunettes connectées : description à la voix, pas guidage

| Produit | Ce qu'il fait côté audio | Guidage ? |
|---|---|---|
| ✅ **Envision Glasses + assistant « Ally »** | **Assistant vocal conversationnel** : on lui pose une question à voix haute, on peut l'interrompre. Lecture de texte, reconnaissance de visages, description de scène, réponses rapides. Ally est disponible sur toutes les éditions depuis août 2025. | **Non.** Aide contextuelle (menus d'aéroport, commandes de siège…), pas de guidage pas à pas. Envision **déconseille d'utiliser des lunettes comme outil principal de navigation**. [Envision](https://www.letsenvision.com/blog/ally-ai-assistant-sightcity-2025), [support](https://support.letsenvision.com/hc/en-us/articles/32029669353873-Ally-on-Envision-Glasses), [presse 2026](https://tribune.com.pk/story/2585783/smart-glasses-find-purpose-among-blind-users) |
| ✅ **Ally Solos** (Envision + Solos) | Même assistant Ally sur des lunettes audio plus légères. | **Pas encore de navigation intégrée** d'après l'équipe (AppleVis Extra #110). Un comparatif parle de consignes relayées depuis les applis de navigation du téléphone. [AppleVis](https://www.applevis.com/podcasts/applevis-extra-110-envision-ally-solos-smart-glasses), [Android Police](https://www.androidpolice.com/ally-solos-glasses-use-ai-to-help-blind-people-navigate-the-world/) |
| ✅ **Ray-Ban / Oakley Meta** | Commandes vocales « regarde et décris », « regarde et lis ». **Appel d'un bénévole Be My Eyes**, qui voit par la caméra et répond dans les **haut-parleurs ouverts**. 📚 Depuis 2025, un réglage « réponses détaillées » et le mode « Live AI » (conversation continue) existent. | **Non.** L'American Foundation for the Blind note que ces lunettes **ne sont pas conçues pour les aveugles** et que Be My Eyes AI n'y fonctionnait pas à l'automne 2025. [Be My Eyes](https://www.bemyeyes.com/be-my-eyes-smartglasses/), [AFB](https://afb.org/aw/fall2025/meta-glasses-review), [Discover Sight](https://discoversight.com/meta-ray-ban-glasses-for-blind-users/) |
| ✅ **Google / Android XR (Gemini), précommandes le 12/11/2026** | **« Guided Vision »** : descriptions audio conversationnelles (petits caractères, retrouver ses clés, disposition d'une pièce, écrans d'appareils). Accès à un **interprète humain Aira** à la voix (« Hey Gemini, open Aira Explorer »). Itinéraire **Google Maps tour par tour à la voix**. | **Explicitement non** pour la mobilité. Google précise que Guided Vision n'est **ni une aide à la mobilité ni un substitut à la canne**, et ne sert **ni à la navigation ni à la détection d'obstacles**. [Google blog](https://blog.google/innovation-and-ai/technology/xr-ar/google-intelligent-eyewear-collections-pre-order/), [Google Store](https://store.google.com/us/magazine/intelligent-eyewear-xr-glasses?hl=en-US), [AppleInsider](https://appleinsider.com/articles/26/11/12/googles-ai-smart-glasses-work-with-iphone-preorders-are-live) |
| ✅ **EchoVision (AGIGA)** | Caméra grand angle de 110°, **IA proactive** qui décrit sans attendre qu'on demande, directions de transport en commun, lecture, intégration de Be My Eyes et Aira. **Retours en vibration** pour la batterie, **alerte sonore** pour retrouver l'étui. | Directions de transport surtout. Les utilisateurs se plaignent d'**autonomie, de prix et de retards**. [AppleVis](https://www.applevis.com/comment/193969), [Double Tap](https://doubletaponair.com/weekend-exploring-the-features-of-agiga-echo-vision-wearable-tech-2/), [NextBigFuture](https://www.nextbigfuture.com/2026/04/echovision-ai-glasses-for-the-blind-and-low-vision-users.html) |
| ✅ **Aira** (service) | Un **agent humain** voit le flux vidéo des lunettes ou du téléphone et guide **à la voix**. | Oui, mais par un humain, de façon payante et verbale. |
| 📚 **OrCam MyEye** | Pince sur la branche des lunettes : lecture en pointant du doigt, visages, billets, objets. **Voix uniquement.** | Non (une fonction d'orientation a été annoncée, statut incertain). |

**À retenir sur les lunettes.** Toutes les grandes lunettes (Meta, Google, Envision, Solos, EchoVision) sont **centrées sur la voix et la description à la demande**, par IA ou par un humain. **Aucune ne propose de guidage sonore spatialisé ni de signal continu vers une cible.** Leurs fabricants refusent même de les présenter comme aides à la mobilité, pour des raisons de responsabilité et de fiabilité.

### 9.2 Les dispositifs de mobilité : son non verbal, vibration

| Produit | Son / voix | Ce qu'on en retient |
|---|---|---|
| ✅ **biped NOA** (gilet porté comme un sac à dos, caméras sur 170°, de la tête au sol, de jour comme de nuit) | Obstacles en **audio spatial par conduction osseuse**, codés sur 3 dimensions : **le volume monte en approchant, la stéréo donne la direction, la hauteur du son indique la hauteur de l'obstacle**. Navigation GPS et descriptions IA par la voix. Ne signale que les objets **sur la trajectoire** (prédiction de mouvement). | **C'est le produit le plus proche de VisionAid.** Retours d'utilisateurs mitigés sur l'**apparence** et le port sur les épaules. Un utilisateur dit que l'appareil « vibrait constamment » lors de son test. [AppleVis SightCity 2025](https://applevis.com/comment/190102), [AppleVis 2024](https://www.applevis.com/comment/172442) |
| ✅ **.lumen Glasses** (Roumanie, CES 2025-2026) | **Vibrations sur le front** pour la direction, même pour de petits changements. **Alertes vocales** pour des situations (« passage étroit »). Haut-parleurs dirigés vers les oreilles. | Choix assumé : **le toucher pour le guidage continu, la voix pour les événements**. Discret pour l'entourage. Prix élevé. [Engadget](https://www.engadget.com/wearables/dotlumens-haptic-headset-could-help-blind-people-navigate-181532099.html), [New Atlas](https://newatlas.com/wearables/dotlumen-ai-glasses-blind-independence), [designboom](https://www.designboom.com/technology/forehead-glasses-assist-blind-people-move-around-without-guide-dog-lumen-12-30-2025/) |
| ✅ **Glidance Glide** (petit robot à roues tenu par une poignée) | Guidage **par vibrations dans la poignée**, plus un haut-parleur et du Bluetooth pour les consignes audio. Un mode « directif » emmène vers une destination. | Le robot **tire physiquement** l'utilisateur, donc presque pas besoin de son pour la direction. Encore en précommande ou en bêta. [Robot Report](https://www.therobotreport.com/rbr50-company-2024/glidance-provides-independence-to-visually-impaired-individuals/), [Podfeet CSUN 2025](https://www.podfeet.com/blog/2025/06/csun-2025-glidance/), [MS Research](https://www.microsoft.com/en-us/research/?p=911676) |
| ✅ **WeWALK Smart Cane 2** | Obstacles en hauteur : **bips qui accélèrent comme un radar de recul**, ou vibration au choix. **Assistant vocal IA** (ChatGPT) : itinéraire pas à pas et description de l'environnement. Haut-parleur dans la canne, ou écouteurs / **aides auditives** en Bluetooth. | Hybride classique : **sons pour l'urgence, voix pour le sens**. [Engadget](https://www.engadget.com/home/the-wewalk-smart-cane-2-could-be-one-of-ais-few-good-use-cases-at-ces-2025-182020074.html), [AppleVis](https://www.applevis.com/comment/188319), [RNIB](https://shop.rnib.org.uk/products/wewalk-smart-cane-2-ai) |
| 📚 **Sunu Band** | Bracelet à ultrasons, **vibration seulement**. | Le toucher sans le son. |

### 9.3 Les applications de téléphone

| Application | Son / voix |
|---|---|
| ✅ **Seeing AI, canal « World »** (Microsoft, iPhone avec LiDAR) | **Réalité augmentée sonore** : les objets autour de soi sont **annoncés par une voix spatialisée** à leur position. « Find My Things » permet d'apprendre ses propres objets puis de **suivre des repères sonores** pour les retrouver. [App Store](https://apps.apple.com/app/id999062298) |
| 📚 **Apple Loupe** (détection de personnes, de portes ; LiDAR) | Au choix : **sons qui accélèrent en approchant**, vibrations ou distance énoncée. La détection de portes **décrit à la voix** la porte, la poignée et l'écriteau. |
| ✅ **Microsoft Soundscape → VoiceVista** | **Balise audio 3D** vers une destination et annonces spatialisées des lieux. Voir section 4.1. |
| 📚 **Google Lookout** | Description continue **à la voix** (texte, objets, billets). Pas de spatialisation documentée. |
| ✅ **Project Guideline** (Google) | Son **dissonant dans l'oreille du côté où l'on dévie**. Voir section 4.1. |
| 📚 **BlindSquare, Lazarillo** | Voix (annonces GPS), plus des sons de notification. |

### 9.4 Ce qu'on peut en conclure pour VisionAid

1. **Un partage assez net :**
   - **Les lunettes = la voix et la description**, à la demande (IA générative ou humain).
   - **La mobilité = le son non verbal ou la vibration**, en continu : NOA, .lumen, Glide, WeWALK, la Loupe d'Apple.
   - C'est exactement ce que dit la recherche (sections 1 et 2) : **le son ou le toucher pour « où », la voix pour « quoi »**.
2. **La niche peu occupée : guider jusqu'à un objet précis par un son spatialisé.**
   - Les lunettes **disent** où est l'objet (« les clés sont à gauche sur la table ») mais **ne guident pas la main ni le pas**.
   - Seuls Seeing AI (Find My Things, avec LiDAR) et NOA (pour les obstacles, pas les cibles) s'en approchent.
   - **VisionAid, avec un guidage spatialisé continu vers une cible et un matériel bon marché, se place dans ce trou.**
3. **Le codage de NOA confirme les choix de la littérature** : stéréo pour la direction, volume ou tempo pour la distance, hauteur du son pour la hauteur. C'est une validation sur le terrain de la piste 12 (élévation par la hauteur).
4. **Le choix de .lumen** (toucher pour le continu, voix pour les événements) est une alternative sérieuse au tout sonore. Elle a l'avantage de **ne rien masquer** à l'oreille (section 1.3).
5. **Les plaintes d'utilisateurs** portent rarement sur le son lui-même. Elles portent sur **l'autonomie, le prix, le poids ou le port, le regard des autres et la fiabilité**. Une solution « matériel bon marché + téléphone » répond directement à plusieurs de ces points.
6. **La responsabilité** : Google et Envision **refusent** de présenter leurs lunettes comme aides à la mobilité. VisionAid doit se positionner clairement (complément de la canne ou du chien, pas un remplacement) et soigner la **fiabilité des alertes** (section 8.1, fatigue d'alarme).
7. **Une piste concrète** : les lunettes à **haut-parleurs ouverts** (Meta, Google, Solos) ont deux haut-parleurs près des oreilles et une caméra frontale qui suit la tête. **Elles pourraient servir de matériel à un guidage spatialisé à la VisionAid**, ce qu'aucune ne fait aujourd'hui. Les kits de développement d'Android XR et de Meta sont à surveiller.

---

## Sources consultées (✅)

- Klatzky et al. 2006 : https://umaine.edu/vemi/wp-content/uploads/sites/220/2016/06/Klatzky-etal2006-Cognitive-Load-of-Navigating-Without-Vision-jep-a.pdf
- Giudice et al. 2008 : https://umaine.edu/vemi/wp-content/uploads/sites/220/2016/08/Giudice-etal2008-Environmental-Learning-without-Vision-Effects-of-Cognitive-Load-on-Interface-Design-vision08.pdf
- Mascetti et al., traversée sonifiée : https://arxiv.org/pdf/1506.07272
- Ahmetovic et al., rotations IJHCS 2023 : https://ludovico.lim.di.unimi.it/download/papers/IJHCS2023.pdf
- Ahmetovic et al., expertise W4A 2019 : https://ri.cmu.edu/?p=121341
- Ahmetovic et al. 2023, lecteurs d'écran et environnement sonore : https://iris.unito.it/bitstream/2318/2016332/1/ahmetovic2023enhancing.pdf
- Parseihian et al. 2016 : https://typeset.io/pdf/comparison-and-evaluation-of-sonification-strategies-for-1dpfi7jxvq.pdf
- Walker & Lindsay 2006 : https://core.ac.uk/download/19562103.pdf
- SWAN 2.0 : https://wirelessrerc.gatech.edu/sites/default/files/publications/walker_swan2-wirelessrerc-sot2021-proceedings-v16-withalttext.pdf
- Spearcons : https://core.ac.uk/download/4718939.pdf
- Bujacz & Strumiłło 2016 : https://www.journals.pan.pl//Content/102689/PDF/aoa-2016-0040.pdf
- Ziemer & Schultheis : https://arxiv.org/pdf/1912.08609.pdf, https://web3.arxiv.org/pdf/1912.00766
- Bharadwaj et al. 2019 : https://pmc.ncbi.nlm.nih.gov/articles/PMC6930908
- Conduction osseuse : https://repository.gatech.edu/entities/publication/d22df9f0-06df-4188-8e2b-f1efcc1567fc, https://pubmed.ncbi.nlm.nih.gov/28237013/, https://www.mdpi.com/2076-3417/11/8/3356
- HRTF et suivi de tête : https://arxiv.org/pdf/2510.09161, https://arxiv.org/pdf/2606.30114, https://www.ieda.ust.hk/dfaculty/so/pdf/Ngan-et-al-2010-Ergonomics.pdf
- Urgence des alarmes : https://researchportal.plymouth.ac.uk/en/publications/designing-urgency-into-auditory-warnings-using-pitch-speed-and-lo/, https://www.mcgill.ca/mpcl/files/mpcl/suied_2008_jepappl.pdf
- Project Guideline : https://research.google/blog/open-sourcing-project-guideline-a-platform-for-computer-vision-accessibility-technology/
- Soundscape : https://www.microsoft.com/en-us/research/?p=605433, VoiceVista : https://apps.apple.com/app/6450388413
- biped : https://www.designboom.com/technology/biped-ai-copilot-blind-visually-impaired-people-ces-2022-01-10-2022/
- EyeMusic 2023 : https://www.frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2023.1058617/pdf
- Bruit et substitution sensorielle : https://hal.sorbonne-universite.fr/hal-02124943/
- Piétons aveugles et bruit de la circulation : https://pmc.ncbi.nlm.nih.gov/articles/PMC2814321, https://pmc.ncbi.nlm.nih.gov/articles/PMC3046409
- Cognition spatiale et audio‑VR : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9268803/
- Aveugles précoces et tardifs : https://pmc.ncbi.nlm.nih.gov/articles/PMC7909643/
- Cadre de conception 2025 : https://www.mdpi.com/2673-2688/7/6/206
- Distance et réverbération : https://arxiv.org/pdf/2505.18020
