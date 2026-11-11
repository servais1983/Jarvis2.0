/* ========================================================
   JARVIS — commandes directes
   Reconnaît les demandes courtes et sans ambiguïté que Jarvis exécute
   immédiatement, sans passer par le modèle de langage. Tout ce qui n'est
   pas reconnu ici avec certitude part au modèle : mieux vaut laisser le
   modèle répondre que deviner de travers.
   ======================================================== */

(function (root) {
  'use strict';

  const MODULES = [
    [/^(playbooks?|m[ée]thodes?|profils? de t[âa]ches?)$/,            'win-methodes',      'Playbooks'],
    [/^(dossiers?( soc)?|file soc|file de travail)$/,                  'win-dossiers',      'Dossiers'],
    [/^(inbox|livrables?)$/,                                            'win-inbox',         'Inbox'],
    [/^(m[ée]moire|base documentaire|documents)$/,                      'win-memoire',       'Mémoire'],
    [/^(triage|analyste|triage d'alertes?)$/,                           'win-triage',        'Triage'],
    [/^(cve|analyse cve|vuln[ée]rabilit[ée]s?)$/,                       'win-cve',           'Analyse CVE'],
    [/^(investigations?|enqu[êe]tes?)$/,                                'win-investigation', 'Investigation'],
    [/^(rapports?( d'incident)?)$/,                                     'win-rapport',       'Rapport'],
    [/^(veille( cve)?|vigie|watchlists?)$/,                             'win-veille',        'Veille CVE'],
    [/^(routines?|automatisations?)$/,                                  'win-routines',      'Routines'],
    [/^(approbations?)$/,                                               'win-approbations',  'Approbations'],
    [/^(connecteurs?)$/,                                                'win-connecteurs',   'Connecteurs'],
    [/^(profil)$/,                                                      'win-profil',        'Profil'],
    [/^(s[ée]curit[ée]|mfa)$/,                                          'win-securite',      'Sécurité'],
    [/^(console|transcription|historique)$/,                            'win-chat',          'Console'],
    [/^(outils?( mcp)?|mcp)$/,                                          'win-mcp',           'Outils MCP'],
  ];

  const COUNTS = [
    [/^(dossiers?|cas)\b/,          'win-dossiers'],
    [/^approbations?\b/,            'win-approbations'],
    [/^(inbox|livrables?)\b/,       'win-inbox'],
    [/^documents?\b/,               'win-memoire'],
    [/^playbooks?\b/,               'win-methodes'],
    [/^watchlists?\b/,              'win-veille'],
    [/^connecteurs?\b/,             'win-connecteurs'],
  ];

  const SITES = {
    youtube: 'youtube.com', google: 'google.com', gmail: 'mail.google.com', netflix: 'netflix.com',
    github: 'github.com', wikipedia: 'fr.wikipedia.org', linkedin: 'linkedin.com',
    amazon: 'amazon.fr', twitter: 'x.com', facebook: 'facebook.com', chatgpt: 'chatgpt.com',
  };

  const ARTICLE = /^(le |la |les |l'|l’|mon |ma |mes |un |une |moi |l'application |l’application |l'appli |le site |la page )+/;

  function clean(text) {
    return String(text).toLowerCase().replace(/[.!?…]+$/g, '').replace(/\s+/g, ' ').trim();
  }

  function wordCount(text) {
    return text ? text.split(' ').length : 0;
  }

  function stripArticle(text) {
    return text.replace(ARTICLE, '').trim();
  }

  /* Rend une intention { kind, … } ou null si la phrase doit aller au modèle. */
  function match(rawText) {
    const original = String(rawText).replace(/\s+/g, ' ').trim();
    const text = clean(original);
    const words = wordCount(text);
    if (!text) return null;

    if (/^(stop|silence|chut|tais[- ]toi|arr[êe]te|[çc]a suffit)$/.test(text)) return { kind: 'stop' };

    // Identifiant CVE dans une demande courte
    const cve = original.match(/CVE-\d{4}-\d{4,}/i);
    if (cve && words <= 6) return { kind: 'cve', id: cve[0].toUpperCase() };

    // Calcul explicite
    const calc = original.match(/^calcule[:\s]+(.+)$/i);
    if (calc) return { kind: 'calc', expression: calc[1].replace(/[?.!]+$/, '').trim() };

    // Recherches
    let m = text.match(/^(?:cherche|recherche|trouve)(?:[- ]moi)? (.+) sur youtube$/);
    if (m && words <= 14) return { kind: 'tool', tool: 'recherche_youtube', args: { requete: m[1] } };
    m = text.match(/^(?:cherche|recherche|google)(?:[- ]moi)? (?:sur (?:google|internet|le web) )?(.+?)(?: sur (?:google|internet|le web))?$/);
    if (m && words <= 14 && !/^(dans|parmi) /.test(m[1])) {
      return { kind: 'tool', tool: 'recherche_web', args: { requete: m[1] } };
    }

    // Ouvrir : un module de l'interface, un site connu, sinon une application
    m = text.match(/^(?:ouvre|ouvrir|affiche|montre|lance|d[ée]marre)(?:[- ]moi)? (.+)$/);
    if (m && words <= 6) {
      const target = stripArticle(m[1]);
      for (const [re, win, label] of MODULES) {
        if (re.test(target)) return { kind: 'module', win, label };
      }
      if (SITES[target]) return { kind: 'tool', tool: 'ouvrir_site', args: { url: SITES[target] } };
      if (/^[a-z0-9-]+(\.[a-z0-9-]+)+(\/\S*)?$/.test(target)) {
        return { kind: 'tool', tool: 'ouvrir_site', args: { url: target } };
      }
      if (/^(ouvre|ouvrir|lance|d[ée]marre)/.test(text) && wordCount(target) <= 3) {
        return { kind: 'tool', tool: 'ouvrir_application', args: { nom: target } };
      }
      return null;
    }
    m = text.match(/^(?:ferme|quitte)(?:[- ]moi)? (.+)$/);
    if (m && words <= 5 && wordCount(stripArticle(m[1])) <= 3) {
      return { kind: 'tool', tool: 'fermer_application', args: { nom: stripArticle(m[1]) } };
    }

    // Son et musique
    m = text.match(/^(?:mets|r[èe]gle|monte|baisse)? ?(?:le )?(?:volume|son) (?:à|a|sur) (\d{1,3})(?: ?%| pour ?cent)?$/);
    if (m) return { kind: 'tool', tool: 'regler_volume', args: { pourcentage: Math.min(100, Number(m[1])) } };
    if (/^(coupe|couper) le son$/.test(text)) return { kind: 'tool', tool: 'regler_volume', args: { pourcentage: 0 } };
    if (/^(mets (la musique )?(en )?pause|pause|mets pause)$/.test(text)) {
      return { kind: 'tool', tool: 'controle_musique', args: { action: 'pause' } };
    }
    if (/^(lecture|play|relance la musique|remets la musique|mets (de )?la musique)$/.test(text)) {
      return { kind: 'tool', tool: 'controle_musique', args: { action: 'lecture' } };
    }
    if (/^((musique|chanson|piste|morceau) suivante?|suivante?)$/.test(text)) {
      return { kind: 'tool', tool: 'controle_musique', args: { action: 'suivant' } };
    }
    if (/^((musique|chanson|piste|morceau) pr[ée]c[ée]dente?|pr[ée]c[ée]dente?)$/.test(text)) {
      return { kind: 'tool', tool: 'controle_musique', args: { action: 'précédent' } };
    }

    // Heure, date, machine
    if (/^(quelle heure (est[- ]il|il est)|il est quelle heure|donne[- ]moi l'heure|l'heure)$/.test(text)) return { kind: 'time' };
    if (/^((quel jour|quelle date) (sommes[- ]nous|est[- ]on|on est)|on est (quel jour|le combien)|quelle est la date( d'aujourd'hui)?)$/.test(text)) {
      return { kind: 'date' };
    }
    if (/^([ée]tat de la machine|[ée]tat du mac|niveau de (la )?batterie|combien de batterie|(quel est )?l'[ée]tat de la batterie)$/.test(text)) {
      return { kind: 'tool', tool: 'etat_machine', args: {} };
    }

    // État de Jarvis
    if (/^(rapport de situation|statut|status|[ée]tat (du|des) syst[èe]mes?|[ée]tat g[ée]n[ée]ral|tout va bien)$/.test(text)) {
      return { kind: 'status' };
    }
    if (/^(qui es[- ]tu|pr[ée]sente[- ]toi|que sais[- ]tu faire|qu'est[- ]ce que tu sais faire)$/.test(text)) {
      return { kind: 'identity' };
    }
    if (/^(quels outils as[- ]tu|quels sont tes outils|liste (les|tes) outils)$/.test(text)) return { kind: 'tools-list' };
    if (/^(nouvelle session|nouvelle conversation|r[ée]initialise la (session|conversation)|oublie (tout|cette conversation))$/.test(text)) {
      return { kind: 'new-session' };
    }

    // Compteurs : seulement si l'objet compté est connu
    m = text.match(/^combien (?:de |d'|d’)(?:nouveaux |nouvelles )?(.+)$/);
    if (m && words <= 7) {
      for (const [re, win] of COUNTS) {
        if (re.test(m[1])) return { kind: 'count', win };
      }
      return null;
    }

    // Opérations SOC, sur demande courte uniquement
    if (words <= 6) {
      if (/^((fais|donne)[- ]moi )?(le )?(brief|r[ée]sum[ée]) (du jour|quotidien)$/.test(text)) return { kind: 'action', name: 'daily-brief' };
      if (/^((fais|donne)[- ]moi )?(le )?brief de (quart|shift)$/.test(text)) return { kind: 'action', name: 'shift-brief' };
      if (/^(contr[ôo]le|v[ée]rifie) les sla$/.test(text)) return { kind: 'action', name: 'sla' };
      if (/^((montre|donne)[- ]moi )?(la )?file de travail$|^par quoi je commence$/.test(text)) return { kind: 'action', name: 'queue' };
    }

    return null;
  }

  const api = { match, clean };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.JarvisIntents = api;
})(typeof window !== 'undefined' ? window : globalThis);
