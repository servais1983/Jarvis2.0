# Opérations locales

## Configuration

Variables de durcissement ajoutées :

- `JARVIS_STORAGE_BACKEND`
- `JARVIS_DATABASE_PATH`
- `JARVIS_LOG_LEVEL`
- `JARVIS_AUTH_REQUIRED`
- `JARVIS_AUTH_TOKEN_TTL_HOURS`
- `JARVIS_AUTH_LOGIN_WINDOW_MINUTES`
- `JARVIS_AUTH_LOGIN_MAX_FAILURES`
- `JARVIS_AUTH_LOGIN_LOCK_MINUTES`
- `JARVIS_AUTH_PASSWORD_MIN_LENGTH`
- `JARVIS_HSTS_ENABLED`
- `JARVIS_SCHEDULER_ENABLED`
- `JARVIS_SCHEDULER_INTERVAL_SECONDS`
- `JARVIS_GITHUB_API_BASE_URL`
- `JARVIS_GITHUB_TOKEN`
- `JARVIS_GOOGLE_DRIVE_API_BASE_URL`
- `JARVIS_GOOGLE_DRIVE_ACCESS_TOKEN`
- `JARVIS_JIRA_BASE_URL`
- `JARVIS_JIRA_EMAIL`
- `JARVIS_JIRA_API_TOKEN`

## Persistance

Jarvis Cyber utilise désormais SQLite comme stockage local principal.

### Données persistées

- conversations ;
- documents ;
- extraits documentaires ;
- embeddings ;
- profils utilisateur ;
- profils de tâches ;
- playbooks ;
- watchlists ;
- automatisations ;
- historiques d'exécution ;
- inbox.

### Migration

Au premier démarrage avec une base SQLite vide :

- `conversations.jsonl` est repris vers la table de conversations ;
- `documents.jsonl` et `document_chunks.jsonl` sont repris vers les tables documentaires.

Si une ancienne base SQLite existe déjà, Jarvis applique aussi une migration de schéma non destructive :

- ajout de `user_id` lorsque nécessaire ;
- migration des données existantes vers l'utilisateur `local-dev` ;
- remplacement de l'ancienne contrainte de déduplication globale par une contrainte par utilisateur.

## Authentification

En développement, `JARVIS_AUTH_REQUIRED=false` autorise un utilisateur local implicite pour garder un cycle court.

En environnement plus strict :

1. définir `JARVIS_AUTH_REQUIRED=true` ;
2. créer un compte via `POST /auth/register` ;
3. obtenir un jeton via `POST /auth/login` ;
4. envoyer `Authorization: Bearer <token>` sur les endpoints protégés.

Les jetons sont opaques et stockés localement en base SQLite dans cette première version.

Les sessions utilisent maintenant :

- un identifiant de session séparé ;
- un hachage de jeton au repos ;
- une date d'expiration ;
- un champ de révocation ;
- une date de dernière utilisation.

Endpoints associés :

- `POST /auth/logout`
- `GET /auth/sessions`
- `DELETE /auth/sessions/{session_id}`

## Rôles

- premier compte créé : `admin` ;
- comptes suivants : `analyst`.

Endpoints d'administration :

- `GET /admin/users`
- `PATCH /admin/users/{user_id}/role`

Les capacités d'un utilisateur sont exposées via `GET /auth/capabilities`.

Les permissions sont maintenant exprimées finement, par exemple :

- `knowledge.read`
- `knowledge.write`
- `knowledge.delete`
- `task_profiles.read`
- `playbooks.write`
- `watchlists.read`
- `briefs.daily`
- `automations.read`
- `automations.run`
- `inbox.read`
- `connectors.read`
- `voice.use`
- `realtime.use`
- `admin.users.write`
- `admin.audit.export`

## Audit et anti-brute-force

Jarvis journalise désormais les événements sensibles dans `security_audit_events`, notamment :

- inscription ;
- connexion réussie ;
- échec de connexion ;
- blocage temporaire ;
- déconnexion ;
- révocation de session ;
- changement de rôle.

Les échecs de connexion sont suivis par couple email / adresse IP.  
Après dépassement du seuil configuré, le couple est temporairement bloqué.

Endpoint d'administration :

- `GET /admin/audit-events`
- `GET /admin/audit-events/export.csv`

Les événements peuvent être filtrés par type, acteur et plage temporelle.

## En-têtes HTTP

Les réponses ajoutent maintenant notamment :

- `Content-Security-Policy`
- `X-Content-Type-Options`
- `X-Frame-Options`
- `Referrer-Policy`
- `Permissions-Policy`

`Strict-Transport-Security` reste désactivé par défaut en local et peut être activé via `JARVIS_HSTS_ENABLED=true` sur un déploiement HTTPS maîtrisé.

## Préparation MFA

La base comprend maintenant :

- `users.mfa_required`
- la table `mfa_factors`
- `GET /auth/mfa/status`

Le parcours d'enrôlement effectif n'est pas encore activé : avant de stocker des secrets TOTP ou WebAuthn, il faut décider du mécanisme de protection de ces secrets au repos.

## Santé applicative

`GET /health` renvoie :

- `database_ready`
- `voice_enabled`
- `embeddings_enabled`
- `scheduler_enabled`
- `scheduler_running`

## Journalisation

Chaque requête HTTP produit une ligne simple avec :

- méthode ;
- chemin ;
- statut ;
- durée.
