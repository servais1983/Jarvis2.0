from jarvis_cyber.core.schemas import InvestigationProfileTemplate


INVESTIGATION_PROFILE_TEMPLATES = [
    InvestigationProfileTemplate(
        template_id="account-compromise",
        name="Compromission de compte",
        description="Connexion suspecte, impossible travel, MFA ou identité compromise.",
        trigger_phrases="impossible travel connexion suspecte compte compromis identité MFA",
        default_goal="Déterminer si le compte est compromis et s'il faut escalader.",
        recommended_checks=(
            "Vérifier les connexions impossibles ou inhabituelles.\n"
            "Contrôler les changements MFA et réinitialisations de mot de passe.\n"
            "Rechercher de nouvelles règles de transfert ou autorisations OAuth.\n"
            "Comparer l'activité à l'historique habituel de l'utilisateur."
        ),
    ),
    InvestigationProfileTemplate(
        template_id="phishing",
        name="Phishing",
        description="Emails suspects, liens ou pièces jointes potentiellement malveillants.",
        trigger_phrases="phishing email suspect lien malveillant pièce jointe",
        default_goal="Qualifier le message, estimer l'exposition et recommander les actions immédiates.",
        recommended_checks=(
            "Vérifier l'expéditeur, le domaine et les en-têtes.\n"
            "Analyser les URLs et pièces jointes.\n"
            "Identifier les destinataires et les clics potentiels.\n"
            "Chercher des messages similaires dans l'environnement."
        ),
    ),
    InvestigationProfileTemplate(
        template_id="malware-execution",
        name="Exécution suspecte / malware",
        description="Processus anormaux, scripts, LOLBins et suspicion de malware.",
        trigger_phrases="powershell script suspect malware lolbin exécution anormale",
        default_goal="Établir si l'exécution est malveillante et prioriser le confinement.",
        recommended_checks=(
            "Vérifier la chaîne de processus et la ligne de commande.\n"
            "Contrôler la signature, le hash et la réputation du fichier.\n"
            "Rechercher des comportements de persistance ou de mouvement latéral.\n"
            "Comparer l'activité avec les autres hôtes."
        ),
    ),
    InvestigationProfileTemplate(
        template_id="critical-vulnerability",
        name="Vulnérabilité critique",
        description="CVE critiques, exploitation probable et exposition d'actifs.",
        trigger_phrases="cve vulnérabilité critique exploit kev exposition",
        default_goal="Évaluer l'exposition, l'urgence de remédiation et les mesures compensatoires.",
        recommended_checks=(
            "Confirmer les actifs et versions réellement exposés.\n"
            "Vérifier les signaux d'exploitation active et le statut KEV.\n"
            "Identifier les correctifs disponibles et mesures compensatoires.\n"
            "Prioriser selon criticité, exposition et impact métier."
        ),
    ),
    InvestigationProfileTemplate(
        template_id="data-exfiltration",
        name="Exfiltration de données",
        description="Volumes sortants inhabituels, partage anormal ou fuite suspectée.",
        trigger_phrases="exfiltration fuite données téléchargement massif partage anormal",
        default_goal="Qualifier la fuite potentielle, estimer le périmètre et décider de l'escalade.",
        recommended_checks=(
            "Mesurer le volume, la destination et la temporalité des flux.\n"
            "Identifier les comptes, appareils et jeux de données impliqués.\n"
            "Comparer avec l'activité normale et les droits attendus.\n"
            "Vérifier les partages, liens publics et accès externes."
        ),
    ),
]


def list_investigation_profile_templates() -> list[InvestigationProfileTemplate]:
    return INVESTIGATION_PROFILE_TEMPLATES
