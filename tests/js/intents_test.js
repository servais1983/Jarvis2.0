// Tests des commandes directes : node tests/js/intents_test.js
const assert = require('node:assert/strict');
const path = require('node:path');
const { match } = require(path.join(__dirname, '../../src/jarvis_cyber/web/static/jarvis-intents.js'));

// Ces phrases doivent partir au modèle de langage (null) : elles étaient capturées à tort
const forModel = [
  'combien de temps pour cuire un œuf',
  'combien de kilomètres entre Paris et Bruxelles',
  'explique-moi le système solaire',
  'quel est le statut juridique d\'une SARL',
  'quel jour est né Napoléon',
  'quelle date pour la sortie du prochain film',
  'quelle heure est-il à Tokyo',
  'réinitialise mon mot de passe wifi comment faire',
  'quelles sont mes priorités dans la vie',
  'raconte-moi une blague',
  'ouvre-moi l\'esprit sur la philosophie stoïcienne et ses grands auteurs',
  'montre-moi comment faire une pâte à crêpes',
  'cherche dans mes souvenirs',
  'qu\'est-ce qu\'une CVE et comment sont-elles attribuées par le MITRE exactement',
  'tu peux me dire si tout va bien se passer demain',
  'pourquoi le ciel est bleu',
];
for (const phrase of forModel) {
  assert.equal(match(phrase), null, `devrait aller au modèle : « ${phrase} »`);
}

const expect = (phrase, expected) =>
  assert.deepEqual(match(phrase), expected, `« ${phrase} » → ${JSON.stringify(match(phrase))}`);

// Arrêt
expect('Stop.', { kind: 'stop' });
expect('tais-toi', { kind: 'stop' });

// Mac
expect('Ouvre Safari.', { kind: 'tool', tool: 'ouvrir_application', args: { nom: 'safari' } });
expect('lance Spotify', { kind: 'tool', tool: 'ouvrir_application', args: { nom: 'spotify' } });
expect('ouvre le terminal', { kind: 'tool', tool: 'ouvrir_application', args: { nom: 'terminal' } });
expect('ouvre-moi les notes', { kind: 'tool', tool: 'ouvrir_application', args: { nom: 'notes' } });
expect('ferme Safari', { kind: 'tool', tool: 'fermer_application', args: { nom: 'safari' } });
expect('ouvre YouTube', { kind: 'tool', tool: 'ouvrir_site', args: { url: 'youtube.com' } });
expect('ouvre apple.com', { kind: 'tool', tool: 'ouvrir_site', args: { url: 'apple.com' } });
expect('cherche la météo à Bruxelles', { kind: 'tool', tool: 'recherche_web', args: { requete: 'la météo à bruxelles' } });
expect('recherche iron man sur youtube', { kind: 'tool', tool: 'recherche_youtube', args: { requete: 'iron man' } });
expect('mets le volume à 40', { kind: 'tool', tool: 'regler_volume', args: { pourcentage: 40 } });
expect('volume à 250 %', { kind: 'tool', tool: 'regler_volume', args: { pourcentage: 100 } });
expect('coupe le son', { kind: 'tool', tool: 'regler_volume', args: { pourcentage: 0 } });
expect('pause', { kind: 'tool', tool: 'controle_musique', args: { action: 'pause' } });
expect('chanson suivante', { kind: 'tool', tool: 'controle_musique', args: { action: 'suivant' } });
expect('niveau de batterie', { kind: 'tool', tool: 'etat_machine', args: {} });

// Modules de l'interface
expect('ouvre les dossiers', { kind: 'module', win: 'win-dossiers', label: 'Dossiers' });
expect('affiche l\'inbox', { kind: 'module', win: 'win-inbox', label: 'Inbox' });
expect('ouvre les outils', { kind: 'module', win: 'win-mcp', label: 'Outils MCP' });

// Heure, date, état
expect('Quelle heure est-il ?', { kind: 'time' });
expect('quel jour sommes-nous', { kind: 'date' });
expect('rapport de situation', { kind: 'status' });
expect('présente-toi', { kind: 'identity' });
expect('nouvelle session', { kind: 'new-session' });
expect('quels outils as-tu ?', { kind: 'tools-list' });
expect('combien de dossiers', { kind: 'count', win: 'win-dossiers' });
expect('combien d\'approbations en attente', { kind: 'count', win: 'win-approbations' });

// Calcul, CVE, SOC
expect('calcule (21*2)+8', { kind: 'calc', expression: '(21*2)+8' });
expect('analyse CVE-2021-44228', { kind: 'cve', id: 'CVE-2021-44228' });
expect('brief de quart', { kind: 'action', name: 'shift-brief' });
expect('donne-moi le brief du jour', { kind: 'action', name: 'daily-brief' });

console.log(`intentions : ${forModel.length} phrases laissées au modèle, commandes directes vérifiées`);
