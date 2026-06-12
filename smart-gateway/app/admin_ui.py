ADMIN_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Smart Gateway Admin</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #667085;
      --line: #d9dee7;
      --accent: #0f766e;
      --accent-dark: #115e59;
      --danger: #b42318;
      --warn: #a15c07;
      --ok: #067647;
      --code: #101828;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    .wrap {
      width: min(1360px, calc(100vw - 32px));
      margin: 0 auto;
    }
    .topbar {
      min-height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
    }
    .sub {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }
    main {
      padding: 22px 0 40px;
    }
    .login {
      max-width: 520px;
      margin: 64px auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    .panel h2 {
      margin: 0 0 12px;
      font-size: 16px;
    }
    .metric {
      font-size: 28px;
      font-weight: 700;
      line-height: 1.1;
    }
    .label {
      color: var(--muted);
      font-size: 13px;
      margin-top: 4px;
    }
    .tabs {
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--line);
      margin: 18px 0 16px;
      overflow-x: auto;
    }
    .tab {
      border: 0;
      border-bottom: 3px solid transparent;
      background: transparent;
      padding: 12px 10px 10px;
      cursor: pointer;
      color: var(--muted);
      font-weight: 600;
      white-space: nowrap;
    }
    .tab.active {
      color: var(--accent-dark);
      border-bottom-color: var(--accent);
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .row.between {
      justify-content: space-between;
    }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      font: inherit;
      background: #fff;
      color: var(--text);
    }
    textarea {
      min-height: 88px;
      resize: vertical;
    }
    label {
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 9px 12px;
      font-weight: 650;
      cursor: pointer;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    button.primary:hover { background: var(--accent-dark); }
    button.danger {
      color: var(--danger);
      border-color: #f1b8b3;
    }
    button:disabled {
      opacity: .55;
      cursor: not-allowed;
    }
    code, .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color: var(--code);
      word-break: break-all;
    }
    .copybox {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      margin: 8px 0;
    }
    .copybox input {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      text-align: left;
      padding: 10px 8px;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-weight: 700;
      background: #fafbfc;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    .tablewrap {
      max-height: 620px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
      white-space: nowrap;
    }
    .pill.ok { color: var(--ok); background: #ecfdf3; border-color: #abefc6; }
    .pill.bad { color: var(--danger); background: #fef3f2; border-color: #fecdca; }
    .pill.warn { color: var(--warn); background: #fffaeb; border-color: #fedf89; }
    .provider {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 12px;
      background: var(--panel);
    }
    .provider-grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr 100px 100px;
      gap: 12px;
    }
    .provider-wide {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 12px;
    }
    .hidden { display: none !important; }
    .notice {
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--muted);
      margin-bottom: 14px;
    }
    .error {
      color: var(--danger);
      font-weight: 650;
    }
    @media (max-width: 920px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .provider-grid, .provider-wide { grid-template-columns: 1fr; }
    }
    @media (max-width: 560px) {
      .grid { grid-template-columns: 1fr; }
      .wrap { width: min(100vw - 20px, 1360px); }
      .topbar { align-items: flex-start; flex-direction: column; padding: 12px 0; }
    }
  </style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <div>
        <h1>AI Smart Gateway Operations</h1>
        <div class="sub">New API 后置智能路由层：运行观测、健康矩阵、最终流向和兜底策略</div>
      </div>
      <div class="row">
        <button id="refreshBtn">刷新</button>
        <button id="logoutBtn">退出</button>
      </div>
    </div>
  </header>

  <main class="wrap">
    <section id="loginView" class="login">
      <h2>管理员登录</h2>
      <p class="sub">输入 ADMIN_TOKEN 后进入后台。Token 只保存在当前浏览器。</p>
      <label for="tokenInput">Admin Token</label>
      <input id="tokenInput" type="password" autocomplete="current-password">
      <div class="row" style="margin-top: 12px;">
        <button id="loginBtn" class="primary">登录</button>
      </div>
      <p id="loginError" class="error"></p>
    </section>

    <section id="appView" class="hidden">
      <div id="notice" class="notice">正在加载...</div>

      <div class="grid">
        <div class="panel">
          <div class="metric" id="providerCount">-</div>
          <div class="label">源池上游</div>
        </div>
        <div class="panel">
          <div class="metric" id="modelCount">-</div>
          <div class="label">运行时可用模型</div>
        </div>
        <div class="panel">
          <div class="metric" id="chatHealthy">-</div>
          <div class="label">Chat 健康通道</div>
        </div>
        <div class="panel">
          <div class="metric" id="responsesHealthy">-</div>
          <div class="label">Responses 健康通道</div>
        </div>
      </div>

      <div class="tabs">
        <button class="tab active" data-tab="overview">运行概览</button>
        <button class="tab" data-tab="models">运行时模型</button>
        <button class="tab" data-tab="matrix">健康矩阵</button>
        <button class="tab" data-tab="logs">路由日志</button>
        <button class="tab" data-tab="providers">源池策略</button>
      </div>

      <section id="tab-overview" class="tabpane">
        <div class="panel">
          <h2>入口归属</h2>
          <div class="notice">公开用户、令牌、额度、订阅、渠道和模型管理都在 New API。Smart Gateway 只作为 New API 后面的智能路由通道，不再发放客户端 Key。</div>
          <label>公开 Base URL</label>
          <div class="copybox">
            <input id="baseUrl" readonly>
            <button data-copy="baseUrl">复制</button>
          </div>
          <label>公开 API Key</label>
          <div class="copybox">
            <input id="apiKeyHint" readonly>
            <button data-copy="apiKeyHint">复制</button>
          </div>
          <label>New API 管理入口</label>
          <div class="copybox">
            <input id="newApiAdminUrl" readonly>
            <button data-copy="newApiAdminUrl">复制</button>
          </div>
          <label>New API Router 通道</label>
          <div class="copybox">
            <input id="routerChannel" readonly>
            <button data-copy="routerChannel">复制</button>
          </div>
          <label>New API 上游源池标签</label>
          <div class="copybox">
            <input id="sourceTag" readonly>
            <button data-copy="sourceTag">复制</button>
          </div>
          <label>Router 服务用户分组</label>
          <div class="copybox">
            <input id="routerGroups" readonly>
            <button data-copy="routerGroups">复制</button>
          </div>
          <label>Smart Gateway 运维入口</label>
          <div class="copybox">
            <input id="adminUrl" readonly>
            <button data-copy="adminUrl">复制</button>
          </div>
          <div class="row" style="margin-top: 12px;">
            <button id="syncBtn" class="primary">同步 New API 源池</button>
            <button id="probeBtn" class="primary">重载配置并增量探测</button>
          </div>
        </div>
      </section>

      <section id="tab-models" class="tabpane hidden">
        <div class="tablewrap">
          <table>
            <thead>
              <tr>
                <th>模型</th>
                <th>Chat 健康数</th>
                <th>Responses 健康数</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody id="modelsBody"></tbody>
          </table>
        </div>
      </section>

      <section id="tab-matrix" class="tabpane hidden">
        <div class="tablewrap">
          <table>
            <thead>
              <tr>
                <th>接口</th>
                <th>模型</th>
                <th>上游</th>
                <th>实际模型</th>
                <th>来源</th>
                <th>格式</th>
                <th>探测路径</th>
                <th>状态</th>
                <th>延迟</th>
                <th>最近检测</th>
                <th>下次探测</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody id="matrixBody"></tbody>
          </table>
        </div>
      </section>

      <section id="tab-logs" class="tabpane hidden">
        <div class="tablewrap">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>请求ID</th>
                <th>接口</th>
                <th>模型</th>
                <th>上游</th>
                <th>路由</th>
                <th>成本</th>
                <th>实际模型</th>
                <th>状态</th>
                <th>耗时</th>
                <th>Token</th>
                <th>错误</th>
              </tr>
            </thead>
            <tbody id="logsBody"></tbody>
          </table>
        </div>
      </section>

      <section id="tab-providers" class="tabpane hidden">
        <div class="row between" style="margin-bottom: 12px;">
          <div class="sub">源池策略会回写 New API 渠道。新增/删除上游、修改 key、模型权限、用户分组和订阅仍在 New API 管理。</div>
          <div class="row">
            <button id="savePolicyBtn" class="primary">保存源池策略</button>
            <button id="syncBtnProviders" class="primary">同步 New API 源池</button>
            <button id="probeBtnProviders" class="primary">重载配置并增量探测</button>
          </div>
        </div>
        <div class="notice">维护流程：New API 录入真实上游和 key；这里调整启停、权重、路由桶、成本层级和声明模型。保存后会自动写回 New API 渠道标签并同步 Smart Gateway。</div>
        <div id="providersEditor"></div>
      </section>
    </section>
  </main>

  <script>
    const tokenKey = "ai-smart-gateway-admin-token";
    let state = null;
    let providers = [];

    const $ = (id) => document.getElementById(id);
    const token = () => localStorage.getItem(tokenKey) || "";
    const authHeaders = () => ({ "Authorization": "Bearer " + token() });
    const setNotice = (text) => { $("notice").textContent = text; };

    async function api(path, options = {}) {
      const headers = Object.assign({}, options.headers || {}, authHeaders());
      const res = await fetch(path, Object.assign({}, options, { headers }));
      if (res.status === 401) throw new Error("未授权，请重新登录");
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    }

    function showApp() {
      $("loginView").classList.add("hidden");
      $("appView").classList.remove("hidden");
    }

    function showLogin(message = "") {
      $("appView").classList.add("hidden");
      $("loginView").classList.remove("hidden");
      $("loginError").textContent = message;
    }

    function mask(value) {
      if (!value) return "";
      if (value.length <= 12) return "*".repeat(value.length);
      return value.slice(0, 6) + "... " + value.slice(-4);
    }

    function statusPill(ok, warn = false) {
      const cls = ok ? "ok" : warn ? "warn" : "bad";
      const text = ok ? "健康" : warn ? "部分" : "不可用";
      return `<span class="pill ${cls}">${text}</span>`;
    }

    function formatTs(ts, empty = "") {
      return ts ? new Date(ts * 1000).toLocaleString() : empty;
    }

    function routeLabel(value) {
      return ({
        primary: "主力",
        opportunistic: "机会",
        backup: "备份",
        other: "其它",
        explore: "探索",
        probe_retry: "探测体重试",
        shadow: "模型列表补偿",
        paid_fallback: "付费兜底"
      })[value] || value || "";
    }

    function costLabel(value, fallbackOnly = false) {
      const label = ({
        free: "免费",
        metered: "计量",
        paid: "付费"
      })[value] || value || "";
      return fallbackOnly ? `${label} 仅兜底` : label;
    }

    function renderOverview(data) {
      $("providerCount").textContent = data.provider_count;
      $("modelCount").textContent = data.models.length;
      $("chatHealthy").textContent = data.chat_healthy;
      $("responsesHealthy").textContent = data.responses_healthy;
      $("baseUrl").value = data.base_url;
      $("apiKeyHint").value = "在 New API 的令牌页面生成和管理";
      $("newApiAdminUrl").value = data.new_api_admin_url || "";
      $("routerChannel").value = data.router_channel_name || "Smart Gateway Router";
      $("sourceTag").value = data.source_tag || "gateway-source";
      $("routerGroups").value = data.router_groups || "default,vip";
      $("adminUrl").value = data.admin_url;
      setNotice(`最后探测: ${formatTs(data.last_probe_at, "未完成")}`);
    }

    function renderModels(data) {
      $("modelsBody").innerHTML = data.models.map((m) => `
        <tr>
          <td class="mono">${m.id}</td>
          <td>${m.chat_ok}</td>
          <td>${m.responses_ok}</td>
          <td>${statusPill(m.chat_ok > 0 || m.responses_ok > 0, m.chat_ok === 0 || m.responses_ok === 0)}</td>
        </tr>
      `).join("");
    }

    function renderMatrix(data) {
      const rows = [];
      for (const kind of ["chat", "responses"]) {
        const group = data.health[kind] || {};
        for (const model of Object.keys(group).sort()) {
          for (const item of Object.values(group[model])) {
            rows.push(`
              <tr>
                <td>${kind}</td>
                <td class="mono">${model}</td>
                <td>${item.provider_name || item.provider_id}</td>
                <td class="mono">${item.actual_model || ""}</td>
                <td class="mono">${item.source || ""}</td>
                <td class="mono">${item.request_format || ""}</td>
                <td class="mono">${item.probe_path || ""}</td>
                <td>${statusPill(!!item.healthy)}</td>
                <td>${item.latency_ms == null ? "" : item.latency_ms + " ms"}</td>
                <td>${formatTs(item.checked_at, "未检测")}</td>
                <td>${formatTs(item.next_probe_at)}</td>
                <td class="mono">${item.reason || item.skip_reason || ""}</td>
              </tr>
            `);
          }
        }
      }
      $("matrixBody").innerHTML = rows.join("");
    }

    function renderLogs(data) {
      $("logsBody").innerHTML = (data.logs || []).map((row) => {
        const usage = row.usage || {};
        const tokens = usage.total_tokens == null ? "" : usage.total_tokens;
        return `
          <tr>
            <td>${formatTs(row.ts)}</td>
            <td class="mono">${row.request_id || ""}</td>
            <td class="mono">${row.kind || ""}${row.stream ? " stream" : ""}</td>
            <td class="mono">${row.requested_model || ""}</td>
            <td>${row.provider_id || ""}</td>
            <td>${routeLabel(row.route_bucket || row.route_group)}</td>
            <td>${costLabel(row.cost_tier, row.fallback_only)}</td>
            <td class="mono">${row.actual_model || ""}</td>
            <td>${statusPill(!!row.success)}</td>
            <td>${row.latency_ms == null ? "" : row.latency_ms + " ms"}</td>
            <td>${tokens}</td>
            <td class="mono">${row.error_type || ""}</td>
          </tr>
        `;
      }).join("");
    }

    function providerTemplate(p, index) {
      const policy = p.editable_policy || {};
      const models = policy.models || (p.declared_models || []).join(",");
      const runtime = p.runtime || {};
      const baseUrls = (policy.base_urls || p.base_urls || [policy.base_url || p.base_url || ""]).join("\\n");
      const enabledValue = String((policy.enabled ?? p.enabled) !== false);
      const fallbackValue = String((policy.fallback_only ?? p.fallback_only) === true);
      return `
        <div class="provider" data-index="${index}">
          <div class="row between">
            <strong>${escapeHtml(p.name || p.id || "provider")}</strong>
            <div class="row">
              <span class="pill ${p.enabled !== false ? "ok" : "bad"}">${p.enabled !== false ? "启用" : "停用"}</span>
              <span class="pill">${routeLabel(p.route_group)}</span>
              <span class="pill">${costLabel(p.cost_tier, p.fallback_only)}</span>
              <span class="pill">健康 ${runtime.healthy ?? 0}</span>
              <span class="pill">异常 ${runtime.unhealthy ?? 0}</span>
            </div>
          </div>
          <div class="provider-grid">
            <div><label>ID</label><input readonly data-field="id" value="${escapeHtml(p.new_api_channel_id || policy.id || "")}"></div>
            <div><label>启用</label><select data-field="enabled">${option("true", "启用", enabledValue)}${option("false", "停用", enabledValue)}</select></div>
            <div><label>路由桶</label><select data-field="route_group">${option("primary", "主力", policy.route_group || p.route_group)}${option("opportunistic", "机会", policy.route_group || p.route_group)}${option("backup", "备份", policy.route_group || p.route_group)}${option("paid_fallback", "付费兜底", policy.route_group || p.route_group)}${option("other", "其它", policy.route_group || p.route_group)}</select></div>
            <div><label>成本层级</label><select data-field="cost_tier">${option("free", "免费", policy.cost_tier || p.cost_tier)}${option("metered", "计量", policy.cost_tier || p.cost_tier)}${option("paid", "付费", policy.cost_tier || p.cost_tier)}${option("unknown", "未知", policy.cost_tier || p.cost_tier)}</select></div>
            <div><label>仅兜底</label><select data-field="fallback_only">${option("false", "否", fallbackValue)}${option("true", "是", fallbackValue)}</select></div>
            <div><label>优先级</label><input data-field="priority" type="number" min="0" max="10000" value="${policy.priority ?? p.priority ?? 0}"></div>
            <div><label>权重</label><input data-field="weight" type="number" min="1" max="10000" value="${policy.weight ?? p.weight ?? 100}"></div>
            <div><label>New API 标签</label><input readonly value="${escapeHtml(policy.tag || p.tag || "")}"></div>
          </div>
          <div class="provider-wide">
            <div>
              <label>API Key 掩码</label>
              <input readonly value="${escapeHtml(p.api_key_preview || "")}">
            </div>
            <div>
              <label>Base URL</label>
              <input data-field="base_url" value="${escapeHtml(policy.base_url || p.base_url || "")}">
            </div>
            <div>
              <label>兼容 Base URL，只读</label>
              <textarea readonly>${escapeHtml(baseUrls)}</textarea>
            </div>
            <div>
              <label>声明模型，逗号或换行分隔</label>
              <textarea data-field="models">${escapeHtml(models)}</textarea>
            </div>
          </div>
        </div>
      `;
    }

    function option(value, label, selected) {
      return `<option value="${value}" ${String(value) === String(selected) ? "selected" : ""}>${label}</option>`;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function renderProviders() {
      $("providersEditor").innerHTML = providers.map(providerTemplate).join("");
    }

    function collectPolicyUpdates() {
      return Array.from(document.querySelectorAll(".provider")).map((node) => {
        const get = (field) => node.querySelector(`[data-field="${field}"]`)?.value || "";
        return {
          id: Number(get("id")),
          enabled: get("enabled") === "true",
          route_group: get("route_group"),
          cost_tier: get("cost_tier"),
          fallback_only: get("fallback_only") === "true",
          priority: Number(get("priority") || 0),
          weight: Number(get("weight") || 100),
          base_url: get("base_url"),
          models: get("models")
        };
      }).filter((item) => item.id > 0);
    }

    async function loadAll() {
      showApp();
      const [overview, providerData] = await Promise.all([
        api("/gateway-admin/api/overview"),
        api("/gateway-admin/api/providers")
      ]);
      const logs = await api("/gateway-admin/api/request-logs?limit=200");
      state = overview;
      providers = providerData.providers;
      renderOverview(overview);
      renderModels(overview);
      renderMatrix(overview);
      renderLogs(logs);
      renderProviders();
    }

    $("loginBtn").addEventListener("click", async () => {
      localStorage.setItem(tokenKey, $("tokenInput").value.trim());
      try {
        await loadAll();
      } catch (err) {
        localStorage.removeItem(tokenKey);
        showLogin(err.message);
      }
    });

    $("logoutBtn").addEventListener("click", () => {
      localStorage.removeItem(tokenKey);
      showLogin();
    });

    $("refreshBtn").addEventListener("click", async () => {
      try { await loadAll(); } catch (err) { showLogin(err.message); }
    });

    $("probeBtn").addEventListener("click", async () => {
      $("probeBtn").disabled = true;
      try {
        await api("/gateway-admin/reload", { method: "POST" });
        setNotice("已重载配置，并按冷却策略增量探测。");
      } finally {
        $("probeBtn").disabled = false;
      }
    });

    async function syncNewApi(button) {
      button.disabled = true;
      try {
        const result = await api("/gateway-admin/sync-newapi", { method: "POST" });
        setNotice("已同步 New API 源池，并自动重载 Smart Gateway。");
        await loadAll();
      } finally {
        button.disabled = false;
      }
    }

    $("syncBtn").addEventListener("click", () => syncNewApi($("syncBtn")));
    $("syncBtnProviders").addEventListener("click", () => syncNewApi($("syncBtnProviders")));

    $("savePolicyBtn").addEventListener("click", async () => {
      $("savePolicyBtn").disabled = true;
      try {
        const updates = collectPolicyUpdates();
        const result = await api("/gateway-admin/api/source-policy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ providers: updates })
        });
        setNotice(`已保存 ${result.changed || 0} 个源池策略，并同步到 Smart Gateway。`);
        await loadAll();
      } finally {
        $("savePolicyBtn").disabled = false;
      }
    });

    $("probeBtnProviders").addEventListener("click", async () => {
      $("probeBtnProviders").disabled = true;
      try {
        await api("/gateway-admin/reload", { method: "POST" });
        setNotice("已重载配置，并按冷却策略增量探测。");
      } finally {
        $("probeBtnProviders").disabled = false;
      }
    });

    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
        document.querySelectorAll(".tabpane").forEach((x) => x.classList.add("hidden"));
        tab.classList.add("active");
        $("tab-" + tab.dataset.tab).classList.remove("hidden");
      });
    });

    document.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const input = $(btn.dataset.copy);
        await navigator.clipboard.writeText(input.value);
        btn.textContent = "已复制";
        setTimeout(() => btn.textContent = "复制", 1200);
      });
    });

    if (token()) {
      loadAll().catch((err) => showLogin(err.message));
    } else {
      showLogin();
    }
  </script>
</body>
</html>
"""
