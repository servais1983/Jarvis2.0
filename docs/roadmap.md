# Roadmap actuelle

Cette roadmap reflète l'état réel du projet à ce stade, et non plus seulement l'intention de départ.

## Lecture rapide

| Domaine | État |
|---|---|
| Copilote cyber de base | Terminé |
| Assistant spécialisé avec mémoire et workflows | Largement terminé |
| Expérience vocale | Première version opérationnelle |
| Garde-fous et sécurité applicative | Socle avancé déjà présent |
| Collègue cyber opérationnel de bout en bout | Première version opérationnelle |
| Jarvis avancé multi-agents | À construire |

## Ce qui est déjà acquis

### 1. Socle produit

- chat texte ;
- mémoire conversationnelle ;
- profil de travail personnel ;
- interface web intégrée ;
- voix MVP et mode Realtime expérimental ;
- workflows :
  - résumé de CVE ;
  - enrichissement CVE ;
  - triage d'alerte ;
  - investigation guidée ;
  - brouillon de rapport d'incident.

### 2. Connaissance et méthodes de travail

- base documentaire avec ingestion de fichiers ;
- recherche lexicale et sémantique ;
- citations internes ;
- profils de tâches ;
- playbooks ;
- profils d'investigation ;
- modèles d'investigation prêts à l'emploi ;
- checklists recommandées par type d'enquête.

### 3. Routines et automatisations

- watchlists ;
- briefs quotidiens ;
- moteur d'automatisations ;
- scheduler actif ;
- inbox interne ;
- digest de connecteurs externes.

### 4. Connecteurs et outils

- NVD ;
- GitHub ;
- Google Drive ;
- Jira ;
- Microsoft Entra ID ;
- outils accessibles depuis le chat et le mode Realtime ;
- premières actions d'écriture sous approbation humaine.

### 5. Sécurité et gouvernance

- authentification ;
- rôles et permissions ;
- isolation par utilisateur ;
- MFA TOTP et codes de récupération ;
- sessions révocables ;
- audit ;
- limitation des tentatives de connexion ;
- coffre local chiffré pour secrets tiers ;
- garde-fous d'outils ;
- file d'approbations humaines.

## Ce qui manque encore vraiment

## Phase A — Devenir un collègue d'investigation

### État

Première version opérationnelle.

### Déjà livré

1. **Dossiers d'investigation persistants** ;
2. **checklists vivantes** avec états `à faire`, `fait`, `bloqué` ;
3. **timeline, preuves et hypothèses** ;
4. **synthèse d'avancement** ;
5. **transformation en livrable final** via rapport d'incident.

### Prochaine amélioration naturelle

Enrichir automatiquement les dossiers avec des signaux issus des vrais connecteurs cyber,
sans perdre le contrôle humain sur les lectures sensibles ou les écritures.

## Phase B — Se connecter aux vraies données cyber

### Objectif

Réduire l'écart entre l'assistant et le terrain opérationnel.

### À construire en priorité

1. connecteurs identité / cloud :
   - Microsoft Entra ID ;
   - Microsoft Defender ;
   - Microsoft Sentinel ;

2. connecteurs SIEM / logs :
   - Splunk ou Elastic ;

3. enrichissement sécurité :
   - VirusTotal ;
   - AbuseIPDB ;
   - Shodan ;
   - fournisseurs threat intel selon besoin réel.

### Principe

Ajouter peu de connecteurs, mais les bons.  
Le critère doit être : **quelles données réduisent réellement ton temps d'analyse au quotidien ?**

## Phase C — Passer du conseil à l'action contrôlée

### Objectif

Permettre à Jarvis d'agir davantage sans perdre le principe humain dans la boucle.

### À construire

- création et mise à jour de tickets ;
- commentaires Jira ;
- tâches de remédiation ;
- escalades contrôlées ;
- enrichissement automatique d'un dossier ;
- propositions d'actions selon le contexte ;
- politiques d'approbation plus fines selon le risque.

### Principe

Lecture automatique autant que possible ; écriture seulement avec garde-fous explicites.

## Phase D — Jarvis avancé

### Objectif

Passer d'un assistant unique très outillé à une véritable constellation de rôles spécialisés.

### À construire

- agent analyste SOC ;
- agent threat intel ;
- agent vulnérabilités ;
- agent rédacteur ;
- coordination entre agents ;
- délégation de tâches ;
- consolidation des réponses ;
- voix plus naturelle et continue ;
- commandes plus contextuelles.

## Phase E — Industrialisation

### Objectif

Préparer un déploiement durable et robuste.

### À construire

- sauvegarde / restauration ;
- observabilité renforcée ;
- métriques et alertes ;
- tests de charge ;
- politique de rétention ;
- WebAuthn / passkeys ;
- meilleure séparation des composants si le produit grossit ;
- documentation d'exploitation ;
- stratégie de déploiement multi-environnement.

## Ordre recommandé

| Priorité | Chantier | Pourquoi maintenant |
|---|---|---|
| 1 | Dossiers d'investigation vivants | Plus fort gain produit immédiat |
| 2 | Connecteurs cyber réels | Plus forte hausse d'intelligence contextuelle |
| 3 | Actions approuvées plus riches | Fait gagner du temps concret |
| 4 | Agents spécialisés | Utile une fois les flux métier solides |
| 5 | Industrialisation avancée | À renforcer avant un usage plus large |

## Prochain incrément conseillé

Le prochain incrément recommandé est maintenant :

1. renforcer **Microsoft Entra ID** comme premier vrai connecteur cyber ;
2. ajouter ensuite un connecteur de détection/réponse comme **Microsoft Defender** ou **Sentinel** ;
3. brancher ces signaux sur les dossiers d'investigation avec enrichissement contrôlé.

Ce lot est le meilleur levier actuel pour augmenter l'intelligence contextuelle réelle de Jarvis.
