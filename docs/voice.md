# Voix

## Objectif

Donner à Jarvis Cyber une première interface orale sans réécrire tout le système.

## Mode gratuit par défaut

L'interface web utilise les API vocales natives du navigateur :

- `SpeechRecognition` ou `webkitSpeechRecognition` pour transformer la voix en texte ;
- `speechSynthesis` pour lire les réponses avec les voix installées sur Windows ;
- `/chat` pour envoyer la transcription à Jarvis.

Ce mode ne consomme aucun crédit OpenAI pour la reconnaissance ou la synthèse vocale.
Chrome et Microsoft Edge offrent la meilleure compatibilité.

## Mode OpenAI optionnel

Les endpoints audio OpenAI restent disponibles pour un usage optionnel :

1. l'utilisateur enregistre une question ;
2. l'audio est transcrit ;
3. la transcription est envoyée au chat existant ;
4. la dernière réponse peut être lue à haute voix.

## Endpoints

- `POST /voice/chat`
- `POST /voice/speech`

## Pourquoi ce choix

Ce premier incrément :

- réutilise la mémoire et les citations déjà existantes ;
- évite de dupliquer la logique conversationnelle ;
- permet de valider l'usage de la voix avant d'introduire la complexité d'un flux temps réel.

## Étape suivante

La vraie expérience "Jarvis" passe maintenant aussi par un mode Realtime expérimental :

- latence plus faible ;
- interaction plus naturelle ;
- audio entrant et sortant en continu.

### Realtime actuel

Le navigateur :

1. demande un secret éphémère au backend via `GET /realtime/token` ;
2. ouvre une session WebRTC vers l'API Realtime ;
3. échange ensuite l'audio directement avec le modèle.

La clé API longue durée reste uniquement côté serveur.

### Outils Realtime

Le mode Realtime expose maintenant trois outils utiles :

- `search_knowledge`
- `summarize_cve`
- `triage_alert`

Les appels d'outils sont désormais traités côté serveur via un canal sideband associé au `call_id` de la session WebRTC. Le navigateur ne porte plus la logique métier.
