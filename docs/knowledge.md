# Base documentaire

## Objectif

Permettre à Jarvis Cyber de s'appuyer sur tes propres :

- procédures ;
- playbooks ;
- modèles de rapports ;
- notes opérationnelles ;
- conventions internes.

## Design MVP

La première version repose sur :

- un stockage JSONL local ;
- un découpage des documents en extraits ;
- une recherche lexicale simple en repli ;
- une recherche sémantique par embeddings quand `OPENAI_API_KEY` est configurée ;
- l'injection des meilleurs extraits dans le prompt de chat.

## Pourquoi ce choix

Cette approche est volontairement modeste mais utile :

- pas de dépendance lourde ;
- très simple à inspecter et déboguer ;
- suffisante pour découvrir les vrais usages ;
- remplaçable plus tard par une recherche vectorielle sans casser l'API.

## Recherche sémantique

Quand les embeddings sont activés :

- les extraits ingérés reçoivent un vecteur localement stocké ;
- les requêtes sont elles aussi vectorisées ;
- les résultats sont classés par similarité cosinus.

Si aucun embedding n'est disponible, Jarvis retombe automatiquement sur la recherche lexicale existante.

## Endpoints

- `POST /knowledge/documents`
- `POST /knowledge/files`
- `GET /knowledge/documents`
- `POST /knowledge/search`

## Formats acceptés au MVP

- `.txt`
- `.md`
- `.markdown`
- `.log`
- `.pdf`
- `.docx`

L'interface accepte aussi l'import multi-fichiers.

### Limite importante

Les PDF scannés sans couche texte ne sont pas encore traités par OCR ; ils peuvent donc être rejetés comme documents sans texte extractible.

## Prochaines évolutions possibles

1. OCR pour PDF scannés ;
2. vraie base vectorielle dédiée si le volume devient important ;
3. tags, collections et permissions.

## Citations internes

Quand le chat retrouve des extraits pertinents, la réponse expose aussi :

- un identifiant de citation (`S1`, `S2`, etc.) ;
- le document source ;
- l'extrait utilisé.

Avec un modèle distant configuré, Jarvis reçoit aussi l'instruction de référencer explicitement ces sources internes dans son texte.

## Gestion documentaire

La base documentaire MVP gère aussi :

- une déduplication par empreinte du contenu ;
- la consultation des documents présents ;
- la suppression d'un document et de ses extraits.

Cela évite que la mémoire interne grossisse avec plusieurs copies identiques d'un même playbook.
