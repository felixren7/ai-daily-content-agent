"use strict";

const state = {
  data: null,
  selectedId: null,
  token: sessionStorage.getItem("dashboardToken") || "",
  language: localStorage.getItem("dashboardLanguage") === "zh" ? "zh" : "en",
  busy: false,
  translationInFlight: false,
  pollTimer: null,
  followRun: false,
  runBaselineId: null,
};

const $ = (id) => document.getElementById(id);
const messages = {
  en: {
    skip: "Skip to content", operations: "Operations", sources: "Sources", topics: "Topics",
    history: "History", settings: "Settings", agentOnline: "Agent online", mode: "Mode",
    destination: "Destination", safety: "Safety", todaysRun: "Today’s run", runNow: "Run now",
    articlesFetched: "Articles fetched", duplicatesRemoved: "Duplicates removed",
    topicsRanked: "Topics ranked", waitingReview: "Waiting review",
    pipelineProgress: "Pipeline progress", selectedPost: "Selected post", noPosts: "No posts need review",
    runToGenerate: "Run the pipeline to generate a new source-grounded draft.",
    generatedCopy: "Generated copy", copy: "Copy", verifiedFacts: "Verified facts",
    sourceEvidence: "Source evidence", source: "Source", published: "Published", evidence: "Evidence",
    recentRuns: "Recent runs", started: "Started", result: "Result", fetched: "Fetched", post: "Post",
    humanCheckpoint: "Human checkpoint", reviewApprove: "Review & approve", facts: "Facts",
    quality: "Quality", scheduled: "Scheduled", publishVersion: "Publish version",
    approveQueue: "Approve & queue", publishNow: "Publish now", schedulePublish: "Schedule publish",
    regenerate: "Regenerate", requestRevision: "Request revision", humanFeedback: "Human feedback",
    revisionDescription: "Describe the factual, structural, or tone change the next draft needs.",
    revisionNote: "Revision note", cancel: "Cancel", sendRequest: "Send request",
    regenerateDraft: "Regenerate draft",
    regenerateDescription: "Explain exactly what should change. The new draft must stay within verified facts.",
    regenerateNow: "Regenerate now", publication: "Publication",
    scheduleDescription: "Choose a local date, time, and the exact language version to publish.",
    publishTime: "Publish time", originalVersion: "Original", chineseVersion: "Chinese",
    confirmSchedule: "Confirm schedule", saveSession: "Save for session", autoRefresh: "Auto refresh",
    dashboardSecurity: "Dashboard security", operatorSettings: "Operator settings",
    adminToken: "Admin token", tokenStorage: "The token is kept in this browser session only and is never displayed.",
  },
  zh: {
    skip: "跳到主要内容", operations: "运行中心", sources: "信息来源", topics: "选题内容",
    history: "运行历史", settings: "设置", agentOnline: "Agent 在线", mode: "模式",
    destination: "发布平台", safety: "安全模式", todaysRun: "今日运行", runNow: "立即运行",
    articlesFetched: "采集文章", duplicatesRemoved: "移除重复", topicsRanked: "候选主题",
    waitingReview: "待审核", pipelineProgress: "流水线进度", selectedPost: "当前帖子",
    noPosts: "当前没有待处理帖子", runToGenerate: "立即运行 Agent，生成一条有来源依据的新草稿。",
    generatedCopy: "生成内容", copy: "复制", verifiedFacts: "已核验事实", sourceEvidence: "来源证据",
    source: "来源", published: "发布时间", evidence: "证据链接", recentRuns: "最近运行",
    started: "开始时间", result: "结果", fetched: "采集数", post: "帖子", humanCheckpoint: "人工检查点",
    reviewApprove: "审核与批准", facts: "事实", quality: "质量", scheduled: "已定时",
    publishVersion: "发布版本", approveQueue: "批准并进入发布", publishNow: "立即发布",
    schedulePublish: "定时发布", regenerate: "重新生成", requestRevision: "退回修改",
    humanFeedback: "人工反馈", revisionDescription: "说明需要修改的事实、结构或表达方式。",
    revisionNote: "修改意见", cancel: "取消", sendRequest: "保存修改意见",
    regenerateDraft: "重新生成草稿", regenerateDescription: "具体说明要如何修改；新草稿仍必须严格限定在已核验事实内。",
    regenerateNow: "立即重新生成", publication: "发布设置",
    scheduleDescription: "选择本地日期、时间和要发布的语言版本。", publishTime: "发布时间",
    originalVersion: "原文", chineseVersion: "中文", confirmSchedule: "确认定时",
    saveSession: "保存到当前会话", autoRefresh: "自动刷新",
    dashboardSecurity: "看板安全", operatorSettings: "操作员设置",
    adminToken: "管理员令牌", tokenStorage: "令牌仅保存在当前浏览器会话中，界面不会显示明文。",
  },
};

const stageLabels = {
  en: { FETCH: "Fetch", NORMALIZE: "Normalize", DEDUP: "Dedup", RANK: "Rank", VERIFY: "Verify", GENERATE: "Generate", QUALITY_CHECK: "Quality", PUBLISH: "Save" },
  zh: { FETCH: "采集", NORMALIZE: "标准化", DEDUP: "去重", RANK: "排序", VERIFY: "核验", GENERATE: "生成", QUALITY_CHECK: "质检", PUBLISH: "保存" },
};
const checkLabels = {
  en: { source_availability: "sources available", confidence: "confidence", evidence_richness: "evidence depth", unsupported_claims: "claims supported", no_hype: "no hype", length: "length", factual_consistency: "fact consistency", clarity: "clarity", grammar: "grammar", not_duplicate: "not duplicated" },
  zh: { source_availability: "来源可用", confidence: "置信度", evidence_richness: "证据充分", unsupported_claims: "事实有依据", no_hype: "无夸张表达", length: "长度合规", factual_consistency: "事实一致", clarity: "表达清晰", grammar: "语法", not_duplicate: "内容不重复" },
};
const statusLabels = {
  zh: { done: "已完成", running: "运行中", failed: "失败", waiting: "等待中", pending_review: "待审核", approved: "已批准", revision_requested: "等待修改", quality_rejected: "质量未通过", published: "已发布", partially_published: "部分发布", publish_failed: "发布失败", superseded: "已被新版本替代" },
};

function t(key) { return messages[state.language][key] || messages.en[key] || key; }
function titleCase(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function localizedValue(value) {
  if (state.language === "zh" && statusLabels.zh[value]) return statusLabels.zh[value];
  const common = { news: "AI 新闻", concept: "AI 概念", mixed: "混合模式", development: "开发环境", production: "生产环境", test: "测试环境" };
  if (state.language === "zh" && common[value]) return common[value];
  return titleCase(value);
}
function formatDate(value, options = {}) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return String(value);
  return new Intl.DateTimeFormat(state.language === "zh" ? "zh-CN" : undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", ...options }).format(date);
}
function safeUrl(value) {
  try { const parsed = new URL(value); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null; }
  catch { return null; }
}
function clear(element) { element.replaceChildren(); }
function icon(className) {
  const item = document.createElement("i");
  item.className = `ph ${className}`;
  item.setAttribute("aria-hidden", "true");
  return item;
}
function showToast(message, type = "success") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.append(icon(type === "error" ? "ph-warning-circle" : "ph-check-circle"));
  const copy = document.createElement("p");
  copy.textContent = message;
  toast.append(copy);
  $("toast-region").append(toast);
  window.setTimeout(() => toast.remove(), 4600);
}
function applyStaticTranslations() {
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    const value = messages[state.language][element.dataset.i18n];
    if (value) element.textContent = value;
  });
  $("language-toggle").querySelector("strong").textContent = state.language === "zh" ? "English" : "中文";
  $("language-toggle").setAttribute("aria-label", state.language === "zh" ? "Switch to English" : "切换到中文");
  $("auto-refresh-label").lastChild.textContent = ` ${t("autoRefresh")}`;
}
function statusClass(status) {
  if (["failed", "publish_failed", "quality_rejected"].includes(status)) return "failed";
  if (status === "revision_requested") return "revision";
  if (["pending_review", "running"].includes(status)) return "pending";
  return "";
}
function setStatus(element, status) {
  element.className = `status-badge ${statusClass(status)}`.trim();
  element.textContent = localizedValue(status || "waiting");
}
function currentTranslation(post) { return post?.translations?.zh && typeof post.translations.zh === "object" ? post.translations.zh : null; }
function currentVariant(post) {
  const translation = currentTranslation(post);
  if (state.language === "zh" && translation) return { title: translation.title, summary: translation.summary, content: translation.content, facts: translation.facts, language: "zh" };
  return { title: post.title, summary: post.summary, content: post.content, facts: null, language: "original" };
}
function publishLanguage(post) { return state.language === "zh" && currentTranslation(post) ? "zh" : "original"; }

function renderSystem() {
  const { system, latest_run: latestRun } = state.data;
  $("sidebar-environment").textContent = localizedValue(system.environment);
  $("content-mode").textContent = localizedValue(system.mode);
  $("destination-label").textContent = system.destinations.length ? system.destinations.map(titleCase).join(", ") : (state.language === "zh" ? "未配置" : "Not configured");
  $("next-run").textContent = system.scheduler_enabled ? `${state.language === "zh" ? "下次运行" : "Next run"} ${formatDate(system.next_run_at)}` : (state.language === "zh" ? "调度器已关闭" : "Scheduler disabled");
  $("dry-run-label").textContent = system.dry_run ? (state.language === "zh" ? "试运行" : "Dry run") : (state.language === "zh" ? "真实发布" : "Live mode");
  $("dry-run-pill").classList.toggle("live", !system.dry_run);
  const failed = latestRun?.status === "failed";
  $("system-health-label").textContent = system.pipeline_running ? (state.language === "zh" ? "流水线运行中" : "Pipeline running") : failed ? (state.language === "zh" ? "最近运行失败" : "Last run failed") : (state.language === "zh" ? "流水线正常" : "Pipeline healthy");
  document.querySelector(".health-dot").style.background = failed ? "var(--coral)" : system.pipeline_running ? "var(--blue)" : "var(--green)";
  $("run-now").disabled = system.pipeline_running || state.busy;
  $("run-now").querySelector("span").textContent = system.pipeline_running ? (state.language === "zh" ? "运行中" : "Running") : t("runNow");
  $("auto-refresh-label").classList.toggle("running", system.pipeline_running);
  if (latestRun) {
    setStatus($("run-status"), latestRun.status);
    $("run-id").textContent = latestRun.run_id;
    $("run-id").title = latestRun.run_id;
    $("pipeline-caption").textContent = `${state.language === "zh" ? "开始于" : "Started"} ${formatDate(latestRun.started_at)}`;
  } else {
    setStatus($("run-status"), "waiting");
    $("run-id").textContent = state.language === "zh" ? "暂无运行" : "No runs yet";
    $("pipeline-caption").textContent = state.language === "zh" ? "等待首次运行" : "Waiting for first execution";
  }
  const note = $("safety-note");
  note.classList.toggle("live", !system.dry_run);
  clear(note);
  note.append(icon(system.dry_run ? "ph-flask" : "ph-broadcast"));
  const copy = document.createElement("p");
  const strong = document.createElement("strong");
  const detail = document.createElement("span");
  strong.textContent = system.dry_run ? (state.language === "zh" ? "试运行已开启。" : "Dry run is on.") : (state.language === "zh" ? "真实发布已开启。" : "Live publishing is enabled.");
  detail.textContent = system.dry_run ? (state.language === "zh" ? " 批准、立即发布和定时发布都不会调用社交平台 API。" : " Approval and publication actions will not call a social API.") : (state.language === "zh" ? " 发布操作会调用已配置的平台 API。" : " Publishing can call configured social APIs.");
  copy.append(strong, detail);
  note.append(copy);
  $("settings-description").textContent = system.dashboard_auth_required ? (state.language === "zh" ? "此环境的批准和发布操作需要管理员令牌。" : "This environment requires an admin token for approval and publication actions.") : (state.language === "zh" ? "本地开发模式无需管理令牌，可以留空。" : "Local development mode does not require a dashboard token. You may leave this empty.");
  $("dashboard-token").value = state.token;
}
function renderMetrics() {
  const { metrics } = state.data;
  $("metric-fetched").textContent = metrics.fetched.toLocaleString();
  $("metric-duplicates").textContent = metrics.duplicates.toLocaleString();
  $("metric-ranked").textContent = metrics.ranked.toLocaleString();
  $("metric-pending").textContent = metrics.pending.toLocaleString();
}
function renderPipeline() {
  const list = $("pipeline-stages"); clear(list);
  for (const stage of state.data.pipeline) {
    const item = document.createElement("li"); item.className = `pipeline-stage ${stage.state}`;
    const dot = document.createElement("span"); dot.className = "stage-dot";
    dot.append(icon(stage.state === "complete" ? "ph-check" : stage.state === "failed" ? "ph-x" : "ph-dot-outline-fill"));
    const label = document.createElement("span"); label.textContent = stageLabels[state.language][stage.key] || localizedValue(stage.key);
    item.append(dot, label); list.append(item);
  }
}
function renderFacts(post, variant) {
  const list = $("facts-list"); clear(list);
  $("facts-count").textContent = state.language === "zh" ? `提取 ${post.facts.length} 条` : `${post.facts.length} extracted`;
  if (!post.facts.length) {
    const item = document.createElement("li"); item.className = "fact-item unsupported"; item.append(icon("ph-warning-circle"));
    const text = document.createElement("p"); text.textContent = state.language === "zh" ? "此帖子没有保存已提取的事实。" : "No extracted fact claims are stored for this post.";
    item.append(text); list.append(item); return;
  }
  post.facts.forEach((fact, index) => {
    const item = document.createElement("li"); item.className = `fact-item ${fact.supported ? "" : "unsupported"}`.trim();
    const stateIcon = document.createElement("span"); stateIcon.className = "fact-state"; stateIcon.append(icon(fact.supported ? "ph-check-circle" : "ph-warning-circle"));
    const text = document.createElement("p"); text.textContent = variant.facts?.[index] || fact.text || (state.language === "zh" ? "未命名事实" : "Untitled fact");
    const confidence = document.createElement("small"); confidence.textContent = `${Math.round(Number(fact.confidence || 0) * 100)}% ${state.language === "zh" ? "置信度" : "confidence"}`;
    item.append(stateIcon, text, confidence); list.append(item);
  });
}
function renderSources(post) {
  const table = $("sources-table"); clear(table);
  $("sources-count").textContent = state.language === "zh" ? `${post.sources.length} 个链接` : `${post.sources.length} linked`;
  if (!post.sources.length) {
    const row = document.createElement("tr"); const cell = document.createElement("td"); cell.colSpan = 3;
    cell.textContent = state.language === "zh" ? "此草稿没有保存来源链接。" : "No source references are stored for this draft.";
    row.append(cell); table.append(row); return;
  }
  for (const source of post.sources) {
    const row = document.createElement("tr"); const title = document.createElement("td"); title.textContent = source.title || t("source");
    const published = document.createElement("td"); published.textContent = formatDate(source.published_at, { year: "numeric" });
    const evidence = document.createElement("td"); const href = safeUrl(source.url);
    if (href) {
      const link = document.createElement("a"); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer";
      link.textContent = state.language === "zh" ? "打开来源" : "Open source"; evidence.append(link);
    } else evidence.textContent = state.language === "zh" ? "不可用" : "Unavailable";
    row.append(title, published, evidence); table.append(row);
  }
}
function renderQuality(post) {
  $("review-quality-score").textContent = `${post.quality_score}`;
  $("review-quality").textContent = post.quality_passed ? (state.language === "zh" ? `已通过 · 门槛 ${state.data.system.quality_threshold}` : `Passed threshold ${state.data.system.quality_threshold}`) : (state.language === "zh" ? `需要处理 · 门槛 ${state.data.system.quality_threshold}` : `Needs attention · threshold ${state.data.system.quality_threshold}`);
  $("quality-bar-value").style.width = `${Math.max(0, Math.min(100, post.quality_score))}%`;
  const checks = $("quality-checks"); clear(checks);
  for (const check of post.quality_checks) {
    const item = document.createElement("li"); item.className = check.passed ? "" : "failed";
    item.textContent = checkLabels[state.language][check.key] || localizedValue(check.key); checks.append(item);
  }
}
function renderActions(post) {
  const canApprove = ["pending_review", "revision_requested"].includes(post.status) && post.quality_score >= state.data.system.quality_threshold && post.confidence_score >= state.data.system.confidence_threshold;
  const canRevise = ["pending_review", "approved"].includes(post.status);
  const canRegenerate = ["pending_review", "revision_requested", "approved", "quality_rejected"].includes(post.status);
  const isApproved = post.status === "approved";
  const hasActiveSchedule = Boolean(post.active_schedule);
  const language = publishLanguage(post);
  $("approve-post").hidden = isApproved; $("approve-post").disabled = !canApprove || state.busy;
  $("publish-post").hidden = !isApproved; $("publish-post").disabled = !isApproved || state.busy || hasActiveSchedule;
  $("schedule-post").hidden = !isApproved; $("schedule-post").disabled = !isApproved || state.busy || hasActiveSchedule;
  $("regenerate-post").disabled = !canRegenerate || state.busy; $("request-revision").disabled = !canRevise || state.busy;
  $("publication-language").textContent = language === "zh" ? (state.language === "zh" ? "中文" : "Chinese") : (state.language === "zh" ? "原文" : "Original");
  $("schedule-summary").hidden = !post.active_schedule;
  if (post.active_schedule) $("schedule-summary-text").textContent = `${formatDate(post.active_schedule.scheduled_for)} · ${post.active_schedule.language === "zh" ? (state.language === "zh" ? "中文" : "Chinese") : (state.language === "zh" ? "原文" : "Original")}`;
  if (hasActiveSchedule) $("action-help").textContent = state.language === "zh" ? "此帖子已定时。如需更换发布方案，请先退回修改，系统会安全取消旧定时任务。" : "This post is scheduled. Request a revision to safely cancel and replace the schedule.";
  else if (post.status === "quality_rejected") $("action-help").textContent = state.language === "zh" ? "质量门槛未通过，请根据问题重新生成。" : "Quality gate rejected this draft. Regenerate it before approval.";
  else if (isApproved) $("action-help").textContent = state.data.system.dry_run ? (state.language === "zh" ? "当前是试运行，立即或定时发布都不会调用社交平台。" : "Dry run is active; immediate and scheduled publication will not call a social API.") : (state.language === "zh" ? "立即发布会调用所有已配置的平台适配器。" : "This action will call every configured destination adapter.");
  else if (!canApprove) $("action-help").textContent = state.language === "zh" ? "质量分和事实置信度通过后才能批准。" : "Approval is locked until quality and confidence thresholds pass.";
  else $("action-help").textContent = state.language === "zh" ? "批准和发布是两个独立操作。" : "Approval is recorded; publishing remains a separate explicit action.";
}
function renderPost() {
  const post = state.data.selected_post;
  const hasPost = Boolean(post);
  $("empty-state").hidden = hasPost; $("post-details").hidden = !hasPost;
  const queue = state.data.review_queue;
  const index = queue.findIndex((item) => item.id === post?.id);
  $("queue-position").textContent = hasPost ? `${index + 1} / ${queue.length}` : `0 / ${queue.length}`;
  $("previous-post").disabled = index <= 0; $("next-post").disabled = index < 0 || index >= queue.length - 1;
  if (!hasPost) {
    $("post-title").textContent = state.language === "zh" ? "审核队列为空" : "Review queue is clear";
    $("post-mode").textContent = "—"; $("post-score").textContent = "—"; setStatus($("review-status"), "waiting");
    $("review-topic-title").textContent = state.language === "zh" ? "请选择一条帖子开始审核。" : "Select a post to begin review.";
    $("review-summary").textContent = state.language === "zh" ? "事实、来源和质量检查会显示在这里。" : "The agent’s evidence and quality checks will appear here.";
    for (const id of ["approve-post", "publish-post", "schedule-post", "regenerate-post", "request-revision"]) $(id).disabled = true;
    return;
  }
  state.selectedId = post.id;
  const variant = currentVariant(post);
  $("post-title").textContent = variant.title; $("post-mode").textContent = localizedValue(post.mode);
  $("post-score").textContent = `${state.language === "zh" ? "质量" : "Quality"} ${post.quality_score}`;
  $("post-content").textContent = variant.content;
  $("character-count").textContent = `${variant.content.length.toLocaleString()} ${state.language === "zh" ? "字符" : "characters"}`;
  $("post-provider").textContent = variant.language === "zh" ? `${titleCase(currentTranslation(post).provider)} · ${currentTranslation(post).model}` : `${titleCase(post.llm.provider)} · ${post.llm.model}`;
  $("post-language-badge").textContent = state.translationInFlight ? (state.language === "zh" ? "翻译中" : "Translating") : variant.language === "zh" ? (state.language === "zh" ? "中文发布版" : "Chinese version") : (state.language === "zh" ? "英文原文" : "Original");
  setStatus($("review-status"), post.status);
  $("review-topic-title").textContent = variant.title; $("review-summary").textContent = post.revision_note || variant.summary;
  const supported = post.facts.filter((fact) => fact.supported).length;
  $("review-facts").textContent = state.language === "zh" ? `${post.facts.length} 条中 ${supported} 条有依据` : `${supported} of ${post.facts.length} claims supported`;
  $("review-sources").textContent = state.language === "zh" ? `已附 ${post.sources.length} 个来源` : `${post.sources.length} source${post.sources.length === 1 ? "" : "s"} attached`;
  $("review-destination").textContent = state.data.system.destinations.length ? state.data.system.destinations.map(titleCase).join(", ") : (state.language === "zh" ? "未配置" : "Not configured");
  renderFacts(post, variant); renderSources(post); renderQuality(post); renderActions(post);
}
function renderRuns() {
  const table = $("runs-table"); clear(table);
  $("run-count").textContent = state.language === "zh" ? `显示 ${state.data.recent_runs.length} 条` : `${state.data.recent_runs.length} shown`;
  if (!state.data.recent_runs.length) {
    const row = document.createElement("tr"); const cell = document.createElement("td"); cell.colSpan = 5;
    cell.textContent = state.language === "zh" ? "尚未记录流水线运行。" : "No pipeline runs have been recorded yet."; row.append(cell); table.append(row); return;
  }
  for (const run of state.data.recent_runs) {
    const row = document.createElement("tr");
    const values = [formatDate(run.started_at), localizedValue(run.mode), localizedValue(run.status), String(run.counts.fetched ?? "—"), run.counts.post_id ? `#${run.counts.post_id}` : "—"];
    for (const value of values) { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }
    table.append(row);
  }
}
function renderAll() { applyStaticTranslations(); renderSystem(); renderMetrics(); renderPipeline(); renderPost(); renderRuns(); }

async function fetchDashboard(postId = null, { silent = false } = {}) {
  const url = postId ? `/api/dashboard?post_id=${encodeURIComponent(postId)}` : "/api/dashboard";
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Dashboard data failed (${response.status})`);
  const previousRun = state.data?.latest_run;
  state.data = await response.json();
  if (state.followRun && state.data.latest_run && state.data.latest_run.run_id !== state.runBaselineId && state.data.latest_run.status === "done") {
    state.followRun = false;
    const newPostId = state.data.latest_run.counts.post_id;
    if (newPostId && newPostId !== postId) return fetchDashboard(newPostId, { silent });
    if (!silent) showToast(state.language === "zh" ? "Agent 运行完成" : "Agent run completed");
  }
  if (state.followRun && state.data.latest_run?.status === "failed" && previousRun?.run_id !== state.data.latest_run.run_id) {
    state.followRun = false;
    showToast(state.language === "zh" ? "Agent 运行失败，请查看运行历史" : "Agent run failed; inspect run history", "error");
  }
  state.selectedId = state.data.selected_post?.id || null;
  renderAll();
  if (state.language === "zh" && state.data.selected_post && !currentTranslation(state.data.selected_post) && !state.translationInFlight) void ensureChineseTranslation();
}
function actionHeaders() {
  const headers = { "Content-Type": "application/json", "X-Requested-With": "AI-Daily-Content-Agent" };
  if (state.token) headers["X-Dashboard-Token"] = state.token;
  return headers;
}
async function parseError(response) {
  try { const body = await response.json(); return body.detail || `Request failed (${response.status})`; }
  catch { return `Request failed (${response.status})`; }
}
async function apiPost(url, body = null) {
  const response = await fetch(url, { method: "POST", headers: actionHeaders(), body: body ? JSON.stringify(body) : undefined });
  if (response.status === 401) { $("settings-dialog").showModal(); throw new Error(state.language === "zh" ? "请输入管理员令牌后重试。" : "Enter the dashboard admin token, then retry."); }
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}
async function postAction(action, body = null) {
  if (!state.selectedId || state.busy) return null;
  state.busy = true; renderActions(state.data.selected_post);
  try {
    const result = await apiPost(`/api/posts/${state.selectedId}/${action}`, body);
    showToast(result.message || (state.language === "zh" ? "操作完成" : "Action complete"));
    await fetchDashboard(result.post_id || state.selectedId);
    return result;
  } catch (error) { showToast(error.message || (state.language === "zh" ? "操作失败" : "Action failed"), "error"); return null; }
  finally { state.busy = false; if (state.data?.selected_post) renderActions(state.data.selected_post); }
}
async function ensureChineseTranslation() {
  const post = state.data?.selected_post;
  if (!post || currentTranslation(post) || state.translationInFlight) return;
  state.translationInFlight = true; renderPost();
  try {
    const result = await apiPost(`/api/posts/${post.id}/translate/zh`);
    showToast(state.language === "zh" ? "中文发布版已生成并完成一致性检查" : result.message);
    await fetchDashboard(post.id, { silent: true });
  } catch (error) { showToast(error.message || (state.language === "zh" ? "中文翻译失败" : "Translation failed"), "error"); }
  finally { state.translationInFlight = false; if (state.data?.selected_post) renderPost(); }
}
async function runNow() {
  if (state.busy || state.data?.system.pipeline_running) return;
  state.busy = true; renderSystem();
  try {
    state.runBaselineId = state.data.latest_run?.run_id || null;
    const result = await apiPost("/api/pipeline/run");
    state.followRun = true;
    showToast(state.language === "zh" ? "Agent 已启动，页面会自动刷新进度" : result.message);
    state.data.system.pipeline_running = true; renderSystem();
  } catch (error) { showToast(error.message || (state.language === "zh" ? "启动失败" : "Run failed to start"), "error"); }
  finally { state.busy = false; renderSystem(); }
}
function moveQueue(direction) {
  const queue = state.data?.review_queue || [];
  const current = queue.findIndex((item) => item.id === state.selectedId);
  const target = queue[current + direction];
  if (target) fetchDashboard(target.id).catch((error) => showToast(error.message, "error"));
}
function defaultScheduleTime() {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  date.setMinutes(Math.ceil(date.getMinutes() / 5) * 5, 0, 0);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function bindEvents() {
  $("language-toggle").addEventListener("click", () => {
    state.language = state.language === "en" ? "zh" : "en";
    localStorage.setItem("dashboardLanguage", state.language); renderAll();
    if (state.language === "zh") void ensureChineseTranslation();
  });
  $("run-now").addEventListener("click", () => void runNow());
  $("previous-post").addEventListener("click", () => moveQueue(-1));
  $("next-post").addEventListener("click", () => moveQueue(1));
  $("approve-post").addEventListener("click", () => void postAction("approve"));
  $("publish-post").addEventListener("click", () => void postAction("publish", { language: publishLanguage(state.data.selected_post) }));
  $("request-revision").addEventListener("click", () => { $("revision-reason").value = ""; $("revision-dialog").showModal(); });
  $("revision-form").addEventListener("submit", (event) => {
    event.preventDefault(); const reason = $("revision-reason").value.trim();
    if (reason.length < 3) { showToast(state.language === "zh" ? "请填写具体的修改意见。" : "Please add a specific revision note.", "error"); return; }
    $("revision-dialog").close(); void postAction("revision", { reason });
  });
  $("cancel-revision").addEventListener("click", () => $("revision-dialog").close());
  $("regenerate-post").addEventListener("click", () => {
    const note = state.data.selected_post?.revision_note || "";
    $("regenerate-reason").value = note.replace(/^Human review:\s*/i, "");
    $("regenerate-dialog").showModal();
  });
  $("regenerate-form").addEventListener("submit", (event) => {
    event.preventDefault(); const reason = $("regenerate-reason").value.trim();
    if (reason.length < 3) { showToast(state.language === "zh" ? "请填写具体的重新生成要求。" : "Please add specific regeneration feedback.", "error"); return; }
    $("regenerate-dialog").close(); void postAction("regenerate", { reason });
  });
  $("cancel-regenerate").addEventListener("click", () => $("regenerate-dialog").close());
  $("schedule-post").addEventListener("click", () => {
    $("schedule-time").value = defaultScheduleTime();
    const hasChinese = Boolean(currentTranslation(state.data.selected_post));
    $("schedule-language").querySelector('option[value="zh"]').disabled = !hasChinese;
    $("schedule-language").value = publishLanguage(state.data.selected_post);
    $("schedule-dialog").showModal();
  });
  $("schedule-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const localTime = $("schedule-time").value;
    if (!localTime) return;
    const result = await postAction("schedule", { scheduled_for: new Date(localTime).toISOString(), language: $("schedule-language").value });
    if (result) $("schedule-dialog").close();
  });
  $("cancel-schedule").addEventListener("click", () => $("schedule-dialog").close());
  $("copy-post").addEventListener("click", async () => {
    const post = state.data?.selected_post; if (!post) return;
    try { await navigator.clipboard.writeText(currentVariant(post).content); showToast(state.language === "zh" ? "帖子已复制" : "Post copied to clipboard"); }
    catch { showToast(state.language === "zh" ? "浏览器未允许访问剪贴板" : "Clipboard access was not available", "error"); }
  });
  for (const button of document.querySelectorAll("[data-target]")) button.addEventListener("click", () => $(button.dataset.target)?.scrollIntoView({ behavior: "smooth" }));
  $("open-settings").addEventListener("click", () => $("settings-dialog").showModal());
  $("settings-form").addEventListener("submit", (event) => {
    event.preventDefault(); state.token = $("dashboard-token").value.trim();
    if (state.token) sessionStorage.setItem("dashboardToken", state.token); else sessionStorage.removeItem("dashboardToken");
    $("settings-dialog").close(); showToast(state.language === "zh" ? "当前会话设置已保存" : "Dashboard session settings saved");
  });
  $("cancel-settings").addEventListener("click", () => $("settings-dialog").close());
  for (const dialog of document.querySelectorAll("dialog")) dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  for (const item of document.querySelectorAll(".nav-item[href]")) item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((node) => node.classList.remove("active")); item.classList.add("active");
  });
}
function startAutoRefresh() {
  window.clearInterval(state.pollTimer);
  state.pollTimer = window.setInterval(() => {
    if (state.busy || state.translationInFlight || document.hidden || document.querySelector("dialog[open]")) return;
    fetchDashboard(state.selectedId, { silent: true }).catch(() => {});
  }, 5000);
}

bindEvents();
fetchDashboard().then(startAutoRefresh).catch((error) => {
  showToast(error.message || "Dashboard could not load", "error");
  $("post-title").textContent = state.language === "zh" ? "看板无法加载" : "Dashboard unavailable";
});
