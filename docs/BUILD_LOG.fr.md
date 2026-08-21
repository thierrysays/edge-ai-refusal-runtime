# Journal de construction

Ce qui a été construit, dans quel ordre, et ce qui était faux en chemin. Tenu
parce que la matière intéressante d'un projet de gouvernance, ce sont les
arbitrages — et qu'un arbitrage n'est lisible que tant que ses raisons sont
fraîches.

---

## 21 août 2026 — Jour 1

### Point de départ

Cinq cartes, commandées entre juin et août 2026 : une UNO Q 4 Go, une VENTUNO Q,
une UNO R4 WiFi avec les nœuds Modulino du Plug and Make Kit, un Alvik et une
Nesso N1. Toutes ne sont pas encore sur l'établi — la VENTUNO Q est partie le
20 août.

Cette contrainte a fixé la première décision : **la simulation d'abord**.
Attendre le matériel aurait produit des contrôles façonnés par ce que la
première carte rendait facile, soit exactement la mauvaise direction de
dépendance pour quelque chose destiné à tourner sur un parc. → ADR 0005.

### Ordre de construction

1. `canonical.py` — avant tout ce qui serait haché. Clés triées, aucun espace
   non significatif, flottants non finis rejetés. Une empreinte ne vaut que le
   déterminisme des octets qui la produisent.
2. `clock.py` — temps injectable. Une preuve qu'on ne peut rejouer est une
   anecdote.
3. `registry/` — schéma de fiche de modèle, signature Ed25519, porte d'admission.
4. `journal/` — primitives Merkle, puis la chaîne, puis le vérificateur
   indépendant.
5. `policy/` — décisions, moteur, budgets.
6. `oversight/` — canaux d'arrêt, superviseur.
7. `marking/` — provenance article 50.
8. `hal/` — cellule simulée, puis profils de cartes.
9. `agent/` — le runtime qui câble les cinq contrôles dans l'ordre, puis le
   scénario.
10. `cli.py` — produire la preuve, vérifier la preuve : deux commandes distinctes.

Les tests ont été écrits en même temps que chaque module, non après. La suite
atteint 113 tests, dont la grande majorité sont négatifs : une porte qui admet un
bon modèle ne démontre rien.

### Transplantation de signature

La première version de l'enveloppe signait directement la fiche de modèle. C'est
transplantable, et surtout cela ne dit rien de *qui* a signé ni *quand*.

Remplacé par une structure à signer qui lie l'empreinte de la fiche,
l'identifiant de clé du signataire et l'horodatage de signature. Les rôles sont
ensuite résolus depuis le magasin de confiance au moment de la vérification,
jamais lus dans l'enveloppe — ce qui ferme la confusion de rôles par la même
occasion. `test_signature_cannot_be_transplanted_between_cards` et
`test_two_signatures_from_the_same_role_do_not_form_a_quorum` verrouillent les
deux.

### Le manifeste circulaire

Le manifeste de provenance portait initialement l'empreinte de l'entrée de
journal qui enregistrait l'inférence. Or cette entrée porte l'empreinte du
manifeste. Ce n'est pas seulement inélégant : c'est incalculable. Je ne l'ai vu
qu'après avoir écrit un `object.__setattr__` sur une dataclass gelée pour
rapiécer le manifeste après coup — le genre de ligne qu'il faut lire comme une
alarme, pas comme un contournement.

Résolu en rendant le lien unidirectionnel : journal → manifeste. Un auditeur qui
trouverait un manifeste contenant l'empreinte de l'entrée qui enregistre
l'empreinte de ce même manifeste aurait raison de se défier du fichier entier.

### Le profil qui refuse

Écrire `hal/devices.py` honnêtement a produit le résultat le plus utile de la
journée. L'UNO R4 WiFi est un microcontrôleur, pas un ordinateur : pas de
stockage durable en ajout seul, donc elle ne peut pas porter le journal
d'inférence, donc son profil ne déclare pas `inference_journal`, donc une fiche
de modèle à haut risque y est **refusée**.

Cette conclusion n'a pas été conçue. Elle est tombée de la description exacte du
matériel, et c'est précisément le type de constat que l'on recouvre lorsqu'on
écrit le code contre la carte d'abord et la documentation ensuite. Elle est
désormais `test_runtime_without_stop_channel_cannot_run_a_high_risk_model` et la
ligne `uno-r4-wifi` de `gea admit`.

### Choisir une graine, et le dire

La première exécution de démonstration était sans intérêt : quatorze pièces, deux
défauts, aucune escalade pour confiance faible, aucune série de trois. Tous les
contrôles étaient corrects et aucun des intéressants ne s'est déclenché.

J'ai cherché dans l'espace des graines une exécution qui exerce à la fois le
chemin d'escalade et l'arrêt sur série de défauts, et retenu la graine 12 avec un
taux de défaut de 0,35. Choisir une graine pour faire fonctionner une
démonstration n'est malhonnête que si on ne le dit pas : `DEMO_SEED` porte un
commentaire qui le dit explicitement, et les tests épinglent d'autres graines, y
compris des exécutions où il ne se passe rien.

### Deux lacunes laissées ouvertes

Les deux sont enregistrées comme *acceptées*, non comme *reportées* :

- **Pas de racine de confiance matérielle.** Les clés de signature sont en clair
  dans un fichier JSON. Les chiffrer avec une phrase de passe rangée à côté ne
  changerait rien au modèle de menace tout en donnant l'apparence du contraire.
  → ADR 0006.
- **Pas d'ancrage externe.** Les points de contrôle sont produits exactement sous
  la forme qui fermerait la fenêtre de troncature — un intervalle, une racine,
  une signature, aucune charge utile — et délibérément non transmis, parce que le
  choix du témoin appartient à qui exploite le parc. → ADR 0007.

Les deux figurent dans le tableau « claims deliberately not made » de la
cartographie des contrôles. Un dépôt de gouvernance qui n'annonce que ce qu'il
fait bien est une plaquette commerciale.

### État en fin de journée

- 113 tests, tous verts, 0,5 s
- `gea demo` produit un journal de 34 entrées avec un point de contrôle signé
- `gea verify` re-dérive la chaîne indépendamment et nomme le numéro de séquence
  quand elle casse
- Compteurs du scénario : 10 inférences, 11 requêtes, 7 autorisées,
  **4 refusées**, 1 escaladée et approuvée
- Rien de démontré sur matériel à ce stade

### Suite

1. Porter le canal d'arrêt sur l'UNO Q avec le Modulino Latch Relay en Qwiic, et
   mesurer si un processus Python tué laisse réellement le relais désexcité.
   Tout le reste est théorie tant que cela n'est pas observé.
2. Remplacer une estimation d'`energy_model` par une mesure et constater l'écart.
   L'ADR 0008 suppose des budgets dimensionnés par la mesure.
3. Déplacer la boucle d'actionnement sur le STM32H5 de la VENTUNO Q sous Zephyr,
   afin qu'un blocage Linux ne puisse pas maintenir la machine en marche.

---

## 2026-08-21 — Jour 1, plus tard : deux choses qui ne sont pas ce dépôt

### Le point de départ

Deux chantiers étaient constamment décrits comme « faisant partie du
programme » sans faire partie de *celui-ci* : l'exploitation de parc — mise à
jour OTA, retour arrière, SBOM, builds reproductibles, orchestration sur nœuds
contraints — et un banc de mesure pour la puissance, la latence et le bridage
thermique sous inférence soutenue.

Les deux utilisent tout le banc plutôt qu'une carte en particulier. Les deux sont
agnostiques du matériel là où ce dépôt ne l'est délibérément pas :
`hal/devices.py` nomme cinq cartes précises, parce que la barrière d'admission
doit savoir ce que chacune sait faire respecter. Un banc de mesure qui nomme cinq
cartes est un script de benchmark pour un laboratoire.

Donc : deux dépôts séparés, et → ADR 0011 pour consigner pourquoi, et à quel
coût.

### `measurement-harness`

Agnostique de l'instrument par construction. Le cœur connaît `open` / `read` /
`close` renvoyant des volts et des ampères, rien d'autre — une sonde de shunt,
une alimentation de laboratoire en SCPI, un analyseur USB-C et un générateur
synthétique ont la même forme.

La règle autour de laquelle tout est construit : **un chiffre qui n'a pas été
mesuré ne sort jamais étiqueté comme tel.** `provenance.kind` est dérivé de
l'instrument, jamais affirmé par l'appelant, et l'export refuse un rapport
synthétique sauf demande explicite — auquel cas `source` porte
`synthetic — not measured` de façon permanente. Cette règle existe à cause de
l'invariant 10 de ce dépôt : chaque `energy_model` y est une estimation, et la
seule chose pire qu'une estimation est une estimation qui a perdu son étiquette
entre deux systèmes.

Trois constats en cours de route, aucun anticipé :

- **Intégrer, pas moyenner.** Watts moyens × durée n'est juste que si
  l'échantillonnage est uniforme, et il l'est d'autant moins sous la charge
  soutenue que l'on cherche justement à caractériser. `max_gap_s` est publié pour
  qu'un lecteur voie quand l'échantillonneur a été privé de temps.
- **Un échantillonneur en ligne ne peut pas voir une inférence.** Lire entre deux
  unités de travail est exactement reproductible et structurellement aveugle au
  pic du travail lui-même. Ce n'est pas un défaut à corriger : c'est la raison
  d'être des deux échantillonneurs, et le rapport indique lequel a tourné.
- **Le détecteur de bridage avait besoin d'une règle anti-bruit avant tout le
  reste.** Une fenêtre lente isolée dans un long run est une rotation de logs,
  pas une limite thermique.

Le verdict dit *le débit a régressé*, jamais *l'appareil a bridé*, sauf si une
série de température est présente. Un ralentissement soutenu a plusieurs causes
et le banc observe un symptôme.

61 tests, `mypy --strict` propre, 96 % de couverture, aucune dépendance
d'exécution. `ina219.py` est écrit d'après la fiche technique, n'a rien piloté,
et refuse de renvoyer des lectures — le même motif `NotPortedError` que
`hal/devices.py` ici.

### `fleet-ops-lab`

Deux règles, tout le reste en découle.

**Le silence est un retour arrière.** L'activation est provisoire : elle ouvre
une fenêtre de confirmation, et un nœud qui ne se manifeste pas revient en
arrière sur sa propre horloge, sans interroger aucun serveur. L'état qui doit
survivre à une coupure de courant est `PENDING`, et `PENDING` revient en arrière.
C'est l'argument de l'ADR 0009 de ce dépôt — une escalade que personne ne traite
est un refus — arrivé au même point depuis l'exploitation plutôt que depuis la
supervision humaine. Ce n'était pas prévu, et c'est probablement ce qu'il y a de
plus intéressant dans la paire.

**Le parc s'arrête de lui-même.** Une vague au-delà de son budget d'échec arrête
le déploiement, sans option pour continuer, parce que cette option serait activée
à trois heures du matin.

La défaillance la plus longue à modéliser correctement est le transfert qui
*réussit* en livrant les mauvais octets. Un contrôle « le téléchargement a-t-il
abouti » la manque complètement : d'où un code `digest-mismatch` distinct de
`transport-failure`, et un `FlakyTransport` capable de tronquer autant que de
couper.

Aucune cryptographie n'est embarquée. Qui exploite un parc a déjà une gestion de
clés, et le paquet n'en imposera pas une — mais un vérificateur *absent* avec un
quorum exigé lève une erreur au lieu de laisser passer, sur le principe de
l'invariant 6 d'ici : un artefact manquant est un contrôle en échec, pas un
contrôle ignoré.

67 tests, `mypy --strict` propre, 96 % de couverture, aucune dépendance
d'exécution. Chaque nœud est un objet Python ; rien n'a rencontré d'interrupteur.
Le `docs/PORTING.md` de ce dépôt liste ce que le premier portage sur banc devrait
trouver de faux, à commencer par l'ordre d'écriture autour de `PENDING`.

### Ce que cela change ici

Rien dans `src/`. L'invariant 10 tient inchangé — chaque `energy_model` reste
étiqueté `estimate` — mais le remplacement a désormais un producteur nommé et un
format nommé, et `energy_model_source` portera la chaîne `source` du banc
verbatim, empreinte comprise.

### Où ils sont allés

Les deux sont leurs propres dépôts, poussés le même jour :

* <https://github.com/thierrysays/measurement-harness>
* <https://github.com/thierrysays/fleet-ops-lab>

Ils ont été construits dans un répertoire de travail ici et entreposés
brièvement sous `spinoff/`, parce que l'application GitHub qui porte la session
ne peut pas créer de dépôts (`403 Resource not accessible by integration`). Dès
que les deux dépôts distants ont existé, les arborescences ont été transplantées
et le répertoire supprimé : il ne reste donc rien de ces deux projets dans
celui-ci — ce qui est tout l'objet de l'ADR 0011, et que les laisser ici aurait
discrètement défait.
