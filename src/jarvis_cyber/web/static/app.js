const runtimeStatus = document.querySelector("#runtime-status");
const authStatus = document.querySelector("#auth-status");
const authMessage = document.querySelector("#auth-message");
const logoutButton = document.querySelector("#logout-button");
const sessionConsole = document.querySelector("#session-console");
const sessionList = document.querySelector("#session-list");
const mfaConsole = document.querySelector("#mfa-console");
const mfaStatus = document.querySelector("#mfa-status");
const mfaEnrollForm = document.querySelector("#mfa-enroll-form");
const mfaVerifyForm = document.querySelector("#mfa-verify-form");
const mfaEnrollmentResult = document.querySelector("#mfa-enrollment-result");
const mfaRecoveryCodesButton = document.querySelector("#mfa-recovery-codes-button");
const mfaRecoveryCodesResult = document.querySelector("#mfa-recovery-codes-result");
const mfaFactorList = document.querySelector("#mfa-factor-list");
const adminConsole = document.querySelector("#admin-console");
const adminUserList = document.querySelector("#admin-user-list");
const auditEventList = document.querySelector("#audit-event-list");
const auditFilterForm = document.querySelector("#audit-filter-form");
const auditEventTypeInput = document.querySelector("#audit-event-type");
const auditExportButton = document.querySelector("#audit-export-button");
const profileForm = document.querySelector("#profile-form");
const profileStatus = document.querySelector("#profile-status");
const taskProfileForm = document.querySelector("#task-profile-form");
const taskProfileList = document.querySelector("#task-profile-list");
const playbookForm = document.querySelector("#playbook-form");
const playbookList = document.querySelector("#playbook-list");
const playbookTaskProfileSelect = document.querySelector("#playbook-task-profile");
const investigationProfileForm = document.querySelector("#investigation-profile-form");
const investigationProfileList = document.querySelector("#investigation-profile-list");
const investigationProfileSelect = document.querySelector("#investigation-profile");
const investigationProfileTemplateSelect = document.querySelector("#investigation-profile-template");
const prefillInvestigationProfileTemplateButton = document.querySelector(
  "#prefill-investigation-profile-template",
);
const investigationCaseList = document.querySelector("#investigation-case-list");
const investigationCaseDetail = document.querySelector("#investigation-case-detail");
const socQueueList = document.querySelector("#soc-queue-list");
const refreshSocQueueButton = document.querySelector("#refresh-soc-queue");
const shiftBriefResult = document.querySelector("#shift-brief-result");
const refreshShiftBriefButton = document.querySelector("#refresh-shift-brief");
const slaWatchResult = document.querySelector("#sla-watch-result");
const refreshSlaWatchButton = document.querySelector("#refresh-sla-watch");
const watchlistForm = document.querySelector("#watchlist-form");
const watchlistList = document.querySelector("#watchlist-list");
const dailyBriefForm = document.querySelector("#daily-brief-form");
const dailyBriefResult = document.querySelector("#daily-brief-result");
const automationForm = document.querySelector("#automation-form");
const automationList = document.querySelector("#automation-list");
const automationRunList = document.querySelector("#automation-run-list");
const runDueAutomationsButton = document.querySelector("#run-due-automations");
const inboxList = document.querySelector("#inbox-list");
const refreshInboxButton = document.querySelector("#refresh-inbox");
const approvalList = document.querySelector("#approval-list");
const refreshApprovalsButton = document.querySelector("#refresh-approvals");
const connectorStatusList = document.querySelector("#connector-status-list");
const chatLog = document.querySelector("#chat-log");
const knowledgeList = document.querySelector("#knowledge-list");
const voiceRecordButton = document.querySelector("#voice-record");
const voiceSpeakLastButton = document.querySelector("#voice-speak-last");
const realtimeConnectButton = document.querySelector("#realtime-connect");
const realtimeDisconnectButton = document.querySelector("#realtime-disconnect");
const voiceStatus = document.querySelector("#voice-status");
let lastAssistantAnswer = "";
let investigationProfileTemplates = [];
let sentinelQueryTemplates = [];
let lastInvestigationCasePayload = null;
let selectedInvestigationCaseId = null;
let latestEnrichmentPlans = {};
let realtimePeerConnection;
let realtimeDataChannel;
let realtimeLocalStream;
let realtimeCallId;
let browserSpeechRecognition;
let browserRealtimeActive = false;
let browserVoiceBusy = false;
let authToken = sessionStorage.getItem("jarvis_auth_token");
let authRequired = false;
let currentUser = null;
let pendingMfaFactorId = null;
let currentMfaStatus = null;

function authHeaders() {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function errorMsg(error) {
  if (!error) return "Erreur inconnue.";
  try {
    const parsed = JSON.parse(error.message);
    return parsed.detail || parsed.message || error.message;
  } catch {
    return error.message || "Erreur inconnue.";
  }
}

function list(items) {
  if (!items?.length) return "<p class=\"subtle\">Aucun élément.</p>";
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function pill(value) {
  const normalized = (value || "unknown").toLowerCase();
  return `<span class="pill ${escapeHtml(normalized)}">${escapeHtml(value || "unknown")}</span>`;
}

function renderCitations(citations = []) {
  if (!citations.length) return "";

  return `
    <div class="citations">
      <strong>Sources internes</strong>
      <ul>
        ${citations
          .map(
            (citation) => `
              <li>
                <span>${escapeHtml(citation.citation_id)}</span>
                <strong>${escapeHtml(citation.title)}</strong>
                ${citation.source ? `· ${escapeHtml(citation.source)}` : ""}
                <p>${escapeHtml(citation.snippet)}</p>
              </li>
            `,
          )
          .join("")}
      </ul>
    </div>
  `;
}

function appendMessage(role, content, citations = []) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;
  wrapper.innerHTML = `
    <span>${role === "assistant" ? "Jarvis" : "Toi"}</span>
    <p>${escapeHtml(content)}</p>
    ${role === "assistant" ? renderCitations(citations) : ""}
  `;
  chatLog.appendChild(wrapper);
  chatLog.scrollTop = chatLog.scrollHeight;
  if (role === "assistant") {
    lastAssistantAnswer = content;
  }
}

async function hydrateStatus() {
  try {
    const data = await request("/health");
    runtimeStatus.textContent = `En ligne · ${data.environment}`;
    authRequired = data.auth_required;
  } catch (error) {
    runtimeStatus.textContent = "Indisponible";
  }
}

function updateAuthUi(user = null) {
  currentUser = user;
  if (user) {
    authStatus.textContent = "Connecté";
    authStatus.className = "auth-chip connected";
    authMessage.textContent = `Session active : ${user.email} | ${user.role}`;
    sessionConsole.classList.toggle("hidden", !authToken);
    mfaConsole.classList.toggle("hidden", !authToken);
    if (authToken) {
      refreshSessions();
      refreshMfaStatus();
    }
    adminConsole.classList.toggle("hidden", user.role !== "admin");
    if (user.role === "admin") {
      refreshAdminUsers();
      refreshAuditEvents();
    }
    return;
  }

  sessionConsole.classList.add("hidden");
  mfaConsole.classList.add("hidden");
  sessionList.className = "session-list empty";
  sessionList.textContent = "Aucune session active chargée.";
  mfaStatus.textContent = "État MFA non chargé.";
  mfaEnrollmentResult.className = "result empty";
  mfaEnrollmentResult.textContent = "Aucun facteur en cours d'enrôlement.";
  mfaRecoveryCodesResult.className = "result empty";
  mfaRecoveryCodesResult.textContent = "Aucun code de récupération généré dans cette session.";
  mfaFactorList.className = "method-list empty";
  mfaFactorList.textContent = "Aucun facteur chargé.";
  currentMfaStatus = null;
  adminConsole.classList.add("hidden");
  adminUserList.className = "admin-user-list empty";
  adminUserList.textContent = "Aucun utilisateur chargé.";
  authStatus.textContent = authRequired ? "Connexion requise" : "Mode local";
  authStatus.className = `auth-chip${authRequired ? " required" : ""}`;
  authMessage.textContent = authRequired
    ? "Connecte-toi pour utiliser les fonctions protégées."
    : "Mode local actif : tu peux tester l'application sans compte.";
}

async function hydrateCurrentUser() {
  try {
    const user = await request("/auth/me");
    updateAuthUi(user);
  } catch (error) {
    authToken = null;
    sessionStorage.removeItem("jarvis_auth_token");
    updateAuthUi();
  }
}

function renderProfile(profile) {
  document.querySelector("#profile-display-name").value = profile.display_name || "";
  document.querySelector("#profile-job-title").value = profile.job_title || "";
  document.querySelector("#profile-organization").value = profile.organization || "";
  document.querySelector("#profile-timezone").value = profile.timezone || "";
  document.querySelector("#profile-language").value = profile.preferred_language || "fr";
  document.querySelector("#profile-response-style").value = profile.response_style || "balanced";
  document.querySelector("#profile-approval-preference").value =
    profile.approval_preference || "ask_before_sensitive_actions";
  document.querySelector("#profile-environment-summary").value = profile.environment_summary || "";
  document.querySelector("#profile-focus-areas").value = profile.focus_areas || "";
  profileStatus.textContent = "Profil chargé.";
}

async function refreshProfile() {
  try {
    const profile = await request("/profile/me");
    renderProfile(profile);
  } catch (error) {
    profileStatus.textContent = "Impossible de charger le profil.";
  }
}

async function refreshMfaStatus() {
  try {
    const status = await request("/auth/mfa/status");
    currentMfaStatus = status;
    mfaStatus.textContent = status.enabled
      ? `MFA actif · ${status.factors.length} facteur(s) enregistré(s) · ${status.unused_recovery_codes} code(s) de récupération disponible(s).`
      : "MFA non activé.";
    renderMfaFactors(status);
  } catch (error) {
    mfaStatus.textContent = "Impossible de charger l'état MFA.";
    mfaFactorList.className = "method-list empty";
    mfaFactorList.textContent = "Impossible de charger les facteurs MFA.";
  }
}

function renderMfaFactors(status) {
  const factors = status?.factors || [];
  if (!factors.length) {
    mfaFactorList.className = "method-list empty";
    mfaFactorList.textContent = "Aucun facteur MFA enregistré.";
    return;
  }

  const activeVerifiedFactors = factors.filter(
    (factor) => factor.verified_at && !factor.disabled_at,
  ).length;
  mfaFactorList.className = "method-list";
  mfaFactorList.innerHTML = factors
    .map((factor) => {
      const active = factor.verified_at && !factor.disabled_at;
      const state = factor.disabled_at
        ? "désactivé"
        : factor.verified_at
          ? "actif"
          : "en attente de vérification";
      return `
        <article class="method-card">
          <div>
            <strong>${escapeHtml(factor.label || factor.factor_type.toUpperCase())}</strong>
            <p>${escapeHtml(factor.factor_type.toUpperCase())} · ${escapeHtml(state)}</p>
          </div>
          ${
            active
              ? `
                <form class="stack compact-stack" data-disable-mfa-factor="${escapeHtml(factor.factor_id)}">
                  <label>
                    Code TOTP ou code de récupération
                    <input name="code" placeholder="123456" />
                  </label>
                  ${
                    activeVerifiedFactors <= 1
                      ? `
                        <label class="inline-check">
                          <input name="allow_disable_last_factor" type="checkbox" />
                          Autoriser la désactivation du dernier facteur
                        </label>
                      `
                      : ""
                  }
                  <button type="submit">Désactiver ce facteur</button>
                </form>
              `
              : ""
          }
        </article>
      `;
    })
    .join("");
}

function renderTaskProfiles(taskProfiles = []) {
  playbookTaskProfileSelect.innerHTML = `
    <option value="">Aucun</option>
    ${taskProfiles
      .map(
        (profile) => `<option value="${escapeHtml(profile.profile_id)}">${escapeHtml(profile.name)}</option>`,
      )
      .join("")}
  `;

  if (!taskProfiles.length) {
    taskProfileList.className = "method-list empty";
    taskProfileList.textContent = "Aucun profil de tâche chargé.";
    return;
  }

  taskProfileList.className = "method-list";
  taskProfileList.innerHTML = taskProfiles
    .map(
      (profile) => `
        <article class="method-card">
          <div>
            <strong>${escapeHtml(profile.name)}</strong>
            <p>${escapeHtml(profile.description || "Sans description")}</p>
          </div>
          <p>${escapeHtml(profile.output_format)}</p>
          <footer>
            <button data-delete-task-profile="${escapeHtml(profile.profile_id)}" type="button">Supprimer</button>
          </footer>
        </article>
      `,
    )
    .join("");
}

async function refreshTaskProfiles() {
  try {
    renderTaskProfiles(await request("/task-profiles"));
  } catch (error) {
    taskProfileList.className = "method-list empty";
    taskProfileList.textContent = "Impossible de charger les profils de tâches.";
  }
}

function renderPlaybooks(playbooks = []) {
  if (!playbooks.length) {
    playbookList.className = "method-list empty";
    playbookList.textContent = "Aucun playbook chargé.";
    return;
  }

  playbookList.className = "method-list";
  playbookList.innerHTML = playbooks
    .map(
      (playbook) => `
        <article class="method-card">
          <div>
            <strong>${escapeHtml(playbook.title)}</strong>
            <p>${escapeHtml(playbook.purpose)}</p>
          </div>
          <p>${escapeHtml(playbook.steps)}</p>
          <footer>
            <button data-delete-playbook="${escapeHtml(playbook.playbook_id)}" type="button">Supprimer</button>
          </footer>
        </article>
      `,
    )
    .join("");
}

function renderInvestigationProfiles(profiles = []) {
  investigationProfileSelect.innerHTML = `
    <option value="">Automatique / aucun</option>
    ${profiles
      .map(
        (profile) =>
          `<option value="${escapeHtml(profile.profile_id)}">${escapeHtml(profile.name)}</option>`,
      )
      .join("")}
  `;

  if (!profiles.length) {
    investigationProfileList.className = "method-list empty";
    investigationProfileList.textContent = "Aucun profil d'investigation chargé.";
    return;
  }

  investigationProfileList.className = "method-list";
  investigationProfileList.innerHTML = profiles
    .map(
      (profile) => `
        <article class="method-card">
          <div>
            <strong>${escapeHtml(profile.name)}</strong>
            <p>${escapeHtml(profile.description || "Sans description")}</p>
          </div>
          <p>${escapeHtml(profile.trigger_phrases || "Sans déclencheur")}</p>
          <p>${escapeHtml(profile.recommended_checks || "Sans checklist")}</p>
          <p>${profile.include_recent_github ? "GitHub récent activé" : "GitHub récent désactivé"}</p>
          <footer>
            <button data-delete-investigation-profile="${escapeHtml(profile.profile_id)}" type="button">Supprimer</button>
          </footer>
        </article>
      `,
    )
    .join("");
}

function renderInvestigationProfileTemplates(templates = []) {
  investigationProfileTemplates = templates;
  investigationProfileTemplateSelect.innerHTML = `
    <option value="">Choisir un modèle</option>
    ${templates
      .map(
        (template) =>
          `<option value="${escapeHtml(template.template_id)}">${escapeHtml(template.name)}</option>`,
      )
      .join("")}
  `;
}

function sentinelTemplateOptions() {
  return `
    <option value="">Requête libre</option>
    ${sentinelQueryTemplates
      .map(
        (template) =>
          `<option value="${escapeHtml(template.template_id)}">${escapeHtml(template.category)} — ${escapeHtml(template.name)}</option>`,
      )
      .join("")}
  `;
}

async function refreshSentinelQueryTemplates() {
  try {
    sentinelQueryTemplates = await request("/sentinel-query-templates");
  } catch (error) {
    sentinelQueryTemplates = [];
  }
}


function renderEnrichmentPlan(plan) {
  latestEnrichmentPlans[plan.case_id] = plan;
  const recommendations = plan.recommendations.length
    ? plan.recommendations
        .map(
          (item) => `
            <article class="checklist-item">
              <div>
                <strong>${escapeHtml(item.priority.toUpperCase())} - ${escapeHtml(item.title)}</strong>
                <p>${escapeHtml(item.rationale)}</p>
                <p>
                  Connecteur : ${escapeHtml(item.connector)} &middot; Action : ${escapeHtml(item.action)}
                  ${item.sentinel_template_id ? ` &middot; Pack KQL : ${escapeHtml(item.sentinel_template_id)}` : ""}
                  ${item.already_enriched ? " &middot; D&eacute;j&agrave; pr&eacute;sent dans les preuves" : ""}
                </p>
                ${Object.keys(item.suggested_parameters || {}).length ? `<p>Param&egrave;tres propos&eacute;s : ${escapeHtml(JSON.stringify(item.suggested_parameters))}</p>` : ""}
                ${item.required_inputs.length ? `<p>Entr&eacute;es &agrave; compl&eacute;ter : ${escapeHtml(item.required_inputs.join(", "))}</p>` : ""}
                <button
                  data-prefill-enrichment-case="${escapeHtml(plan.case_id)}"
                  data-prefill-enrichment-recommendation="${escapeHtml(item.recommendation_id)}"
                  type="button"
                >Pr&eacute;remplir ce formulaire</button>
              </div>
            </article>
          `,
        )
        .join("")
    : "<p>Aucune recommandation sp&eacute;cifique.</p>";
  return `
    <strong>Plan d'enrichissement conseill&eacute;</strong>
    <p>Cat&eacute;gorie inf&eacute;r&eacute;e : ${escapeHtml(plan.inferred_category)} &middot; confiance ${Math.round(plan.confidence * 100)}%</p>
    <div class="case-checklist">${recommendations}</div>
    <div><strong>Garde-fous</strong>${list(plan.safety_notes)}</div>
  `;
}

function renderIncidentView(view) {
  const indicators = Object.keys(view.indicators || {}).length
    ? list(Object.entries(view.indicators).map(([key, value]) => `${key}: ${value}`))
    : "<p class=\"subtle\">Aucun indicateur structuré détecté.</p>";
  const sections = view.sections.length
    ? view.sections
        .map(
          (section) => `
            <article class="checklist-item">
              <div>
                <strong>${escapeHtml(section.title)} ${pill(section.status)}</strong>
                ${list(section.items)}
              </div>
            </article>
          `,
        )
        .join("")
    : "<p>Aucune section disponible.</p>";
  return `
    <strong>Vue incident</strong>
    <p>${escapeHtml(view.headline)}</p>
    <p>Sc&eacute;nario : ${escapeHtml(view.inferred_category)} &middot; confiance ${Math.round(view.confidence * 100)}%</p>
    <div><strong>Indicateurs pivot</strong>${indicators}</div>
    <div class="case-checklist">${sections}</div>
    <div><strong>Questions de pilotage</strong>${list(view.next_questions)}</div>
    <p class="subtle">${escapeHtml(view.analyst_note)}</p>
  `;
}

function renderClosureAssistant(closure) {
  const checks = closure.checks.length
    ? closure.checks
        .map(
          (check) => `
            <article class="checklist-item">
              <div>
                <strong>${escapeHtml(check.title)} ${pill(check.status)}</strong>
                <p>${escapeHtml(check.detail)}</p>
              </div>
            </article>
          `,
        )
        .join("")
    : "<p>Aucune vérification de clôture.</p>";
  return `
    <strong>Assistant de clôture</strong>
    <p>${escapeHtml(closure.headline)}</p>
    <div class="result-grid">
      <div class="metric"><span>Score</span>${closure.readiness_score}%</div>
      <div class="metric"><span>État</span>${pill(closure.state)}</div>
      <div class="metric"><span>Rapport</span>${closure.report_recommended ? "recommandé" : "à différer"}</div>
    </div>
    <div class="case-checklist">${checks}</div>
    <div><strong>Blocages</strong>${list(closure.blockers)}</div>
    <p><strong>Prochaine action :</strong> ${escapeHtml(closure.recommended_next_action)}</p>
  `;
}

function enrichmentPlanTarget(caseId) {
  return investigationCaseDetail.querySelector(
    `[data-investigation-enrichment-plan-result="${caseId}"]`,
  );
}

function setEnrichmentPlanStatus(caseId, message) {
  const target = enrichmentPlanTarget(caseId);
  if (!target) return;
  const status = document.createElement("p");
  status.className = "subtle";
  status.textContent = message;
  target.appendChild(status);
}

function setInputValue(form, name, value) {
  if (!form || value === undefined || value === null || value === "") return;
  const field = form.querySelector(`[name="${name}"]`);
  if (field) field.value = value;
}

async function prefillInvestigationRecommendation(caseId, recommendation) {
  const parameters = recommendation.suggested_parameters || {};
  if (recommendation.connector === "microsoft_entra_id") {
    const form = investigationCaseDetail.querySelector(`[data-investigation-entra-form="${caseId}"]`);
    setInputValue(form, "user_principal_name", parameters.user_principal_name);
    setEnrichmentPlanStatus(caseId, "Formulaire Entra ID prérempli. Vérifie puis lance l'enrichissement si c'est pertinent.");
    return;
  }

  if (recommendation.connector === "microsoft_defender") {
    const form = investigationCaseDetail.querySelector(`[data-investigation-defender-form="${caseId}"]`);
    setInputValue(form, "query", parameters.query);
    setEnrichmentPlanStatus(caseId, "Formulaire Defender prérempli. Rien n'a été interrogé automatiquement.");
    return;
  }

  if (recommendation.connector === "microsoft_sentinel") {
    const form = investigationCaseDetail.querySelector(`[data-investigation-sentinel-form="${caseId}"]`);
    if (!form) return;
    setInputValue(form, "template_id", recommendation.sentinel_template_id);
    form.querySelector('[name="template_parameters"]').value = JSON.stringify(parameters, null, 2);
    if (recommendation.sentinel_template_id && !recommendation.required_inputs.length) {
      const rendered = await request(`/sentinel-query-templates/${recommendation.sentinel_template_id}/render`, {
        method: "POST",
        body: JSON.stringify({ parameters }),
      });
      setInputValue(form, "query", rendered.query);
      setInputValue(form, "timespan", rendered.timespan);
      setEnrichmentPlanStatus(caseId, "Pack Sentinel prérempli et KQL généré localement. La requête n'a pas été exécutée.");
      return;
    }
    setEnrichmentPlanStatus(caseId, "Pack Sentinel sélectionné. Complète les paramètres manquants avant de générer la KQL.");
  }
}


async function refreshInvestigationProfiles() {
  try {
    renderInvestigationProfiles(await request("/investigation-profiles"));
  } catch (error) {
    investigationProfileList.className = "method-list empty";
    investigationProfileList.textContent = "Impossible de charger les profils d'investigation.";
  }
}

async function refreshInvestigationProfileTemplates() {
  try {
    renderInvestigationProfileTemplates(await request("/investigation-profile-templates"));
  } catch (error) {
    investigationProfileTemplateSelect.innerHTML = '<option value="">Modèles indisponibles</option>';
  }
}

function renderInvestigationCaseList(cases = []) {
  if (!cases.length) {
    investigationCaseList.className = "method-list empty";
    investigationCaseList.textContent = "Aucun dossier d'investigation ouvert.";
    return;
  }
  investigationCaseList.className = "method-list";
  investigationCaseList.innerHTML = cases
    .map(
      (item) => `
        <article class="method-card ${item.case_id === selectedInvestigationCaseId ? "selected-card" : ""}">
          <div>
            <strong>${escapeHtml(item.title)}</strong>
            <p>${escapeHtml(item.status)}</p>
          </div>
          <footer>
            <button data-open-investigation-case="${escapeHtml(item.case_id)}" type="button">Ouvrir</button>
            <button data-delete-investigation-case="${escapeHtml(item.case_id)}" type="button">Supprimer</button>
          </footer>
        </article>
      `,
    )
    .join("");
}

function renderSOCQueue(queue) {
  const items = queue?.items || [];
  if (!items.length) {
    socQueueList.className = "method-list empty";
    socQueueList.textContent = "Aucun dossier actif à prioriser.";
    return;
  }
  socQueueList.className = "method-list";
  socQueueList.innerHTML = items
    .map(
      (item) => `
        <article class="method-card ${item.case_id === selectedInvestigationCaseId ? "selected-card" : ""}">
          <div>
            <strong>${escapeHtml(item.title)}</strong>
            <p>${pill(item.priority)} &middot; score ${item.score} &middot; ${escapeHtml(item.inferred_category)}</p>
            <p>${escapeHtml(item.next_action)}</p>
            <p>${escapeHtml(item.reasons.slice(0, 3).join(" | "))}</p>
          </div>
          <footer>
            <button data-open-investigation-case="${escapeHtml(item.case_id)}" type="button">Ouvrir</button>
          </footer>
        </article>
      `,
    )
    .join("");
}

function queueItemSummary(item) {
  return `${item.priority.toUpperCase()} · ${item.title} · ${item.next_action}`;
}

function renderShiftBrief(brief) {
  shiftBriefResult.className = "result";
  shiftBriefResult.innerHTML = `
    <div class="result-grid">
      <div class="metric"><span>Actifs</span>${brief.total_active_cases}</div>
      <div class="metric"><span>Critiques</span>${brief.critical_cases}</div>
      <div class="metric"><span>Hauts</span>${brief.high_cases}</div>
    </div>
    <strong>${escapeHtml(brief.headline)}</strong>
    <div><strong>À traiter maintenant</strong>${list(brief.focus_now.map(queueItemSummary))}</div>
    <div><strong>Bloqués ou sous-documentés</strong>${list(brief.blocked_or_under_evidenced.map(queueItemSummary))}</div>
    <div><strong>Prêts pour synthèse / rapport</strong>${list(brief.ready_for_report.map(queueItemSummary))}</div>
    <div><strong>Peut attendre</strong>${list(brief.can_wait.map(queueItemSummary))}</div>
    <div><strong>Guidage opérateur</strong>${list(brief.operator_guidance)}</div>
    <p class="subtle">Généré le ${escapeHtml(brief.generated_at)}</p>
  `;
}

async function refreshShiftBrief() {
  try {
    renderShiftBrief(await request("/investigation-cases/shift-brief"));
  } catch (error) {
    shiftBriefResult.className = "result empty";
    shiftBriefResult.textContent = "Impossible de générer le brief de quart.";
  }
}

function renderSLAWatch(sla) {
  const urgentItems = (sla.items || []).filter((item) => item.state !== "ok").slice(0, 8);
  slaWatchResult.className = "result";
  slaWatchResult.innerHTML = `
    <div class="result-grid">
      <div class="metric"><span>Actifs</span>${sla.total_active_cases}</div>
      <div class="metric"><span>SLA dépassés</span>${sla.breached_count}</div>
      <div class="metric"><span>Alertes</span>${sla.warning_count}</div>
    </div>
    <strong>Surveillance SLA SOC</strong>
    ${
      urgentItems.length
        ? `<div class="case-checklist">
            ${urgentItems
              .map(
                (item) => `
                  <article class="checklist-item">
                    <div>
                      <strong>${escapeHtml(item.title)} ${pill(item.state)}</strong>
                      <p>${escapeHtml(item.priority)} · âge ${item.age_minutes} min · inactif ${item.idle_minutes} min</p>
                      ${list([...(item.breaches || []), ...(item.warnings || [])])}
                      <p>${escapeHtml(item.next_action)}</p>
                    </div>
                  </article>
                `,
              )
              .join("")}
          </div>`
        : "<p>Aucun dépassement ou avertissement SLA.</p>"
    }
    <p class="subtle">Généré le ${escapeHtml(sla.generated_at)}</p>
  `;
}

async function refreshSLAWatch() {
  try {
    renderSLAWatch(await request("/investigation-cases/sla"));
  } catch (error) {
    slaWatchResult.className = "result empty";
    slaWatchResult.textContent = "Impossible de vérifier les SLA.";
  }
}

async function refreshSOCQueue() {
  try {
    renderSOCQueue(await request("/investigation-cases/queue"));
  } catch (error) {
    socQueueList.className = "method-list empty";
    socQueueList.textContent = "Impossible de charger la file SOC.";
  }
}

function renderInvestigationCaseDetail(detail) {
  if (!detail) {
    investigationCaseDetail.className = "result empty";
    investigationCaseDetail.textContent =
      "Lance une investigation puis crée un dossier pour suivre l'avancement.";
    return;
  }
  const {
    case: investigationCase,
    checklist_items,
    notes,
    events,
    evidence,
    hypotheses,
    summary,
  } = detail;
  investigationCaseDetail.className = "result";
  investigationCaseDetail.innerHTML = `
    <div class="result-grid">
      <div class="metric"><span>Statut</span>${pill(investigationCase.status)}</div>
      <div class="metric"><span>Progression</span>${Math.round(summary.completion_ratio * 100)}%</div>
      <div class="metric"><span>Faits</span>${summary.done_checks}/${summary.total_checks}</div>
      <div class="metric"><span>Bloqués</span>${summary.blocked_checks}</div>
      <div class="metric"><span>Hypothèses ouvertes</span>${summary.open_hypotheses}</div>
    </div>
    <div>
      <strong>${escapeHtml(investigationCase.title)}</strong>
      <p>${escapeHtml(investigationCase.goal || "Aucun objectif précisé.")}</p>
    </div>
    <button data-investigation-summary="${escapeHtml(investigationCase.case_id)}" type="button">
      Générer une synthèse d'avancement
    </button>
    <button data-investigation-report="${escapeHtml(investigationCase.case_id)}" type="button">
      Générer un rapport final
    </button>
    <button data-investigation-enrichment-plan="${escapeHtml(investigationCase.case_id)}" type="button">
      Proposer un plan d'enrichissement
    </button>
    <button data-investigation-incident-view="${escapeHtml(investigationCase.case_id)}" type="button">
      Afficher la vue incident
    </button>
    <button data-investigation-closure-assistant="${escapeHtml(investigationCase.case_id)}" type="button">
      Assistant de clôture
    </button>
    <form data-investigation-entra-form="${escapeHtml(investigationCase.case_id)}" class="stack">
      <label>
        Enrichir avec Microsoft Entra ID
        <input name="user_principal_name" placeholder="utilisateur@entreprise.com" />
      </label>
      <label>
        Nombre de connexions ? examiner
        <input name="sign_in_limit" type="number" min="1" max="20" value="5" />
      </label>
      <button type="submit">Ajouter les faits Entra ID au dossier</button>
    </form>
    <div class="subtle" data-investigation-summary-result="${escapeHtml(investigationCase.case_id)}"></div>
    <div class="subtle" data-investigation-report-result="${escapeHtml(investigationCase.case_id)}"></div>
    <div class="subtle" data-investigation-enrichment-plan-result="${escapeHtml(investigationCase.case_id)}"></div>
    <div class="subtle" data-investigation-incident-view-result="${escapeHtml(investigationCase.case_id)}"></div>
    <div class="subtle" data-investigation-closure-assistant-result="${escapeHtml(investigationCase.case_id)}"></div>
    <div class="subtle" data-investigation-entra-result="${escapeHtml(investigationCase.case_id)}"></div>
    <form data-investigation-defender-form="${escapeHtml(investigationCase.case_id)}" class="stack">
      <label>
        Enrichir avec Microsoft Defender
        <input name="query" placeholder="utilisateur, machine, alerte..." />
      </label>
      <label>
        S?v?rit? optionnelle
        <input name="severity" placeholder="high, medium, low..." />
      </label>
      <button type="submit">Ajouter les faits Defender au dossier</button>
    </form>
    <div class="subtle" data-investigation-defender-result="${escapeHtml(investigationCase.case_id)}"></div>
    <form data-investigation-sentinel-form="${escapeHtml(investigationCase.case_id)}" class="stack">
      <label>
        Pack KQL Sentinel
        <select name="template_id">${sentinelTemplateOptions()}</select>
      </label>
      <label>
        Paramètres du modèle (JSON)
        <textarea name="template_parameters" rows="3" placeholder='{"user_principal_name":"utilisateur@entreprise.com"}'></textarea>
      </label>
      <button data-render-sentinel-template="${escapeHtml(investigationCase.case_id)}" type="button">Préremplir la requête KQL</button>
      <label>
        Enrichir avec Sentinel / KQL
        <textarea name="query" rows="4" placeholder="SigninLogs | where UserPrincipalName == 'utilisateur@entreprise.com' | take 10"></textarea>
      </label>
      <label>
        Timespan optionnel
        <input name="timespan" placeholder="PT24H" />
      </label>
      <button type="submit">Ajouter les résultats KQL au dossier</button>
    </form>
    <div class="subtle" data-investigation-sentinel-result="${escapeHtml(investigationCase.case_id)}"></div>
    <label>
      Statut du dossier
      <select data-investigation-case-status="${escapeHtml(investigationCase.case_id)}">
        <option value="open" ${investigationCase.status === "open" ? "selected" : ""}>Ouvert</option>
        <option value="monitoring" ${investigationCase.status === "monitoring" ? "selected" : ""}>Surveillance</option>
        <option value="closed" ${investigationCase.status === "closed" ? "selected" : ""}>Clos</option>
      </select>
    </label>
    <div>
      <strong>Prochaines vérifications</strong>
      ${list(summary.next_open_checks)}
    </div>
    <div>
      <strong>Checklist</strong>
      <div class="case-checklist">
        ${checklist_items
          .map(
            (item) => `
              <article class="checklist-item">
                <div>
                  <strong>${escapeHtml(item.title)}</strong>
                  <p>${escapeHtml(item.notes || "Aucune note spécifique.")}</p>
                </div>
                <div class="button-row">
                  <button data-checklist-status="todo" data-case-id="${escapeHtml(investigationCase.case_id)}" data-item-id="${escapeHtml(item.item_id)}" type="button">À faire</button>
                  <button data-checklist-status="done" data-case-id="${escapeHtml(investigationCase.case_id)}" data-item-id="${escapeHtml(item.item_id)}" type="button">Fait</button>
                  <button data-checklist-status="blocked" data-case-id="${escapeHtml(investigationCase.case_id)}" data-item-id="${escapeHtml(item.item_id)}" type="button">Bloqué</button>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    </div>
    <form data-investigation-note-form="${escapeHtml(investigationCase.case_id)}" class="stack">
      <label>
        Ajouter une note
        <textarea rows="3" placeholder="Observation, hypothèse, décision..."></textarea>
      </label>
      <button type="submit">Ajouter la note</button>
    </form>
    <form data-investigation-event-form="${escapeHtml(investigationCase.case_id)}" class="stack">
      <label>
        Ajouter un événement
        <input name="occurred_at" placeholder="2026-05-18T08:00:00Z" />
      </label>
      <label>
        Titre
        <input name="title" placeholder="Connexion Bruxelles" />
      </label>
      <label>
        Description
        <textarea name="description" rows="2" placeholder="Détail factuel de l'événement"></textarea>
      </label>
      <button type="submit">Ajouter l'événement</button>
    </form>
    <div>
      <strong>Timeline</strong>
      ${
        events.length
          ? list(events.map((item) => `${item.occurred_at} — ${item.title}`))
          : "<p>Aucun événement.</p>"
      }
    </div>
    <form data-investigation-evidence-form="${escapeHtml(investigationCase.case_id)}" class="stack">
      <label>
        Ajouter une preuve
        <input name="title" placeholder="Journal Entra ID" />
      </label>
      <label>
        Source
        <input name="source" placeholder="entra" />
      </label>
      <label>
        Description
        <textarea name="description" rows="2" placeholder="Ce que cette preuve montre"></textarea>
      </label>
      <button type="submit">Ajouter la preuve</button>
    </form>
    <div>
      <strong>Preuves</strong>
      ${
        evidence.length
          ? list(
              evidence.map(
                (item) =>
                  `${item.title}${item.source ? ` (${item.source})` : ""}`,
              ),
            )
          : "<p>Aucune preuve.</p>"
      }
    </div>
    <form data-investigation-hypothesis-form="${escapeHtml(investigationCase.case_id)}" class="stack">
      <label>
        Ajouter une hypothèse
        <textarea name="statement" rows="2" placeholder="Le compte est compromis."></textarea>
      </label>
      <label>
        Justification initiale
        <textarea name="rationale" rows="2" placeholder="Connexion impossible et changement MFA."></textarea>
      </label>
      <button type="submit">Ajouter l'hypothèse</button>
    </form>
    <div>
      <strong>Hypothèses</strong>
      <div class="case-checklist">
        ${hypotheses
          .map(
            (item) => `
              <article class="checklist-item">
                <div>
                  <strong>${escapeHtml(item.statement)}</strong>
                  <p>${escapeHtml(item.rationale || "Sans justification.")}</p>
                </div>
                <div class="button-row">
                  <button data-hypothesis-status="open" data-case-id="${escapeHtml(investigationCase.case_id)}" data-hypothesis-id="${escapeHtml(item.hypothesis_id)}" type="button">Ouverte</button>
                  <button data-hypothesis-status="supported" data-case-id="${escapeHtml(investigationCase.case_id)}" data-hypothesis-id="${escapeHtml(item.hypothesis_id)}" type="button">Confirmée</button>
                  <button data-hypothesis-status="rejected" data-case-id="${escapeHtml(investigationCase.case_id)}" data-hypothesis-id="${escapeHtml(item.hypothesis_id)}" type="button">Rejetée</button>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    </div>
    <div>
      <strong>Notes</strong>
      ${notes.length ? list(notes.map((note) => note.body)) : "<p>Aucune note.</p>"}
    </div>
  `;
}

async function refreshInvestigationCases() {
  try {
    const cases = await request("/investigation-cases");
    if (!selectedInvestigationCaseId && cases.length) {
      selectedInvestigationCaseId = cases[0].case_id;
    }
    renderInvestigationCaseList(cases);
    if (selectedInvestigationCaseId) {
      renderInvestigationCaseDetail(
        await request(`/investigation-cases/${selectedInvestigationCaseId}`),
      );
    } else {
      renderInvestigationCaseDetail(null);
    }
  } catch (error) {
    investigationCaseList.className = "method-list empty";
    investigationCaseList.textContent = "Impossible de charger les dossiers.";
  }
  await refreshSOCQueue();
}

async function refreshPlaybooks() {
  try {
    renderPlaybooks(await request("/playbooks"));
  } catch (error) {
    playbookList.className = "method-list empty";
    playbookList.textContent = "Impossible de charger les playbooks.";
  }
}

function renderWatchlists(watchlists = []) {
  if (!watchlists.length) {
    watchlistList.className = "method-list empty";
    watchlistList.textContent = "Aucune watchlist chargée.";
    return;
  }

  watchlistList.className = "method-list";
  watchlistList.innerHTML = watchlists
    .map(
      (watchlist) => `
        <article class="method-card">
          <div>
            <strong>${escapeHtml(watchlist.title)}</strong>
            <p>${escapeHtml(watchlist.keywords)}</p>
          </div>
          <p>
            ${watchlist.exact_match ? "expression exacte" : "mots-clés"}
            · ${watchlist.kev_only ? "KEV uniquement" : "toutes les CVE"}
          </p>
          <footer>
            <button data-delete-watchlist="${escapeHtml(watchlist.watchlist_id)}" type="button">Supprimer</button>
          </footer>
        </article>
      `,
    )
    .join("");
}

async function refreshWatchlists() {
  try {
    renderWatchlists(await request("/watchlists"));
  } catch (error) {
    watchlistList.className = "method-list empty";
    watchlistList.textContent = "Impossible de charger les watchlists.";
  }
}

function renderAutomations(automations = []) {
  if (!automations.length) {
    automationList.className = "method-list empty";
    automationList.textContent = "Aucune automatisation chargée.";
    return;
  }

  automationList.className = "method-list";
  automationList.innerHTML = automations
    .map(
      (automation) => `
        <article class="method-card">
          <div>
            <strong>${escapeHtml(automation.name)}</strong>
            <p>${escapeHtml(automation.schedule_kind)} · ${escapeHtml(automation.schedule_time)} · ${escapeHtml(automation.timezone)}</p>
          </div>
          <p>Prochaine exécution : ${escapeHtml(automation.next_run_at || "non planifiée")}</p>
          <footer>
            <button data-run-automation="${escapeHtml(automation.automation_id)}" type="button">Exécuter</button>
            <button data-view-automation-runs="${escapeHtml(automation.automation_id)}" type="button">Historique</button>
            <button data-delete-automation="${escapeHtml(automation.automation_id)}" type="button">Supprimer</button>
          </footer>
        </article>
      `,
    )
    .join("");
}

function renderApprovals(approvals = []) {
  if (!approvals.length) {
    approvalList.className = "method-list empty";
    approvalList.textContent = "Aucune demande d'approbation en attente.";
    return;
  }

  approvalList.className = "method-list";
  approvalList.innerHTML = approvals
    .map(
      (approval) => `
        <article class="method-card">
          <div>
            <strong>${escapeHtml(approval.tool_name)}</strong>
            <p>${escapeHtml(formatApprovalSummary(approval))}</p>
          </div>
          <p>Raison : ${escapeHtml(approval.reason)}</p>
          <footer class="approval-actions">
            <button data-approve-tool="${escapeHtml(approval.approval_id)}" type="button">Approuver</button>
            <button data-reject-tool="${escapeHtml(approval.approval_id)}" type="button">Refuser</button>
          </footer>
        </article>
      `,
    )
    .join("");
}

function formatApprovalSummary(approval) {
  if (approval.tool_name === "create_watchlist") {
    return `Créer la watchlist « ${approval.arguments.title || "sans titre"} » pour « ${approval.arguments.keywords || ""} ».`;
  }
  return `Exécuter ${approval.tool_name}.`;
}

async function refreshApprovals() {
  try {
    renderApprovals(await request("/approvals?status=pending"));
  } catch (error) {
    approvalList.className = "method-list empty";
    approvalList.textContent = "Impossible de charger les demandes d'approbation.";
  }
}

async function refreshAutomations() {
  try {
    renderAutomations(await request("/automations"));
  } catch (error) {
    automationList.className = "method-list empty";
    automationList.textContent = "Impossible de charger les automatisations.";
  }
}

function renderInbox(items = []) {
  if (!items.length) {
    inboxList.className = "method-list empty";
    inboxList.textContent = "Aucun élément dans l'inbox.";
    return;
  }

  inboxList.className = "method-list";
  inboxList.innerHTML = items
    .map(
      (item) => `
        <article class="method-card">
          <div>
            <strong>${escapeHtml(item.title)}</strong>
            <p>${escapeHtml(item.created_at)}</p>
          </div>
          <p>${escapeHtml(item.body)}</p>
          ${
            item.payload
              ? item.payload.items
                ? `<p>${item.payload.items.length} watchlist(s) dans le livrable.</p>`
                : `<p>${item.payload.repositories?.length || 0} dépôt(s) · ${item.payload.drive_files?.length || 0} fichier(s) Drive · ${item.payload.jira_issues?.length || 0} ticket(s) Jira.</p>`
              : ""
          }
          <footer>
            ${
              item.read_at
                ? `<span class="subtle">Lu le ${escapeHtml(item.read_at)}</span>`
                : `<button data-mark-inbox-read="${escapeHtml(item.item_id)}" type="button">Marquer comme lu</button>`
            }
          </footer>
        </article>
      `,
    )
    .join("");
}

async function refreshInbox() {
  try {
    renderInbox(await request("/inbox"));
  } catch (error) {
    inboxList.className = "method-list empty";
    inboxList.textContent = "Impossible de charger l'inbox.";
  }
}

function renderConnectorStatuses(statuses = []) {
  if (!statuses.length) {
    connectorStatusList.className = "method-list empty";
    connectorStatusList.textContent = "Aucun statut chargé.";
    return;
  }

  connectorStatusList.className = "method-list";
  connectorStatusList.innerHTML = statuses
    .map(
      (status) => `
        <article class="method-card">
          <div>
            <strong>${escapeHtml(status.provider)}</strong>
            <p>${status.configured ? "configuré" : "non configuré"} · ${escapeHtml(status.mode)}</p>
          </div>
        </article>
      `,
    )
    .join("");
}

async function refreshConnectorStatuses() {
  try {
    renderConnectorStatuses(await request("/connectors/status"));
  } catch (error) {
    connectorStatusList.className = "method-list empty";
    connectorStatusList.textContent = "Impossible de charger les connecteurs.";
  }
}

function renderAutomationRuns(runs = []) {
  if (!runs.length) {
    automationRunList.className = "method-list empty";
    automationRunList.textContent = "Aucune exécution enregistrée.";
    return;
  }

  automationRunList.className = "method-list";
  automationRunList.innerHTML = runs
    .map(
      (run) => `
        <article class="method-card">
          <div>
            <strong>${escapeHtml(run.status)}</strong>
            <p>${escapeHtml(run.started_at)}</p>
          </div>
          ${
            run.output
              ? run.output.items
                ? `<p>${run.output.items.length} watchlist(s) traitée(s).</p>`
                : `<p>${run.output.repositories?.length || 0} dépôt(s) · ${run.output.drive_files?.length || 0} fichier(s) Drive · ${run.output.jira_issues?.length || 0} ticket(s) Jira.</p>`
              : run.error_message
                ? `<p>${escapeHtml(run.error_message)}</p>`
                : `<p>Aucun détail supplémentaire.</p>`
          }
        </article>
      `,
    )
    .join("");
}

function renderDailyBrief(brief) {
  if (!brief.items.length) {
    dailyBriefResult.className = "result empty";
    dailyBriefResult.textContent = "Aucune watchlist configurée.";
    return;
  }

  dailyBriefResult.className = "result";
  dailyBriefResult.innerHTML = `
    <div class="result-grid">
      <div class="metric"><span>Fenêtre</span>${escapeHtml(brief.window_start)} → ${escapeHtml(brief.window_end)}</div>
      <div class="metric"><span>Watchlists</span>${brief.items.length}</div>
    </div>
    ${brief.items
      .map(
        (item) => `
          <div>
            <strong>${escapeHtml(item.watchlist.title)}</strong>
            ${
              item.records.length
                ? `<ul>${item.records
                    .map(
                      (record) =>
                        `<li>${escapeHtml(record.cve_id)} · ${escapeHtml(record.cvss_severity || "n/a")} · ${escapeHtml(record.description)}</li>`,
                    )
                    .join("")}</ul>`
                : `<p class="subtle">Aucune CVE récente trouvée.</p>`
            }
          </div>
        `,
      )
      .join("")}
  `;
}

function renderKnowledgeDocuments(documents = []) {
  if (!documents.length) {
    knowledgeList.className = "document-list empty";
    knowledgeList.textContent = "Aucun document chargé.";
    return;
  }

  knowledgeList.className = "document-list";
  knowledgeList.innerHTML = documents
    .map(
      (document) => `
        <article class="document-card">
          <div>
            <strong>${escapeHtml(document.title)}</strong>
            <p>${escapeHtml(document.source || "source manuelle")}</p>
          </div>
          <button data-delete-document="${escapeHtml(document.document_id)}">Supprimer</button>
        </article>
      `,
    )
    .join("");
}

async function refreshKnowledgeDocuments() {
  try {
    const documents = await request("/knowledge/documents");
    renderKnowledgeDocuments(documents);
  } catch (error) {
    knowledgeList.className = "document-list empty";
    knowledgeList.textContent = "Impossible de charger les documents.";
  }
}

function renderAdminUsers(users = []) {
  if (!users.length) {
    adminUserList.className = "admin-user-list empty";
    adminUserList.textContent = "Aucun utilisateur chargé.";
    return;
  }

  adminUserList.className = "admin-user-list";
  adminUserList.innerHTML = users
    .map(
      (user) => `
        <article class="admin-user-card">
          <div>
            <strong>${escapeHtml(user.email)}</strong>
            <p>${escapeHtml(user.user_id)}</p>
          </div>
          <select data-role-select="${escapeHtml(user.user_id)}">
            <option value="admin" ${user.role === "admin" ? "selected" : ""}>admin</option>
            <option value="analyst" ${user.role === "analyst" ? "selected" : ""}>analyst</option>
          </select>
          <button data-role-save="${escapeHtml(user.user_id)}" type="button">Enregistrer</button>
        </article>
      `,
    )
    .join("");
}

async function refreshAdminUsers() {
  if (currentUser?.role !== "admin") return;
  try {
    const users = await request("/admin/users");
    renderAdminUsers(users);
  } catch (error) {
    adminUserList.className = "admin-user-list empty";
    adminUserList.textContent = "Impossible de charger les utilisateurs.";
  }
}

function renderAuditEvents(events = []) {
  if (!events.length) {
    auditEventList.className = "audit-event-list empty";
    auditEventList.textContent = "Aucun événement charg?.";
    return;
  }

  auditEventList.className = "audit-event-list";
  auditEventList.innerHTML = events
    .map(
      (event) => `
        <article class="audit-event-card">
          <strong>${escapeHtml(event.event_type)}</strong>
          <p>${escapeHtml(event.created_at)}</p>
          <p>${escapeHtml(event.actor_user_id || "système")}</p>
        </article>
      `,
    )
    .join("");
}

async function refreshAuditEvents() {
  if (currentUser?.role !== "admin") return;
  try {
    const params = new URLSearchParams({ limit: "10" });
    if (auditEventTypeInput.value.trim()) params.set("event_type", auditEventTypeInput.value.trim());
    const events = await request(`/admin/audit-events?${params.toString()}`);
    renderAuditEvents(events);
  } catch (error) {
    auditEventList.className = "audit-event-list empty";
    auditEventList.textContent = "Impossible de charger l'audit.";
  }
}

function renderSessions(sessions = []) {
  if (!sessions.length) {
    sessionList.className = "session-list empty";
    sessionList.textContent = "Aucune session active.";
    return;
  }

  sessionList.className = "session-list";
  sessionList.innerHTML = sessions
    .map(
      (session) => `
        <article class="session-card">
          <div>
            <strong class="${session.current ? "session-current" : ""}">
              ${session.current ? "Session courante" : "Session active"}
            </strong>
            <p>Créée le ${escapeHtml(session.created_at)}</p>
            <p>Expire le ${escapeHtml(session.expires_at)}</p>
          </div>
          ${
            session.current
              ? ""
              : `<button data-session-revoke="${escapeHtml(session.session_id)}" type="button">R?voquer</button>`
          }
        </article>
      `,
    )
    .join("");
}

async function refreshSessions() {
  if (!authToken) return;
  try {
    const sessions = await request("/auth/sessions");
    renderSessions(sessions);
  } catch (error) {
    sessionList.className = "session-list empty";
    sessionList.textContent = "Impossible de charger les sessions.";
  }
}

document.querySelector("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const sessionId = document.querySelector("#chat-session").value.trim() || "default";
  const message = document.querySelector("#chat-message").value.trim();
  if (!message) return;

  appendMessage("user", message);
  document.querySelector("#chat-message").value = "";

  try {
    const data = await request("/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    appendMessage("assistant", data.answer, data.citations);
  } catch (error) {
    appendMessage("assistant", "Je n'ai pas pu répondre pour le moment.");
  }
});

document.querySelector("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.querySelector("#login-email").value.trim();
  const password = document.querySelector("#login-password").value;
  const mfaCode = document.querySelector("#login-mfa-code").value.trim() || null;
  if (!email || !password) return;

  try {
    const data = await request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, mfa_code: mfaCode }),
    });
    authToken = data.token;
    sessionStorage.setItem("jarvis_auth_token", authToken);
    updateAuthUi(data.user);
    await refreshAllUserData();
  } catch (error) {
    authMessage.textContent = errorMsg(error) || "Connexion impossible.";
  }
});

document.querySelector("#register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.querySelector("#register-email").value.trim();
  const password = document.querySelector("#register-password").value;
  if (!email || !password) return;

  try {
    const data = await request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    authToken = data.token;
    sessionStorage.setItem("jarvis_auth_token", authToken);
    updateAuthUi(data.user);
    await refreshAllUserData();
  } catch (error) {
    authMessage.textContent = errorMsg(error) || "Création de compte impossible.";
  }
});

mfaEnrollForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await request("/auth/mfa/totp/enroll", {
      method: "POST",
      body: JSON.stringify({
        label: document.querySelector("#mfa-label").value.trim() || null,
      }),
    });
    pendingMfaFactorId = result.factor_id;
    mfaEnrollmentResult.className = "result";
    mfaEnrollmentResult.innerHTML = `
      <div>
        <strong>Secret TOTP</strong>
        <p>${escapeHtml(result.secret)}</p>
      </div>
      <div>
        <strong>URI d'enrôlement</strong>
        <p>${escapeHtml(result.otpauth_uri)}</p>
      </div>
    `;
  } catch (error) {
    mfaEnrollmentResult.className = "result empty";
    mfaEnrollmentResult.textContent = "Impossible de créer un facteur MFA.";
  }
});

mfaVerifyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!pendingMfaFactorId) {
    mfaEnrollmentResult.className = "result empty";
    mfaEnrollmentResult.textContent = "Crée d'abord un facteur TOTP.";
    return;
  }
  try {
    await request("/auth/mfa/totp/verify", {
      method: "POST",
      body: JSON.stringify({
        factor_id: pendingMfaFactorId,
        code: document.querySelector("#mfa-verify-code").value.trim(),
      }),
    });
    pendingMfaFactorId = null;
    mfaVerifyForm.reset();
    await refreshMfaStatus();
    mfaEnrollmentResult.className = "result";
    mfaEnrollmentResult.textContent = "Facteur MFA vérifié.";
  } catch (error) {
    mfaEnrollmentResult.className = "result empty";
    mfaEnrollmentResult.textContent = "Code MFA invalide ou facteur indisponible.";
  }
});

mfaRecoveryCodesButton.addEventListener("click", async () => {
  try {
    const result = await request("/auth/mfa/recovery-codes", { method: "POST" });
    await refreshMfaStatus();
    mfaRecoveryCodesResult.className = "result";
    mfaRecoveryCodesResult.innerHTML = `
      <div>
        <strong>Conserve ces codes maintenant</strong>
        <p>Ils ne seront plus affichés ensuite.</p>
      </div>
      ${list(result.codes)}
    `;
  } catch (error) {
    mfaRecoveryCodesResult.className = "result empty";
    mfaRecoveryCodesResult.textContent =
      "Impossible de générer des codes sans facteur MFA vérifié.";
  }
});

mfaFactorList.addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-disable-mfa-factor]");
  if (!form) return;
  event.preventDefault();

  const code = form.elements.code?.value.trim() || null;
  const allowDisableLastFactor = Boolean(form.elements.allow_disable_last_factor?.checked);

  try {
    await request(`/auth/mfa/factors/${form.dataset.disableMfaFactor}/disable`, {
      method: "POST",
      body: JSON.stringify({
        code,
        allow_disable_last_factor: allowDisableLastFactor,
      }),
    });
    await refreshMfaStatus();
    mfaEnrollmentResult.className = "result";
    mfaEnrollmentResult.textContent = "Facteur MFA désactivé.";
  } catch (error) {
    mfaEnrollmentResult.className = "result empty";
    mfaEnrollmentResult.textContent =
      "Impossible de désactiver ce facteur. Vérifie le code ou la confirmation demandée.";
  }
});

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    display_name: document.querySelector("#profile-display-name").value.trim() || null,
    job_title: document.querySelector("#profile-job-title").value.trim() || null,
    organization: document.querySelector("#profile-organization").value.trim() || null,
    timezone: document.querySelector("#profile-timezone").value.trim() || null,
    preferred_language: document.querySelector("#profile-language").value.trim() || null,
    response_style: document.querySelector("#profile-response-style").value,
    approval_preference: document.querySelector("#profile-approval-preference").value,
    environment_summary:
      document.querySelector("#profile-environment-summary").value.trim() || null,
    focus_areas: document.querySelector("#profile-focus-areas").value.trim() || null,
  };

  profileStatus.textContent = "Enregistrement du profil...";
  try {
    const profile = await request("/profile/me", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    renderProfile(profile);
    profileStatus.textContent = "Profil enregistré.";
  } catch (error) {
    profileStatus.textContent = "Impossible d'enregistrer le profil.";
  }
});

taskProfileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    name: document.querySelector("#task-profile-name").value.trim(),
    description: document.querySelector("#task-profile-description").value.trim() || null,
    output_format: document.querySelector("#task-profile-output-format").value.trim(),
    review_checklist: document.querySelector("#task-profile-review-checklist").value.trim() || null,
  };
  if (!payload.name || !payload.output_format) return;

  try {
    await request("/task-profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    taskProfileForm.reset();
    await refreshTaskProfiles();
  } catch (error) {
    taskProfileList.className = "method-list empty";
    taskProfileList.textContent = "Impossible d'ajouter le profil de tâche.";
  }
});

playbookForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    title: document.querySelector("#playbook-title").value.trim(),
    purpose: document.querySelector("#playbook-purpose").value.trim(),
    trigger_phrases: document.querySelector("#playbook-trigger-phrases").value.trim() || null,
    task_profile_id: playbookTaskProfileSelect.value || null,
    steps: document.querySelector("#playbook-steps").value.trim(),
    expected_outcome: document.querySelector("#playbook-expected-outcome").value.trim() || null,
  };
  if (!payload.title || !payload.purpose || !payload.steps) return;

  try {
    await request("/playbooks", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    playbookForm.reset();
    await refreshPlaybooks();
  } catch (error) {
    playbookList.className = "method-list empty";
    playbookList.textContent = "Impossible d'ajouter le playbook.";
  }
});

investigationProfileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    name: document.querySelector("#investigation-profile-name").value.trim(),
    description: document.querySelector("#investigation-profile-description").value.trim() || null,
    trigger_phrases: document.querySelector("#investigation-profile-triggers").value.trim() || null,
    default_goal: document.querySelector("#investigation-profile-goal").value.trim() || null,
    recommended_checks:
      document.querySelector("#investigation-profile-checks").value.trim() || null,
    include_recent_github: document.querySelector("#investigation-profile-github").checked,
    drive_query: document.querySelector("#investigation-profile-drive-query").value.trim() || null,
    jira_jql: document.querySelector("#investigation-profile-jira-jql").value.trim() || null,
  };
  if (!payload.name) return;

  try {
    await request("/investigation-profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    investigationProfileForm.reset();
    await refreshInvestigationProfiles();
  } catch (error) {
    investigationProfileList.className = "method-list empty";
    investigationProfileList.textContent = "Impossible d'ajouter ce profil.";
  }
});

prefillInvestigationProfileTemplateButton.addEventListener("click", async () => {
  const templateId = investigationProfileTemplateSelect.value;
  if (!templateId) return;
  try {
    const template = investigationProfileTemplates.find((item) => item.template_id === templateId);
    if (!template) return;
    document.querySelector("#investigation-profile-name").value = template.name;
    document.querySelector("#investigation-profile-description").value = template.description || "";
    document.querySelector("#investigation-profile-triggers").value = template.trigger_phrases || "";
    document.querySelector("#investigation-profile-goal").value = template.default_goal || "";
    document.querySelector("#investigation-profile-checks").value = template.recommended_checks || "";
    document.querySelector("#investigation-profile-drive-query").value = template.drive_query || "";
    document.querySelector("#investigation-profile-jira-jql").value = template.jira_jql || "";
    document.querySelector("#investigation-profile-github").checked = template.include_recent_github;
  } catch (error) {
    investigationProfileList.innerHTML = `<p class="error">Impossible de charger ce modèle.</p>`;
  }
});

watchlistForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    title: document.querySelector("#watchlist-title").value.trim(),
    keywords: document.querySelector("#watchlist-keywords").value.trim(),
    exact_match: document.querySelector("#watchlist-exact-match").checked,
    kev_only: document.querySelector("#watchlist-kev-only").checked,
  };
  if (!payload.title || !payload.keywords) return;

  try {
    await request("/watchlists", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    watchlistForm.reset();
    await refreshWatchlists();
  } catch (error) {
    watchlistList.className = "method-list empty";
    watchlistList.textContent = "Impossible d'ajouter la watchlist.";
  }
});

dailyBriefForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  dailyBriefResult.className = "result";
  dailyBriefResult.textContent = "Génération du brief...";
  try {
    const brief = await request("/briefs/daily", {
      method: "POST",
      body: JSON.stringify({
        days: Number(document.querySelector("#daily-brief-days").value || 1),
        per_watchlist_limit: Number(document.querySelector("#daily-brief-limit").value || 5),
      }),
    });
    renderDailyBrief(brief);
  } catch (error) {
    dailyBriefResult.innerHTML = `<p class="error">Impossible de générer le brief.</p>`;
  }
});

automationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    name: document.querySelector("#automation-name").value.trim(),
    automation_type: "daily_brief",
    schedule_kind: "daily",
    schedule_time: document.querySelector("#automation-time").value || "08:00",
    timezone: document.querySelector("#automation-timezone").value.trim() || "Europe/Brussels",
    payload: {
      days: Number(document.querySelector("#automation-days").value || 1),
      per_watchlist_limit: Number(document.querySelector("#automation-limit").value || 5),
    },
    enabled: true,
    requires_approval: document.querySelector("#automation-requires-approval").checked,
  };
  if (!payload.name) return;

  try {
    await request("/automations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    automationForm.reset();
    document.querySelector("#automation-time").value = "08:00";
    document.querySelector("#automation-timezone").value = "Europe/Brussels";
    document.querySelector("#automation-days").value = "1";
    document.querySelector("#automation-limit").value = "5";
    await refreshAutomations();
  } catch (error) {
    automationList.className = "method-list empty";
    automationList.textContent = "Impossible de créer l'automatisation.";
  }
});

runDueAutomationsButton.addEventListener("click", async () => {
  try {
    const result = await request("/automations/run-due", { method: "POST" });
    renderAutomationRuns(result.runs);
    await refreshAutomations();
    await refreshInbox();
  } catch (error) {
    automationRunList.className = "method-list empty";
    automationRunList.textContent = "Impossible d'exécuter les routines dues.";
  }
});

refreshInboxButton.addEventListener("click", async () => {
  await refreshInbox();
});

refreshApprovalsButton.addEventListener("click", async () => {
  await refreshApprovals();
});

auditFilterForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await refreshAuditEvents();
});

auditExportButton.addEventListener("click", async () => {
  const params = new URLSearchParams({ limit: "100" });
  if (auditEventTypeInput.value.trim()) params.set("event_type", auditEventTypeInput.value.trim());
  try {
    const response = await fetch(`/admin/audit-events/export.csv?${params.toString()}`, {
      headers: authHeaders(),
    });
    if (!response.ok) throw new Error(await response.text());
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "jarvis-audit-events.csv";
    link.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    authMessage.textContent = "Impossible d'exporter l'audit.";
  }
});

logoutButton.addEventListener("click", async () => {
  if (authToken) {
    try {
      await request("/auth/logout", { method: "POST" });
    } catch (error) {
      // Local cleanup still proceeds if the server is unavailable.
    }
  }
  authToken = null;
  sessionStorage.removeItem("jarvis_auth_token");
  updateAuthUi();
  await refreshProfile();
  await refreshKnowledgeDocuments();
  await refreshTaskProfiles();
  await refreshPlaybooks();
  await refreshWatchlists();
  await refreshAutomations();
  await refreshInbox();
  await refreshConnectorStatuses();
});

sessionList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-session-revoke]");
  if (!button) return;

  try {
    await request(`/auth/sessions/${button.dataset.sessionRevoke}`, { method: "DELETE" });
    await refreshSessions();
  } catch (error) {
    authMessage.textContent = errorMsg(error) || "Impossible de révoquer la session.";
  }
});

adminUserList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-role-save]");
  if (!button) return;
  const userId = button.dataset.roleSave;
  const select = adminUserList.querySelector(`[data-role-select="${CSS.escape(userId)}"]`);
  if (!select) return;

  try {
    await request(`/admin/users/${userId}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role: select.value }),
    });
    await refreshAdminUsers();
    await refreshAuditEvents();
  } catch (error) {
    authMessage.textContent = "Impossible de modifier le rôle.";
  }
});

document.querySelector("#cve-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const target = document.querySelector("#cve-result");
  const cveId = document.querySelector("#cve-id").value.trim();
  if (!cveId) return;

  target.className = "result";
  target.innerHTML = "Analyse en cours…";

  try {
    const data = await request("/workflows/cve-enrichment", {
      method: "POST",
      body: JSON.stringify({ cve_id: cveId }),
    });
    const { record, analysis } = data;
    target.innerHTML = `
      <div class="result-grid">
        <div class="metric"><span>CVE</span>${escapeHtml(record.cve_id)}</div>
        <div class="metric"><span>Urgence</span>${pill(analysis.urgency)}</div>
        <div class="metric"><span>CVSS</span>${escapeHtml(record.cvss_score ?? "n/a")}</div>
        <div class="metric"><span>Confiance</span>${pill(analysis.confidence)}</div>
      </div>
      <div>
        <strong>Résumé</strong>
        <p>${escapeHtml(analysis.executive_summary)}</p>
      </div>
      <div>
        <strong>Actions recommandées</strong>
        ${list(analysis.recommended_actions)}
      </div>
    `;
  } catch (error) {
    target.innerHTML = `<p class="error">Impossible d'enrichir cette CVE.</p>`;
  }
});

document.querySelector("#alert-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const target = document.querySelector("#alert-result");
  const payload = {
    title: document.querySelector("#alert-title").value.trim(),
    raw_alert: document.querySelector("#alert-raw").value.trim(),
    environment_context: document.querySelector("#alert-context").value.trim() || null,
  };
  if (!payload.title || !payload.raw_alert) return;

  target.className = "result";
  target.innerHTML = "Triage en cours…";

  try {
    const data = await request("/workflows/alert-triage", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const result = data.result;
    target.innerHTML = `
      <div class="result-grid">
        <div class="metric"><span>Classification</span>${pill(result.classification)}</div>
        <div class="metric"><span>Sévérité</span>${pill(result.severity)}</div>
        <div class="metric"><span>Décision</span>${escapeHtml(result.decision)}</div>
        <div class="metric"><span>Confiance</span>${pill(result.confidence)}</div>
      </div>
      <div>
        <strong>Pourquoi</strong>
        <p>${escapeHtml(result.rationale)}</p>
      </div>
      <div>
        <strong>Vérifications prioritaires</strong>
        ${list(result.priority_checks)}
      </div>
    `;
  } catch (error) {
    target.innerHTML = `<p class="error">Impossible de trier cette alerte.</p>`;
  }
});

document.querySelector("#investigation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const target = document.querySelector("#investigation-result");
  const payload = {
    title: document.querySelector("#investigation-title").value.trim(),
    raw_alert: document.querySelector("#investigation-raw").value.trim(),
    environment_context: document.querySelector("#investigation-context").value.trim() || null,
    goal: document.querySelector("#investigation-goal").value.trim() || null,
    investigation_profile_id: investigationProfileSelect.value || null,
    include_recent_github: document.querySelector("#investigation-include-github").checked,
    drive_query: document.querySelector("#investigation-drive-query").value.trim() || null,
    jira_jql: document.querySelector("#investigation-jira-jql").value.trim() || null,
  };
  if (!payload.title || !payload.raw_alert) return;

  target.className = "result";
  target.innerHTML = "Investigation en cours…";

  try {
    const data = await request("/workflows/alert-investigation", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const result = data.result;
    lastInvestigationCasePayload = {
      title: payload.title,
      raw_alert: payload.raw_alert,
      environment_context: payload.environment_context,
      goal: payload.goal,
      investigation_profile_id:
        data.applied_profile?.profile_id || payload.investigation_profile_id || null,
    };
    target.innerHTML = `
      <div class="result-grid">
        <div class="metric"><span>Décision</span>${escapeHtml(result.triage.decision)}</div>
        <div class="metric"><span>Confiance</span>${escapeHtml(result.confidence)}</div>
      </div>
      <div>
        <strong>Résumé</strong>
        <p>${escapeHtml(result.executive_summary)}</p>
      </div>
      ${
        data.applied_profile
          ? `
            <div>
              <strong>Profil appliqué</strong>
              <p>${escapeHtml(data.applied_profile.name)}</p>
            </div>
          `
          : ""
      }
      <div>
        <strong>Contexte utile</strong>
        ${list(result.context_findings)}
      </div>
      <div>
        <strong>Playbooks mobilisés</strong>
        ${list(result.matched_playbooks)}
      </div>
      <div>
        <strong>Vérifications prioritaires</strong>
        ${list(result.priority_checks)}
      </div>
      <div>
        <strong>Actions recommandées</strong>
        ${list(result.recommended_actions)}
      </div>
      <div>
        <strong>Contexte externe</strong>
        ${
          data.external_context
            ? `
              <p>${data.external_context.repositories.length} dépôt(s) · ${data.external_context.drive_files.length} fichier(s) Drive · ${data.external_context.jira_issues.length} ticket(s) Jira.</p>
              ${list(data.external_context.repositories.map((item) => item.full_name))}
              ${list(data.external_context.drive_files.map((item) => item.name))}
              ${list(data.external_context.jira_issues.map((item) => `${item.key} — ${item.summary}`))}
            `
            : "<p class=\"subtle\">Aucun contexte externe demandé.</p>"
        }
      </div>
      ${
        result.suggested_watchlist
          ? `
            <div>
              <strong>Action proposée</strong>
              <p>Watchlist « ${escapeHtml(result.suggested_watchlist.title)} » pour « ${escapeHtml(result.suggested_watchlist.keywords)} ».</p>
              ${
                data.pending_approval_id
                  ? "<p class=\"subtle\">Une approbation a été ajoutée à la file de contrôle humain.</p>"
                  : ""
              }
            </div>
          `
          : ""
      }
      <button id="create-case-from-investigation" type="button">Créer un dossier d'investigation</button>
    `;
    await refreshApprovals();
    await refreshInbox();
  } catch (error) {
    target.innerHTML = `<p class="error">Impossible de lancer cette investigation.</p>`;
  }
});

document.querySelector("#investigation-result").addEventListener("click", async (event) => {
  const button = event.target.closest("#create-case-from-investigation");
  if (!button || !lastInvestigationCasePayload) return;
  try {
    const detail = await request("/investigation-cases", {
      method: "POST",
      body: JSON.stringify(lastInvestigationCasePayload),
    });
    selectedInvestigationCaseId = detail.case.case_id;
    await refreshInvestigationCases();
  } catch (error) {
    investigationCaseDetail.innerHTML = `<p class="error">Impossible de créer le dossier.</p>`;
  }
});

document.querySelector("#incident-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const target = document.querySelector("#incident-result");
  const payload = {
    incident_summary: document.querySelector("#incident-summary").value.trim(),
    timeline: document.querySelector("#incident-timeline").value.trim() || null,
    impact: document.querySelector("#incident-impact").value.trim() || null,
  };
  if (!payload.incident_summary) return;

  target.className = "result";
  target.innerHTML = "Génération en cours…";

  try {
    const data = await request("/workflows/incident-report", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const result = data.result;
    target.innerHTML = `
      <div class="result-grid">
        <div class="metric"><span>Confiance</span>${pill(result.confidence)}</div>
        <div class="metric"><span>Éléments de timeline</span>${result.timeline.length}</div>
      </div>
      <div>
        <strong>Résumé exécutif</strong>
        <p>${escapeHtml(result.executive_summary)}</p>
      </div>
      <div>
        <strong>Actions recommandées</strong>
        ${list(result.recommended_actions)}
      </div>
    `;
  } catch (error) {
    target.innerHTML = `<p class="error">Impossible de générer le brouillon.</p>`;
  }
});

document.querySelector("#knowledge-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const target = document.querySelector("#knowledge-result");
  const payload = {
    title: document.querySelector("#knowledge-title").value.trim(),
    source: document.querySelector("#knowledge-source").value.trim() || null,
    content: document.querySelector("#knowledge-content").value.trim(),
  };
  if (!payload.title || !payload.content) return;

  target.className = "result";
  target.innerHTML = "Ajout en cours…";

  try {
    const documentRecord = await request("/knowledge/documents", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    target.innerHTML = `
      <div class="result-grid">
        <div class="metric"><span>Document</span>${escapeHtml(documentRecord.title)}</div>
        <div class="metric"><span>Source</span>${escapeHtml(documentRecord.source || "manuelle")}</div>
      </div>
      <p>Le document a été ajouté à la base de connaissances.</p>
    `;
    document.querySelector("#knowledge-form").reset();
    await refreshKnowledgeDocuments();
  } catch (error) {
    target.innerHTML = `<p class="error">Impossible d'ajouter ce document.</p>`;
  }
});

document.querySelector("#knowledge-file-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const target = document.querySelector("#knowledge-result");
  const fileInput = document.querySelector("#knowledge-file");
  const files = [...(fileInput.files || [])];
  if (!files.length) return;

  target.className = "result";
  target.innerHTML = "Import en cours…";

  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  try {
    const response = await fetch("/knowledge/files/batch", {
      method: "POST",
      body: formData,
      headers: authHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const documentRecords = await response.json();
    target.innerHTML = `
      <div class="result-grid">
        <div class="metric"><span>Documents</span>${documentRecords.length}</div>
        <div class="metric"><span>Formats</span>${escapeHtml(
          [...new Set(documentRecords.map((document) => document.source?.split(".").pop() || "fichier"))].join(", "),
        )}</div>
      </div>
      <p>${documentRecords.length} document(s) ont été ingérés dans la base de connaissances.</p>
    `;
    document.querySelector("#knowledge-file-form").reset();
    await refreshKnowledgeDocuments();
  } catch (error) {
    target.innerHTML = `<p class="error">Impossible d'importer ce fichier.</p>`;
  }
});

knowledgeList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-document]");
  if (!button) return;

  try {
    await request(`/knowledge/documents/${button.dataset.deleteDocument}`, { method: "DELETE" });
    await refreshKnowledgeDocuments();
  } catch (error) {
    knowledgeList.innerHTML = `<p class="error">Impossible de supprimer ce document.</p>`;
  }
});

taskProfileList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-task-profile]");
  if (!button) return;

  try {
    await request(`/task-profiles/${button.dataset.deleteTaskProfile}`, { method: "DELETE" });
    await refreshTaskProfiles();
    await refreshPlaybooks();
  } catch (error) {
    taskProfileList.innerHTML = `<p class="error">Impossible de supprimer ce profil.</p>`;
  }
});

playbookList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-playbook]");
  if (!button) return;

  try {
    await request(`/playbooks/${button.dataset.deletePlaybook}`, { method: "DELETE" });
    await refreshPlaybooks();
  } catch (error) {
    playbookList.innerHTML = `<p class="error">Impossible de supprimer ce playbook.</p>`;
  }
});

investigationProfileList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-investigation-profile]");
  if (!button) return;

  try {
    await request(`/investigation-profiles/${button.dataset.deleteInvestigationProfile}`, {
      method: "DELETE",
    });
    await refreshInvestigationProfiles();
  } catch (error) {
    investigationProfileList.innerHTML = `<p class="error">Impossible de supprimer ce profil.</p>`;
  }
});

investigationCaseList.addEventListener("click", async (event) => {
  const openButton = event.target.closest("[data-open-investigation-case]");
  const deleteButton = event.target.closest("[data-delete-investigation-case]");
  if (openButton) {
    selectedInvestigationCaseId = openButton.dataset.openInvestigationCase;
    await refreshInvestigationCases();
  }
  if (deleteButton) {
    try {
      await request(`/investigation-cases/${deleteButton.dataset.deleteInvestigationCase}`, {
        method: "DELETE",
      });
      if (selectedInvestigationCaseId === deleteButton.dataset.deleteInvestigationCase) {
        selectedInvestigationCaseId = null;
      }
      await refreshInvestigationCases();
    } catch (error) {
      investigationCaseList.innerHTML = `<p class="error">Impossible de supprimer ce dossier.</p>`;
    }
  }
});

socQueueList.addEventListener("click", async (event) => {
  const openButton = event.target.closest("[data-open-investigation-case]");
  if (!openButton) return;
  selectedInvestigationCaseId = openButton.dataset.openInvestigationCase;
  await refreshInvestigationCases();
});

refreshSocQueueButton.addEventListener("click", refreshSOCQueue);
refreshShiftBriefButton.addEventListener("click", refreshShiftBrief);
refreshSlaWatchButton.addEventListener("click", refreshSLAWatch);

investigationCaseDetail.addEventListener("change", async (event) => {
  const select = event.target.closest("[data-investigation-case-status]");
  if (!select) return;
  try {
    await request(`/investigation-cases/${select.dataset.investigationCaseStatus}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: select.value }),
    });
    await refreshInvestigationCases();
  } catch (error) {
    investigationCaseDetail.innerHTML = `<p class="error">Impossible de mettre à jour le statut.</p>`;
  }
});

investigationCaseDetail.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-checklist-status]");
  const hypothesisButton = event.target.closest("[data-hypothesis-status]");
  const summaryButton = event.target.closest("[data-investigation-summary]");
  const reportButton = event.target.closest("[data-investigation-report]");
  const enrichmentPlanButton = event.target.closest("[data-investigation-enrichment-plan]");
  const incidentViewButton = event.target.closest("[data-investigation-incident-view]");
  const closureAssistantButton = event.target.closest("[data-investigation-closure-assistant]");
  const prefillEnrichmentButton = event.target.closest("[data-prefill-enrichment-recommendation]");
  const sentinelTemplateButton = event.target.closest("[data-render-sentinel-template]");
  if (prefillEnrichmentButton) {
    const caseId = prefillEnrichmentButton.dataset.prefillEnrichmentCase;
    const recommendationId = prefillEnrichmentButton.dataset.prefillEnrichmentRecommendation;
    const plan = latestEnrichmentPlans[caseId];
    const recommendation = plan?.recommendations.find(
      (item) => item.recommendation_id === recommendationId,
    );
    if (!recommendation) return;
    try {
      await prefillInvestigationRecommendation(caseId, recommendation);
    } catch (error) {
      setEnrichmentPlanStatus(caseId, "Impossible de préremplir ce formulaire.");
    }
    return;
  }
  if (sentinelTemplateButton) {
    const form = sentinelTemplateButton.closest("[data-investigation-sentinel-form]");
    const templateId = form.querySelector('[name="template_id"]').value;
    if (!templateId) return;
    try {
      const rawParameters = form.querySelector('[name="template_parameters"]').value.trim();
      const parameters = rawParameters ? JSON.parse(rawParameters) : {};
      const data = await request(`/sentinel-query-templates/${templateId}/render`, {
        method: "POST",
        body: JSON.stringify({ parameters }),
      });
      form.querySelector('[name="query"]').value = data.query;
      form.querySelector('[name="timespan"]').value = data.timespan || "";
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible de préremplir la requête KQL. Vérifiez les paramètres JSON.</p>`;
    }
    return;
  }
  if (button) {
    try {
      const detail = await request(
        `/investigation-cases/${button.dataset.caseId}/checklist/${button.dataset.itemId}`,
        {
          method: "PATCH",
          body: JSON.stringify({ status: button.dataset.checklistStatus, notes: null }),
        },
      );
      renderInvestigationCaseDetail(detail);
      await refreshInvestigationCases();
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible de mettre à jour la checklist.</p>`;
    }
  }
  if (hypothesisButton) {
    try {
      const detail = await request(
        `/investigation-cases/${hypothesisButton.dataset.caseId}/hypotheses/${hypothesisButton.dataset.hypothesisId}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            status: hypothesisButton.dataset.hypothesisStatus,
            rationale: null,
          }),
        },
      );
      renderInvestigationCaseDetail(detail);
      await refreshInvestigationCases();
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible de mettre à jour l'hypothèse.</p>`;
    }
  }
  if (summaryButton) {
    try {
      const data = await request(
        `/investigation-cases/${summaryButton.dataset.investigationSummary}/summary`,
        { method: "POST" },
      );
      const target = investigationCaseDetail.querySelector(
        `[data-investigation-summary-result="${summaryButton.dataset.investigationSummary}"]`,
      );
      target.innerHTML = `
        <strong>Synthèse d'avancement</strong>
        <p>${escapeHtml(data.result.executive_summary)}</p>
        <div><strong>Faits établis</strong>${list(data.result.established_facts)}</div>
        <div><strong>Hypothèses soutenues</strong>${list(data.result.supported_hypotheses)}</div>
        <div><strong>Hypothèses rejetées</strong>${list(data.result.rejected_hypotheses)}</div>
        <div><strong>Prochaines actions</strong>${list(data.result.next_actions)}</div>
        <div><strong>Incertitudes</strong>${list(data.result.uncertainties)}</div>
      `;
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible de générer la synthèse.</p>`;
    }
  }
  if (reportButton) {
    try {
      const data = await request(
        `/investigation-cases/${reportButton.dataset.investigationReport}/report`,
        { method: "POST" },
      );
      const target = investigationCaseDetail.querySelector(
        `[data-investigation-report-result="${reportButton.dataset.investigationReport}"]`,
      );
      target.innerHTML = `
        <strong>Rapport final</strong>
        <p>${escapeHtml(data.result.executive_summary)}</p>
        <div><strong>Chronologie</strong>${list(data.result.timeline)}</div>
        <div><strong>Périmètre et impact</strong><p>${escapeHtml(data.result.scope_and_impact)}</p></div>
        <div><strong>Cause probable</strong><p>${escapeHtml(data.result.probable_cause)}</p></div>
        <div><strong>Actions réalisées</strong>${list(data.result.actions_taken)}</div>
        <div><strong>Actions recommandées</strong>${list(data.result.recommended_actions)}</div>
        <div><strong>Questions ouvertes</strong>${list(data.result.open_questions)}</div>
      `;
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible de générer le rapport.</p>`;
    }
  }
  if (enrichmentPlanButton) {
    try {
      const data = await request(
        `/investigation-cases/${enrichmentPlanButton.dataset.investigationEnrichmentPlan}/enrichment-plan`,
        { method: "POST" },
      );
      const target = investigationCaseDetail.querySelector(
        `[data-investigation-enrichment-plan-result="${enrichmentPlanButton.dataset.investigationEnrichmentPlan}"]`,
      );
      target.innerHTML = renderEnrichmentPlan(data);
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible de proposer un plan d'enrichissement.</p>`;
    }
  }
  if (incidentViewButton) {
    try {
      const data = await request(
        `/investigation-cases/${incidentViewButton.dataset.investigationIncidentView}/incident-view`,
        { method: "POST" },
      );
      const target = investigationCaseDetail.querySelector(
        `[data-investigation-incident-view-result="${incidentViewButton.dataset.investigationIncidentView}"]`,
      );
      target.innerHTML = renderIncidentView(data);
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible d'afficher la vue incident.</p>`;
    }
  }
  if (closureAssistantButton) {
    try {
      const data = await request(
        `/investigation-cases/${closureAssistantButton.dataset.investigationClosureAssistant}/closure-assistant`,
        { method: "POST" },
      );
      const target = investigationCaseDetail.querySelector(
        `[data-investigation-closure-assistant-result="${closureAssistantButton.dataset.investigationClosureAssistant}"]`,
      );
      target.innerHTML = renderClosureAssistant(data);
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible d'évaluer la clôture du dossier.</p>`;
    }
  }
});

investigationCaseDetail.addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-investigation-note-form]");
  if (!form) return;
  event.preventDefault();
  const textarea = form.querySelector("textarea");
  const body = textarea.value.trim();
  if (!body) return;
  try {
    const detail = await request(`/investigation-cases/${form.dataset.investigationNoteForm}/notes`, {
      method: "POST",
      body: JSON.stringify({ body }),
    });
    renderInvestigationCaseDetail(detail);
    textarea.value = "";
    await refreshInvestigationCases();
  } catch (error) {
    investigationCaseDetail.innerHTML = `<p class="error">Impossible d'ajouter la note.</p>`;
  }
});

investigationCaseDetail.addEventListener("submit", async (event) => {
  const eventForm = event.target.closest("[data-investigation-event-form]");
  const evidenceForm = event.target.closest("[data-investigation-evidence-form]");
  const hypothesisForm = event.target.closest("[data-investigation-hypothesis-form]");
  const entraForm = event.target.closest("[data-investigation-entra-form]");
  const defenderForm = event.target.closest("[data-investigation-defender-form]");
  const sentinelForm = event.target.closest("[data-investigation-sentinel-form]");
  if (sentinelForm) {
    event.preventDefault();
    const query = sentinelForm.querySelector('[name="query"]').value.trim();
    const timespan = sentinelForm.querySelector('[name="timespan"]').value.trim() || null;
    if (!query) return;
    try {
      const data = await request(
        `/investigation-cases/${sentinelForm.dataset.investigationSentinelForm}/enrich/sentinel`,
        {
          method: "POST",
          body: JSON.stringify({ query, timespan, max_events: 5 }),
        },
      );
      renderInvestigationCaseDetail(data.detail);
      const target = investigationCaseDetail.querySelector(
        `[data-investigation-sentinel-result="${sentinelForm.dataset.investigationSentinelForm}"]`,
      );
      if (target) {
        target.innerHTML = `
          <strong>Enrichissement Sentinel termin?</strong>
          <p>${data.result.rows_reviewed} ligne(s), ${data.result.added_events} ?v?nement(s) et ${data.result.added_evidence} preuve(s) ajout?s.</p>
        `;
      }
      await refreshInvestigationCases();
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible d'enrichir le dossier avec Sentinel.</p>`;
    }
    return;
  }
  if (defenderForm) {
    event.preventDefault();
    const query = defenderForm.querySelector('[name="query"]').value.trim() || null;
    const severity = defenderForm.querySelector('[name="severity"]').value.trim() || null;
    try {
      const data = await request(
        `/investigation-cases/${defenderForm.dataset.investigationDefenderForm}/enrich/defender`,
        {
          method: "POST",
          body: JSON.stringify({ query, severity, incident_limit: 5, alert_limit: 10 }),
        },
      );
      renderInvestigationCaseDetail(data.detail);
      const target = investigationCaseDetail.querySelector(
        `[data-investigation-defender-result="${defenderForm.dataset.investigationDefenderForm}"]`,
      );
      if (target) {
        target.innerHTML = `
          <strong>Enrichissement Defender termin?</strong>
          <p>${data.result.incidents_reviewed} incident(s), ${data.result.alerts_reviewed} alerte(s), ${data.result.added_events} ?v?nement(s) et ${data.result.added_evidence} preuve(s) ajout?s.</p>
        `;
      }
      await refreshInvestigationCases();
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible d'enrichir le dossier avec Defender.</p>`;
    }
    return;
  }
  if (entraForm) {
    event.preventDefault();
    const userPrincipalName = entraForm.querySelector('[name="user_principal_name"]').value.trim();
    const signInLimit = Number(entraForm.querySelector('[name="sign_in_limit"]').value || 5);
    if (!userPrincipalName) return;
    try {
      const data = await request(
        `/investigation-cases/${entraForm.dataset.investigationEntraForm}/enrich/entra-id`,
        {
          method: "POST",
          body: JSON.stringify({
            user_principal_name: userPrincipalName,
            sign_in_limit: signInLimit,
          }),
        },
      );
      renderInvestigationCaseDetail(data.detail);
      const target = investigationCaseDetail.querySelector(
        `[data-investigation-entra-result="${entraForm.dataset.investigationEntraForm}"]`,
      );
      if (target) {
        target.innerHTML = `
          <strong>Enrichissement Entra ID termin?</strong>
          <p>${data.result.sign_ins_reviewed} connexion(s) examin?e(s), ${data.result.matched_risky_users} utilisateur(s) ? risque correspondant(s), ${data.result.added_events} ?v?nement(s) et ${data.result.added_evidence} preuve(s) ajout?s.</p>
        `;
      }
      await refreshInvestigationCases();
    } catch (error) {
      investigationCaseDetail.innerHTML = `<p class="error">Impossible d'enrichir le dossier avec Entra ID.</p>`;
    }
    return;
  }
  if (eventForm) {
    event.preventDefault();
    const occurredAt = eventForm.querySelector('[name="occurred_at"]').value.trim();
    const title = eventForm.querySelector('[name="title"]').value.trim();
    const description = eventForm.querySelector('[name="description"]').value.trim() || null;
    if (!occurredAt || !title) return;
    const detail = await request(`/investigation-cases/${eventForm.dataset.investigationEventForm}/events`, {
      method: "POST",
      body: JSON.stringify({ occurred_at: occurredAt, title, description }),
    });
    renderInvestigationCaseDetail(detail);
    await refreshInvestigationCases();
  }
  if (evidenceForm) {
    event.preventDefault();
    const title = evidenceForm.querySelector('[name="title"]').value.trim();
    const source = evidenceForm.querySelector('[name="source"]').value.trim() || null;
    const description = evidenceForm.querySelector('[name="description"]').value.trim() || null;
    if (!title) return;
    const detail = await request(`/investigation-cases/${evidenceForm.dataset.investigationEvidenceForm}/evidence`, {
      method: "POST",
      body: JSON.stringify({ title, source, description }),
    });
    renderInvestigationCaseDetail(detail);
    await refreshInvestigationCases();
  }
  if (hypothesisForm) {
    event.preventDefault();
    const statement = hypothesisForm.querySelector('[name="statement"]').value.trim();
    const rationale = hypothesisForm.querySelector('[name="rationale"]').value.trim() || null;
    if (!statement) return;
    const detail = await request(`/investigation-cases/${hypothesisForm.dataset.investigationHypothesisForm}/hypotheses`, {
      method: "POST",
      body: JSON.stringify({ statement, rationale }),
    });
    renderInvestigationCaseDetail(detail);
    await refreshInvestigationCases();
  }
});

watchlistList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-watchlist]");
  if (!button) return;

  try {
    await request(`/watchlists/${button.dataset.deleteWatchlist}`, { method: "DELETE" });
    await refreshWatchlists();
  } catch (error) {
    watchlistList.innerHTML = `<p class="error">Impossible de supprimer cette watchlist.</p>`;
  }
});

automationList.addEventListener("click", async (event) => {
  const runButton = event.target.closest("[data-run-automation]");
  const historyButton = event.target.closest("[data-view-automation-runs]");
  const deleteButton = event.target.closest("[data-delete-automation]");

  if (runButton) {
    try {
      const run = await request(`/automations/${runButton.dataset.runAutomation}/run`, {
        method: "POST",
      });
      renderAutomationRuns([run]);
      await refreshAutomations();
      await refreshInbox();
    } catch (error) {
      automationRunList.className = "method-list empty";
      automationRunList.textContent = "Impossible d'exécuter cette automatisation.";
    }
    return;
  }

  if (historyButton) {
    try {
      renderAutomationRuns(await request(`/automations/${historyButton.dataset.viewAutomationRuns}/runs`));
    } catch (error) {
      automationRunList.className = "method-list empty";
      automationRunList.textContent = "Impossible de charger l'historique.";
    }
    return;
  }

  if (deleteButton) {
    try {
      await request(`/automations/${deleteButton.dataset.deleteAutomation}`, { method: "DELETE" });
      await refreshAutomations();
    } catch (error) {
      automationList.innerHTML = `<p class="error">Impossible de supprimer cette automatisation.</p>`;
    }
  }
});

inboxList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-mark-inbox-read]");
  if (!button) return;

  try {
    await request(`/inbox/${button.dataset.markInboxRead}/read`, { method: "PATCH" });
    await refreshInbox();
  } catch (error) {
    inboxList.innerHTML = `<p class="error">Impossible de marquer cet élément comme lu.</p>`;
  }
});

approvalList.addEventListener("click", async (event) => {
  const approveButton = event.target.closest("[data-approve-tool]");
  const rejectButton = event.target.closest("[data-reject-tool]");
  if (!approveButton && !rejectButton) return;

  try {
    if (approveButton) {
      await request(`/approvals/${approveButton.dataset.approveTool}/approve`, { method: "POST" });
      await refreshWatchlists();
    } else {
      await request(`/approvals/${rejectButton.dataset.rejectTool}/reject`, { method: "POST" });
    }
    await refreshApprovals();
    await refreshInbox();
  } catch (error) {
    approvalList.innerHTML = `<p class="error">Impossible de traiter cette demande.</p>`;
  }
});

function speechRecognitionConstructor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition;
}

function speakWithBrowser(text) {
  return new Promise((resolve, reject) => {
    if (!("speechSynthesis" in window)) {
      reject(new Error("Browser speech synthesis unavailable."));
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "fr-BE";
    utterance.rate = 1;
    utterance.onend = resolve;
    utterance.onerror = reject;
    window.speechSynthesis.speak(utterance);
  });
}

async function sendBrowserVoiceMessage(transcript, speakAnswer = false) {
  const message = transcript.trim();
  if (!message) return;

  browserVoiceBusy = true;
  appendMessage("user", message);
  voiceStatus.textContent = "Jarvis réfléchit…";

  try {
    const sessionId = document.querySelector("#chat-session").value.trim() || "voice";
    const data = await request("/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    appendMessage("assistant", data.answer, data.citations);
    if (speakAnswer) {
      voiceStatus.textContent = "Jarvis répond…";
      await speakWithBrowser(data.answer);
    }
    voiceStatus.textContent = browserRealtimeActive
      ? "Mode vocal gratuit actif. Tu peux parler."
      : "Réponse vocale prête.";
  } catch (error) {
    voiceStatus.textContent = "Impossible de traiter la demande vocale.";
  } finally {
    browserVoiceBusy = false;
    if (browserRealtimeActive) startBrowserRealtimeListening();
  }
}

function createBrowserRecognition({ onTranscript, onEnd }) {
  const Recognition = speechRecognitionConstructor();
  if (!Recognition) throw new Error("Speech recognition unavailable.");

  const recognition = new Recognition();
  recognition.lang = "fr-BE";
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onresult = (event) => {
    const result = event.results[event.results.length - 1];
    if (result.isFinal) onTranscript(result[0].transcript);
  };
  recognition.onerror = (event) => {
    if (event.error !== "aborted" && event.error !== "no-speech") {
      voiceStatus.textContent = `Erreur micro : ${event.error}.`;
    }
  };
  recognition.onend = onEnd;
  return recognition;
}

voiceRecordButton.addEventListener("click", () => {
  try {
    const recognition = createBrowserRecognition({
      onTranscript: (transcript) => sendBrowserVoiceMessage(transcript),
      onEnd: () => {
        voiceRecordButton.disabled = false;
        if (!browserVoiceBusy) voiceStatus.textContent = "Écoute terminée.";
      },
    });
    voiceRecordButton.disabled = true;
    voiceStatus.textContent = "Écoute gratuite en cours…";
    recognition.start();
  } catch (error) {
    voiceStatus.textContent = "Reconnaissance vocale indisponible dans ce navigateur.";
  }
});

voiceSpeakLastButton.addEventListener("click", async () => {
  if (!lastAssistantAnswer) return;

  voiceStatus.textContent = "Lecture avec la voix du système…";
  try {
    await speakWithBrowser(lastAssistantAnswer);
    voiceStatus.textContent = "Lecture terminée.";
  } catch (error) {
    voiceStatus.textContent = "Synthèse vocale indisponible dans ce navigateur.";
  }
});

function startBrowserRealtimeListening() {
  if (!browserRealtimeActive || browserVoiceBusy) return;

  try {
    browserSpeechRecognition = createBrowserRecognition({
      onTranscript: (transcript) => {
        browserSpeechRecognition?.abort();
        sendBrowserVoiceMessage(transcript, true);
      },
      onEnd: () => {
        browserSpeechRecognition = undefined;
        if (browserRealtimeActive && !browserVoiceBusy) {
          window.setTimeout(startBrowserRealtimeListening, 250);
        }
      },
    });
    browserSpeechRecognition.start();
    voiceStatus.textContent = "Mode vocal gratuit actif. Tu peux parler.";
  } catch (error) {
    browserRealtimeActive = false;
    realtimeConnectButton.disabled = false;
    realtimeDisconnectButton.disabled = true;
    voiceStatus.textContent = "Mode vocal gratuit indisponible dans ce navigateur.";
  }
}

realtimeConnectButton.addEventListener("click", () => {
  browserRealtimeActive = true;
  realtimeConnectButton.disabled = true;
  realtimeDisconnectButton.disabled = false;
  startBrowserRealtimeListening();
});

realtimeDisconnectButton.addEventListener("click", async () => {
  await stopRealtimeSession();
});

async function stopRealtimeSession() {
  browserRealtimeActive = false;
  browserSpeechRecognition?.abort();
  browserSpeechRecognition = undefined;
  window.speechSynthesis?.cancel();
  if (realtimeCallId) {
    try {
      await request(`/realtime/sideband/${realtimeCallId}`, { method: "DELETE" });
    } catch (error) {
      // Best effort cleanup only.
    }
  }
  realtimeDataChannel?.close();
  realtimePeerConnection?.close();
  realtimeLocalStream?.getTracks().forEach((track) => track.stop());
  realtimeDataChannel = undefined;
  realtimePeerConnection = undefined;
  realtimeLocalStream = undefined;
  realtimeCallId = undefined;
  realtimeConnectButton.disabled = false;
  realtimeDisconnectButton.disabled = true;
  voiceStatus.textContent = "Mode vocal arrêté.";
}

async function refreshAllUserData() {
  await refreshProfile();
  await refreshMfaStatus();
  await refreshKnowledgeDocuments();
  await refreshTaskProfiles();
  await refreshPlaybooks();
  await refreshInvestigationProfiles();
  await refreshInvestigationProfileTemplates();
  await refreshSentinelQueryTemplates();
  await refreshInvestigationCases();
  await refreshWatchlists();
  await refreshAutomations();
  await refreshInbox();
  await refreshApprovals();
  await refreshConnectorStatuses();
}

async function initializeApp() {
  await hydrateStatus();
  await hydrateCurrentUser();
  await refreshAllUserData();
  await refreshShiftBrief();
  await refreshSLAWatch();
}

initializeApp();

