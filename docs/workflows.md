# Premiers workflows cyber

## 1. Résumé de CVE

### Entrée

- identifiant CVE optionnel ;
- texte source fourni par l'utilisateur.

### Sortie attendue

- `executive_summary` ;
- `affected_products` ;
- `technical_impact` ;
- `urgency` ;
- `exploitation_signals` ;
- `recommended_actions` ;
- `uncertainties` ;
- `confidence`.

## 1 bis. Enrichissement automatique de CVE

### Entrée

- identifiant CVE.

### Comportement

- récupération de la fiche officielle depuis la NVD ;
- extraction de la description, du score CVSS, des références, des critères affectés et du signal KEV quand disponible ;
- réutilisation du workflow de résumé structuré.

### Sortie attendue

- `record` : données brutes normalisées ;
- `analysis` : synthèse structurée prête à exploiter.

## 2. Triage d'alerte

### Entrée

- titre ;
- alerte brute ;
- contexte d'environnement optionnel.

### Sortie attendue

- `classification` ;
- `observed_facts` ;
- `hypotheses` ;
- `priority_checks` ;
- `severity` ;
- `decision` ;
- `rationale` ;
- `confidence`.

## 3. Brouillon de rapport d'incident

### Entrée

- résumé ;
- chronologie ;
- impact ;
- actions prises ;
- questions ouvertes.

### Sortie attendue

- `executive_summary` ;
- `timeline` ;
- `scope_and_impact` ;
- `probable_cause` ;
- `actions_taken` ;
- `recommended_actions` ;
- `open_questions` ;
- `confidence`.

## 4. Investigation guidée

### Entrée

- titre ;
- alerte brute ;
- contexte d'environnement optionnel ;
- objectif d'investigation optionnel ;
- profil d'investigation optionnel ;
- enrichissements GitHub, Google Drive et Jira optionnels.

### Comportement

- réutilise le triage initial ;
- recherche les connaissances internes pertinentes ;
- recherche les playbooks personnels applicables ;
- peut charger du contexte externe lecture seule depuis les connecteurs ;
- applique un profil d'investigation explicite, ou en infère un lorsqu'une correspondance lexicale existe.

### Sortie attendue

- `result` structuré ;
- `knowledge_hits` ;
- `playbook_hits` ;
- `applied_profile` ;
- `external_context` ;
- `pending_approval_id` lorsqu'une action d'écriture proposée exige une validation humaine.

## Profils d'investigation prêts à l'emploi

Jarvis fournit une bibliothèque globale de modèles lisibles via :

- `GET /investigation-profile-templates`

Les premiers modèles couvrent :

- compromission de compte ;
- phishing ;
- exécution suspecte / malware ;
- vulnérabilité critique ;
- exfiltration de données.

Ces modèles ne sont pas créés automatiquement dans l'espace utilisateur.  
Ils servent de base de préremplissage afin que l'analyste conserve la main sur les ajustements locaux avant enregistrement.

Chaque modèle fournit aussi une checklist recommandée.  
Lorsqu'un profil est appliqué à une investigation, cette checklist est injectée dans le contexte du workflow pour orienter les vérifications prioritaires sans remplacer le jugement de l'analyste.

## Dossiers d'investigation

### Rôle

Les dossiers prolongent le workflow d'investigation dans le temps :

- une alerte et son contexte deviennent persistants ;
- la checklist du profil est copiée dans le dossier ;
- chaque point peut passer de `todo` à `done` ou `blocked` ;
- des notes sont ajoutées au fil de l'analyse ;
- des événements factuels forment une timeline ;
- des preuves conservent les observations collectées ;
- des hypothèses restent suivies séparément avec les états `open`, `supported` ou `rejected` ;
- une synthèse d'avancement indique la progression et les prochaines vérifications ouvertes.

### Endpoints

- `POST /investigation-cases`
- `GET /investigation-cases`
- `GET /investigation-cases/queue`
- `GET /investigation-cases/shift-brief`
- `GET /investigation-cases/sla`
- `GET /investigation-cases/{case_id}`
- `PATCH /investigation-cases/{case_id}/status`
- `PATCH /investigation-cases/{case_id}/checklist/{item_id}`
- `POST /investigation-cases/{case_id}/notes`
- `POST /investigation-cases/{case_id}/events`
- `POST /investigation-cases/{case_id}/evidence`
- `POST /investigation-cases/{case_id}/hypotheses`
- `PATCH /investigation-cases/{case_id}/hypotheses/{hypothesis_id}`
- `POST /investigation-cases/{case_id}/summary`
- `POST /investigation-cases/{case_id}/report`
- `POST /investigation-cases/{case_id}/enrichment-plan`
- `POST /investigation-cases/{case_id}/incident-view`
- `POST /investigation-cases/{case_id}/closure-assistant`
- `DELETE /investigation-cases/{case_id}`

### Synthèse d'avancement

La synthèse d'avancement transforme l'état courant du dossier en un objet structuré :

- faits établis ;
- hypothèses soutenues ;
- hypothèses rejetées ;
- prochaines actions ;
- incertitudes ;
- confiance globale.

Le mode local conserve un comportement utile en s'appuyant directement sur les événements, hypothèses et points ouverts du dossier.

### Enrichissement Defender

Un dossier peut aussi ?tre enrichi explicitement avec les incidents et alertes Microsoft Defender / Graph Security.

L'enrichissement Defender ajoute :

- les alertes comme ?v?nements de timeline ;
- les incidents et alertes comme preuves sourc?es ;
- aucune hypoth?se automatique.

Le filtre `query` permet de limiter localement les ?l?ments retenus ? un utilisateur, une machine, un titre ou un identifiant pertinent.

### Enrichissement Sentinel / KQL

Un dossier peut ?tre enrichi avec une requ?te KQL explicite sur le workspace Sentinel / Log Analytics.

L'enrichissement Sentinel ajoute :

- une preuve synth?tique avec les colonnes et un aper?u limit? des premi?res lignes ;
- des ?v?nements de timeline lorsque les lignes contiennent une colonne temporelle exploitable comme `TimeGenerated` ;
- aucune hypoth?se automatique.

Cet enrichissement est puissant mais sensible : les requ?tes doivent rester cibl?es et proportionn?es au dossier.

Des packs KQL pr?ts ? l'emploi sont disponibles pour pr?remplir les requ?tes selon le sc?nario :

- compromission de compte ;
- phishing ;
- malware / ex?cution suspecte ;
- exfiltration ;
- vuln?rabilit? critique.

Endpoints :

- `GET /sentinel-query-templates`
- `POST /sentinel-query-templates/{template_id}/render`

### Plan d'enrichissement conseill?

Jarvis peut proposer un plan consultatif depuis l'?tat courant du dossier via `POST /investigation-cases/{case_id}/enrichment-plan`.

Le plan :

- inf?re le sc?nario probable : compromission de compte, phishing, malware, exfiltration, vuln?rabilit? critique ou g?n?ral ;
- recommande les enrichissements Entra ID, Defender et Sentinel utiles ;
- indique les param?tres d?j? d?tect?s, comme UPN, CVE, URL ou nom de machine ;
- signale les enrichissements d?j? pr?sents dans les preuves ;
- n'ex?cute aucune requ?te externe automatiquement.
- permet de pr?remplir les formulaires d'enrichissement dans l'interface sans d?clencher l'ex?cution.

Ce comportement garde Jarvis dans un r?le de copilote : il propose le chemin d'analyse, mais l'analyste valide chaque interrogation.

### Vue incident

`POST /investigation-cases/{case_id}/incident-view` produit une vue de pilotage locale adapt?e au sc?nario inf?r?. Elle affiche les indicateurs pivot, les preuves d?j? disponibles, les manques visibles et les questions de d?cision utiles pour l'analyste. Elle ne contacte aucun connecteur et ne modifie pas le dossier.

### File de travail SOC

`GET /investigation-cases/queue` classe les dossiers actifs selon un score explicable : sc?nario inf?r?, statut, absence de preuves, timeline vide, hypoth?ses ouvertes et checklist restante. La sortie donne une priorit? (`critical`, `high`, `medium`, `low`), les raisons principales et la prochaine action conseill?e.

### Mode quart SOC

`GET /investigation-cases/shift-brief` transforme la file SOC en brief op?rationnel. Il regroupe les dossiers ? traiter maintenant, les dossiers bloqu?s ou sous-document?s, ceux pr?ts pour synth?se/rapport, et ceux qui peuvent attendre. Le brief reste consultatif et ne d?clenche aucune action.

### Timers SLA SOC

`GET /investigation-cases/sla` surveille les d?passements temporels locaux : dossiers critiques ouverts trop longtemps, absence de preuve apr?s cr?ation, timeline vide et dossiers pr?ts pour rapport mais inactifs. Chaque alerte fournit l'?tat (`breached`, `warning`, `ok`) et une prochaine action conseill?e.

### Assistant de cl?ture

`POST /investigation-cases/{case_id}/closure-assistant` ?value la readiness de cl?ture : preuves, timeline, hypoth?ses, checklist et note de d?cision. Il renvoie un score, les blocages, et recommande la g?n?ration du rapport final seulement lorsque le dossier est pr?t. Il ne ferme jamais un dossier automatiquement.

### Rapport final depuis dossier

Le rapport final réutilise le workflow de rédaction d'incident existant, mais l'alimente directement depuis le dossier :

- timeline depuis les événements ;
- résumé depuis les notes ;
- impact depuis les preuves ;
- actions réalisées depuis la checklist terminée ;
- questions ouvertes depuis les hypothèses encore ouvertes.

## Pourquoi les sorties sont désormais structurées

Chaque workflow renvoie maintenant un objet typé plutôt qu'un simple bloc de texte.

Cela permet :

- de construire plus tard une interface avec des cartes, badges et filtres ;
- d'automatiser certaines décisions sans parser du langage naturel fragile ;
- d'exporter plus facilement les résultats vers des tickets, rapports ou connecteurs.

## Pourquoi ces trois workflows

Ils couvrent trois gestes très fréquents du travail cyber :

1. comprendre vite ;
2. décider quoi faire ;
3. documenter proprement.

Ce trio donne plus de valeur pratique au projet qu'une accumulation précoce de fonctionnalités spectaculaires mais peu ciblées.
