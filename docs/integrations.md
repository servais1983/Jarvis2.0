# Intégrations

## NVD — CVE API 2.0

Jarvis Cyber utilise la NVD comme première source d'enrichissement de vulnérabilités.

### Pourquoi ce choix

- source officielle ;
- récupération par identifiant CVE ;
- métadonnées utiles pour le triage ;
- présence de champs complémentaires liés au catalogue KEV de la CISA quand disponibles.

### Variables de configuration

- `JARVIS_NVD_BASE_URL`
- `JARVIS_NVD_API_KEY`
- `JARVIS_HTTP_TIMEOUT_SECONDS`

### Bonnes pratiques prévues

- conserver la source dans les réponses ;
- ne pas modifier les données brutes avant restitution ;
- ajouter ensuite du cache et une gestion de quotas si l'usage devient fréquent.

> Ce produit utilise des données issues de l'API NVD mais n'est ni approuvé ni certifié par la NVD.


## Microsoft Entra ID — Microsoft Graph

Jarvis Cyber dispose maintenant d'un connecteur Entra ID **lecture seule** pour soutenir les investigations
de compromission de compte :

- `GET /connectors/entra-id/sign-ins`
- `GET /connectors/entra-id/risky-users`
- `GET /connectors/entra-id/users/{user_id}/authentication-methods`

### Variables de configuration

- `JARVIS_ENTRA_ID_GRAPH_BASE_URL`
- `JARVIS_ENTRA_ID_ACCESS_TOKEN`

### Choix de sécurité

- le connecteur n'effectue aucune action d'écriture ;
- les méthodes d'authentification sont volontairement ramenées à leur **type** ;
- l'outil conversationnel qui consulte ces méthodes est classé comme sensible et passe par l'approbation humaine ;
- les appels Graph restent explicites plutôt qu'automatiquement lanc?s dans tous les workflows.


## Microsoft Defender ? Microsoft Graph Security

Jarvis Cyber dispose maintenant d'un connecteur Microsoft Defender / Graph Security **lecture seule** :

- `GET /connectors/defender/incidents`
- `GET /connectors/defender/alerts`

### Variables de configuration

- `JARVIS_DEFENDER_GRAPH_BASE_URL`
- `JARVIS_DEFENDER_ACCESS_TOKEN`

### Permissions Graph attendues

- `SecurityIncident.Read.All` pour les incidents ;
- `SecurityAlert.Read.All` pour les alertes `alerts_v2`.

### Choix de s?curit?

- aucune action d'?criture ou de rem?diation ;
- aucun changement de statut d'alerte ;
- les alertes et incidents peuvent ?tre ajout?s ? un dossier comme faits observables ;
- les conclusions restent s?par?es dans les hypoth?ses suivies par l'analyste.


## Microsoft Sentinel ? Log Analytics KQL

Jarvis Cyber dispose maintenant d'un connecteur Sentinel / Log Analytics **lecture seule** :

- `POST /connectors/sentinel/query`

### Variables de configuration

- `JARVIS_SENTINEL_API_BASE_URL`
- `JARVIS_SENTINEL_WORKSPACE_ID`
- `JARVIS_SENTINEL_ACCESS_TOKEN`

### Permissions attendues

Le jeton doit pouvoir interroger le workspace Log Analytics cibl?. C?t? Azure, cela correspond aux permissions
`Microsoft.OperationalInsights/workspaces/query/*/read`, typiquement via un r?le comme Log Analytics Reader.

### Choix de s?curit?

- ex?cution uniquement de requ?tes KQL explicites ;
- outil conversationnel class? sensible ;
- r?sultats limit?s c?t? agent ;
- enrichissement de dossier sous forme de timeline et de preuve sourc?e, sans conclusion automatique.
