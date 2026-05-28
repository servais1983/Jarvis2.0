# Jarvis Cyber

Jarvis Cyber est un copilote personnel orienté cybersécurité, pensé pour évoluer vers un collègue numérique vocal capable d'assister un analyste dans son travail quotidien.

## Vision courte

Construire d'abord un assistant **réellement utile au quotidien** :

1. discuter et raisonner avec toi sur des sujets cyber ;
2. comprendre ton contexte, tes procédures et tes préférences ;
3. t'aider à analyser, résumer, documenter et décider ;
4. recevoir ensuite une couche vocale et des intégrations d'outils ;
5. évoluer plus tard vers plusieurs agents spécialisés et des automatisations contrôlées.

## Pourquoi commencer petit

Le risque d'un projet "à la Iron Man" est de produire une démo impressionnante mais peu exploitable.  
Le MVP vise donc trois qualités avant tout :

- **utile** : il doit t'épargner du temps rapidement ;
- **fiable** : il doit expliquer ses hypothèses et rester vérifiable ;
- **évolutif** : il ne doit pas bloquer l'arrivée future de la voix, de la mémoire et des outils.

## Démarrage rapide

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn jarvis_cyber.api.main:app --reload
```

Puis ouvre :

- `GET /` pour l'interface web ;
- `GET /health`
- `POST /chat`
- `POST /workflows/cve-summary`
- `POST /workflows/cve-enrichment`
- `POST /workflows/alert-triage`
- `POST /workflows/incident-report`

Exemple de payload :

```json
{
  "session_id": "perso",
  "message": "Aide-moi à trier cette alerte."
}
```

Si `OPENAI_API_KEY` est renseignée dans `.env`, le service utilisera le modèle configuré.  
Sinon, il reste en mode local de repli pour que le projet puisse être lancé et testé immédiatement.

## Durcissement local

Le socle utilise maintenant SQLite pour :

- l'historique conversationnel ;
- les documents ;
- les extraits documentaires ;
- les profils utilisateur.

Les anciens fichiers JSONL sont migrés automatiquement au premier lancement lorsqu'une base SQLite vide est détectée.

## Authentification et isolation

Jarvis possède maintenant une première couche d'identité :

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`

Les conversations et les documents sont isolés par `user_id`.
Les endpoints de workflow, de voix et de Realtime passent eux aussi par la dépendance d'authentification quand le mode strict est activé.

Jarvis possède aussi maintenant un profil de travail personnel via :

- `GET /profile/me`
- `PUT /profile/me`

Ce profil conserve séparément :

- le nom affiché, la fonction et l'organisation ;
- le contexte d'environnement ;
- les domaines prioritaires ;
- la langue, le style de réponse et la préférence d'approbation ;
- le fuseau horaire.

Ces informations sont injectées dans les conversations classiques et dans le mode Realtime afin que Jarvis réponde davantage comme un collègue qui connaît ton cadre de travail.

Jarvis distingue maintenant deux rôles :

- `admin` : accès complet, y compris la gestion des utilisateurs ;
- `analyst` : accès aux fonctions métier courantes.

Le premier compte créé devient automatiquement `admin`, les suivants deviennent `analyst`.

Les sessions sont maintenant durcies :

- jetons stockés sous forme hachée en base ;
- durée de vie configurable via `JARVIS_AUTH_TOKEN_TTL_HOURS` ;
- révocation serveur lors de la déconnexion ;
- affichage et révocation des autres sessions actives depuis l'interface.

Le backend ajoute aussi maintenant :

- un journal d'audit des événements sensibles ;
- un freinage des tentatives de connexion répétées ;
- des en-têtes HTTP de sécurité sur les réponses.

La couche d'identité applique maintenant aussi une politique de mot de passe minimale :

- au moins 12 caractères par défaut ;
- majuscule, minuscule, chiffre et symbole ;
- rejet de quelques secrets trop communs ;
- rejet d'un mot de passe contenant la partie locale de l'email.

Le modèle de permissions est maintenant plus fin que les seuls rôles :

- lecture / écriture / suppression documentaire ;
- lecture / écriture / suppression des profils de tâches et playbooks ;
- lecture / écriture / suppression des watchlists et génération de briefs ;
- lecture / écriture / exécution des automatisations ;
- usage du chat, de la voix et du Realtime ;
- workflows cyber ;
- lecture / écriture des utilisateurs ;
- lecture / export de l'audit.

Par défaut, `JARVIS_AUTH_REQUIRED=false` garde un mode de développement fluide avec un utilisateur local implicite (`local-dev`).  
En positionnant `JARVIS_AUTH_REQUIRED=true`, les endpoints protégés exigent un jeton Bearer obtenu après inscription ou connexion.

Exemple :

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/auth/login `
  -ContentType "application/json" `
  -Body '{"email":"toi@example.com","password":"motdepassefort"}'

Invoke-RestMethod `
  -Method Get `
  -Uri http://127.0.0.1:8000/auth/me `
  -Headers @{ Authorization = "Bearer $($login.token)" }
```

L'endpoint `/health` expose désormais aussi :

- l'état de la base ;
- l'activation de la voix ;
- l'activation des embeddings.

Jarvis possède maintenant un premier vrai parcours MFA TOTP :

- `POST /auth/mfa/totp/enroll`
- `POST /auth/mfa/totp/verify`

Les secrets TOTP sont chiffrés en base avec `JARVIS_MFA_ENCRYPTION_KEY`.  
Une fois un facteur vérifié, les connexions du compte exigent un code MFA et les codes déjà utilisés
dans la même fenêtre temporelle sont refusés.

## Premiers workflows cyber

### Résumé de CVE

```json
{
  "cve_id": "CVE-2026-0001",
  "source_text": "Remote code execution affecting Product X before version 4.2."
}
```

### Enrichissement automatique de CVE

```json
{
  "cve_id": "CVE-2026-0001"
}
```

Ce workflow récupère d'abord les données officielles de la NVD, puis produit une analyse structurée à partir de ces informations.

## Interface web

Une première interface légère est disponible sur `/`.

Elle permet déjà de :

- créer un compte, se connecter et se déconnecter ;
- renseigner son profil de travail ;
- afficher le rôle actif ;
- gérer les utilisateurs depuis un petit panneau d'administration lorsqu'on est `admin` ;
- consulter les derniers événements de sécurité depuis ce même panneau ;
- discuter avec Jarvis ;
- lancer une analyse CVE ;
- trier une alerte ;
- générer un brouillon de rapport d'incident ;
- ajouter des notes et procédures dans la base documentaire.
- utiliser un premier mode vocal :
  - enregistrement micro ;
  - transcription ;
  - lecture de la dernière réponse.

Le choix volontaire de cette première version est la simplicité : une UI intégrée à FastAPI, suffisante pour valider l'utilité produit avant d'investir dans un frontend séparé.
Le jeton d'authentification de l'interface est conservé dans la session navigateur dans cette version MVP.

## Base documentaire

Jarvis peut maintenant stocker des connaissances personnelles via :

- `POST /knowledge/documents`
- `POST /knowledge/files`
- `GET /knowledge/documents`
- `POST /knowledge/search`

La recherche documentaire fonctionne maintenant en deux niveaux :

- recherche sémantique par embeddings si `OPENAI_API_KEY` est configurée ;
- recherche lexicale locale en repli sinon.

Les vecteurs restent stockés localement dans le MVP, afin de gagner en pertinence sans ajouter encore une base vectorielle dédiée. L'ingestion accepte maintenant les fichiers `.txt`, `.md`, `.markdown`, `.log`, `.pdf` et `.docx`, ainsi que l'import multi-fichiers.

Quand le chat retrouve des extraits pertinents, il expose aussi des **citations internes** (`S1`, `S2`, etc.) avec le document source et l'extrait utilisé.

La base gère maintenant aussi :

- la déduplication simple par contenu ;
- la liste des documents présents ;
- la suppression d'un document et de ses extraits associés.

La déduplication est désormais appliquée **par utilisateur** : deux personnes peuvent donc stocker le même contenu sans partager leurs documents.

## Profils de tâches et playbooks

Jarvis peut maintenant mémoriser non seulement ce qu'il sait, mais aussi **comment tu travailles** :

- `POST /task-profiles`
- `GET /task-profiles`
- `DELETE /task-profiles/{profile_id}`
- `POST /playbooks`
- `GET /playbooks`
- `POST /playbooks/search`
- `DELETE /playbooks/{playbook_id}`

Un **profil de tâche** décrit la forme attendue d'un livrable :

- nom ;
- description ;
- format de sortie ;
- checklist de relecture.

Un **playbook** décrit une procédure réutilisable :

- objectif ;
- déclencheurs ;
- étapes ;
- résultat attendu ;
- profil de tâche associé éventuel.

Quand une conversation ressemble à un playbook connu, Jarvis injecte ce contexte métier dans son raisonnement.  
Le mode Realtime peut aussi rechercher ces playbooks via un outil serveur dédié.

## Profils d'investigation

Jarvis peut maintenant mémoriser **comment lancer différents types d'enquête** :

- `POST /investigation-profiles`
- `GET /investigation-profiles`
- `DELETE /investigation-profiles/{profile_id}`

Un profil d'investigation peut définir :

- un nom et une description ;
- des expressions déclencheuses ;
- un objectif par défaut ;
- une checklist recommandée ;
- l'activation optionnelle du contexte GitHub récent ;
- une requête Google Drive par défaut ;
- une requête Jira par défaut.

Lors d'une investigation guidée, tu peux sélectionner explicitement un profil.  
Si aucun profil n'est choisi, Jarvis peut en proposer un automatiquement lorsqu'un profil correspond lexicalement à l'alerte reçue.

Jarvis expose aussi une petite bibliothèque de **modèles prêts à l'emploi** via :

- `GET /investigation-profile-templates`

Les modèles initiaux couvrent :

- compromission de compte ;
- phishing ;
- exécution suspecte / malware ;
- vulnérabilité critique ;
- exfiltration de données.

Ils restent globaux et en lecture seule : depuis l'interface, tu peux les utiliser pour **préremplir** un nouveau profil, puis adapter les champs avant de l'enregistrer dans ton propre espace.

Chaque modèle embarque aussi une checklist de vérifications de départ, utilisée par le workflow comme contexte guidant l'analyse.

## Watchlists et brief quotidien

Jarvis possède maintenant une première routine récurrente exploitable :

- `POST /watchlists`
- `GET /watchlists`
- `DELETE /watchlists/{watchlist_id}`
- `POST /briefs/daily`

Une watchlist suit un sujet vulnérabilité via :

- un titre ;
- des mots-clés NVD ;
- un mode d'expression exacte optionnel ;
- un filtre optionnel `KEV uniquement`.

Le brief quotidien interroge les CVE récentes publiées dans la fenêtre demandée et regroupe les résultats par watchlist.  
Ce premier flux s'appuie sur les filtres officiels de l'API NVD (`keywordSearch`, `pubStartDate`, `pubEndDate`, `hasKev`). 

## Automatisations natives

Jarvis dispose maintenant d'un premier moteur d'automatisations internes :

- `POST /automations`
- `GET /automations`
- `DELETE /automations/{automation_id}`
- `POST /automations/{automation_id}/run`
- `POST /automations/run-due`
- `GET /automations/{automation_id}/runs`

La première tâche supportée est `daily_brief`.

Chaque automatisation conserve :

- son horaire local ;
- son fuseau horaire ;
- ses paramètres ;
- l'option `requires_approval` ;
- la prochaine exécution prévue ;
- la dernière exécution.

Chaque exécution possède aussi son propre historique (`succeeded`, `failed`, `approval_required`) afin de préparer un futur planificateur continu et des garde-fous plus fins.

Le planificateur continu est maintenant actif au démarrage de l'application :

- intervalle configurable via `JARVIS_SCHEDULER_INTERVAL_SECONDS` ;
- activation configurable via `JARVIS_SCHEDULER_ENABLED` ;
- exécution périodique des routines arrivées à échéance ;
- arrêt propre lors de la fermeture de l'application.

## Inbox interne

Les résultats des automatisations sont maintenant visibles dans une inbox personnelle :

- `GET /inbox`
- `PATCH /inbox/{item_id}/read`

Les routines y déposent automatiquement :

- les livrables réussis ;
- les échecs ;
- les demandes d'approbation.

Chaque élément garde un statut lu / non lu, un résumé et, quand disponible, le payload complet du livrable.

Jarvis tient maintenant compte d'un résumé des éléments non lus dans le chat, et le mode Realtime expose
un outil `list_inbox` pour répondre naturellement à des demandes comme :

- « qu'est-ce qui m'attend ce matin ? »
- « lis-moi mes livrables non lus »
- « quel est le dernier brief disponible ? »

## Connecteurs externes

Un premier socle de connecteurs **lecture seule** est maintenant disponible :

- `GET /connectors/status`
- `GET /connectors/github/repositories`
- `GET /connectors/github/repos/{owner}/{repo}/pulls`
- `GET /connectors/google-drive/files`
- `GET /connectors/jira/issues`
- `GET /connectors/entra-id/sign-ins`
- `GET /connectors/entra-id/risky-users`
- `GET /connectors/entra-id/users/{user_id}/authentication-methods`
- `GET /connectors/defender/incidents`
- `GET /connectors/defender/alerts`
- `POST /connectors/sentinel/query`

Les quatre fournisseurs initiaux sont :

- GitHub ;
- Google Drive ;
- Jira ;
- Microsoft Entra ID ;
- Microsoft Defender / Graph Security ;
- Microsoft Sentinel / Log Analytics KQL.

Les identifiants peuvent désormais être fournis de deux façons :

- via variables d'environnement, qui restent prioritaires ;
- via un **coffre local chiffré** optionnel pour les jetons tiers :

- `GET /admin/connector-secrets`
- `PUT /admin/connector-secrets/{provider}`
- `DELETE /admin/connector-secrets/{provider}`

Les variables d'environnement restent prioritaires lorsqu'elles existent ; sinon les connecteurs peuvent
résoudre leurs jetons depuis le coffre chiffré avec `JARVIS_SECRET_VAULT_KEY`.

Ces connecteurs sont maintenant exploitables :

- en mode Realtime via les outils `list_github_repositories`, `list_google_drive_files`,
  `search_jira_issues`, `list_entra_sign_ins`, `list_entra_risky_users`,
  `list_entra_authentication_methods`, `list_defender_incidents`, `list_defender_alerts`
  et `run_sentinel_query` ;
- dans les automatisations via un nouveau type `connector_digest` ;
- dans le chat textuel, qui peut désormais appeler ces outils en lecture seule quand une réponse
  dépend de données récentes ou externes.

## Garde-fous par outil

Jarvis possède maintenant une politique d'exécution commune pour ses outils agentiques :

- chaque outil est associé à une permission, un niveau de risque et un mode d'accès ;
- le chat texte et Realtime passent par la même décision ;
- les préférences utilisateur sont respectées :
  - `ask_before_sensitive_actions` autorise les outils actuels de lecture seule ;
  - `always_ask` renvoie une demande d'approbation avant exécution ;
  - `suggest_only` bloque l'exécution et laisse Jarvis conseiller sans agir ;
- chaque décision est auditée sans journaliser le contenu détaillé des requêtes.

Jarvis possède maintenant aussi un premier **flux d'action approuvée** :

- l'agent peut proposer certaines actions d'écriture ;
- les actions sensibles créent une demande d'approbation persistée ;
- l'utilisateur peut les approuver ou les refuser depuis l'interface ;
- l'exécution ne se fait qu'après validation humaine explicite.

Le premier outil d'écriture pris en charge est `create_watchlist`, qui permet à Jarvis de proposer une
nouvelle surveillance CVE depuis la conversation sans la créer silencieusement.

## MFA et récupération

Le parcours MFA est désormais complet pour le mode TOTP :

- enrôlement puis vérification d'un facteur ;
- exigence automatique du second facteur à la connexion ;
- génération de codes de récupération à usage unique uniquement après vérification d'un facteur ;
- suivi du nombre de codes encore disponibles ;
- désactivation d'un facteur avec preuve MFA ;
- confirmation explicite obligatoire avant de retirer le dernier facteur actif.

Si le dernier facteur est retiré volontairement, les codes de récupération inutilisés sont supprimés en même
temps afin d'éviter de conserver des moyens d'accès orphelins.

## Voix

Le mode vocal MVP repose sur deux étapes :

1. `POST /voice/chat` pour transcrire un enregistrement puis l'envoyer au chat ;
2. `POST /voice/speech` pour générer un audio à partir d'une réponse texte.

Ce choix garde le système simple tout en préparant une évolution future vers une vraie conversation temps réel.

Un **mode Realtime expérimental** est aussi disponible :

- `GET /realtime/token`
- boutons dédiés dans l'interface pour démarrer / arrêter la session voix-à-voix.

Le navigateur utilise un secret éphémère généré côté backend ; la clé API principale n'est jamais exposée au client.

Le mode Realtime expose déjà plusieurs outils :

- recherche documentaire ;
- recherche de playbooks ;
- consultation de l'inbox ;
- lecture des dépôts GitHub accessibles ;
- lecture des fichiers Google Drive récents ;
- recherche de tickets Jira ;
- analyse de CVE ;
- triage d'alerte.

L'orchestration des outils passe maintenant par un canal **sideband serveur** associé à la session Realtime ; le navigateur reste cantonné à son rôle de client audio.
Le sideband conserve désormais aussi l'identité de l'utilisateur connecté afin que la recherche documentaire Realtime reste cloisonnée.

### Triage d'alerte

```json
{
  "title": "Impossible travel",
  "raw_alert": "Login from Brussels followed by login from Tokyo in 4 minutes.",
  "environment_context": "User is not known to travel."
}
```

### Brouillon de rapport d'incident

```json
{
  "incident_summary": "Suspicious PowerShell execution on workstation WS-42.",
  "timeline": "10:02 alert, 10:05 host isolated.",
  "impact": "One workstation affected."
}
```

### Investigation guidée

Jarvis dispose maintenant d'un workflow plus complet pour les alertes :

- `POST /workflows/alert-investigation`

Ce flux rassemble :

- le triage initial ;
- les extraits de connaissance pertinents ;
- les playbooks personnels applicables ;
- du contexte externe optionnel issu de GitHub, Google Drive et Jira lorsqu'une requête explicite est fournie ;
- les vérifications prioritaires ;
- les prochaines actions recommandées.

Le workflow accepte maintenant aussi un `investigation_profile_id`.  
Le profil appliqué est renvoyé dans la réponse via `applied_profile`, et ses valeurs par défaut peuvent alimenter automatiquement l'objectif de l'enquête ainsi que les enrichissements GitHub, Drive et Jira.

S'il identifie une surveillance récurrente clairement utile, il peut proposer une watchlist ; cette action
ne s'exécute pas seule, elle passe par la file d'approbation humaine.

## Dossiers d'investigation

Jarvis peut maintenant suivre une enquête dans le temps via :

- `POST /investigation-cases`
- `GET /investigation-cases`
- `GET /investigation-cases/queue`
- `GET /investigation-cases/shift-brief`
- `GET /investigation-cases/sla`
- `GET /investigation-cases/{case_id}`
- `PATCH /investigation-cases/{case_id}/status`
- `PATCH /investigation-cases/{case_id}/checklist/{item_id}`
- `POST /investigation-cases/{case_id}/notes`
- `DELETE /investigation-cases/{case_id}`

Un dossier conserve :

- l'alerte de départ ;
- le profil d'investigation associé ;
- une checklist initialisée depuis le profil ;
- le statut global du dossier ;
- des notes d'analyse ;
- une timeline factuelle ;
- des preuves / artefacts ;
- des hypothèses suivies séparément des faits ;
- une synthèse d'avancement simple avec prochaines vérifications ouvertes.

Jarvis peut maintenant aussi produire une **synthèse d'avancement rédigée** via :

- `POST /investigation-cases/{case_id}/summary`

Cette synthèse distingue :

- les faits établis ;
- les hypothèses soutenues ;
- les hypothèses rejetées ;
- les prochaines actions ;
- les incertitudes restantes ;
- le niveau de confiance.

Le dossier peut aussi être transformé directement en **rapport final d'incident** via :

- `POST /investigation-cases/{case_id}/report`

Le rapport réutilise automatiquement la timeline, les notes, les preuves, les actions déjà réalisées et les questions encore ouvertes du dossier.

Depuis l'interface, une investigation guidée peut maintenant être transformée en dossier persistant pour continuer le travail au-delà de la première réponse.

## Structure initiale

```text
docs/                  # vision, architecture, roadmap
src/jarvis_cyber/
  api/                 # API HTTP
  core/                # prompts, contrats métier
  services/            # logique applicative
tests/                 # tests de non-régression
```

## Prochaine cible

Le socle SOC est maintenant solide : dossiers persistants, preuves, timeline, hypoth?ses, Entra ID, Defender, Sentinel/KQL, packs de requ?tes et plan d'enrichissement consultatif.

Le prochain incr?ment le plus utile est de rapprocher l'exp?rience du coll?gue cyber quotidien :

1. ajouter des vues de synth?se par type d'incident ;
2. renforcer la boucle vocale pour piloter une investigation sans perdre les garde-fous ;
3. pr?parer une vraie file de travail SOC avec priorisation des dossiers.
