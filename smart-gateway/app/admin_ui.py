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
      --bg: #f4f6f8;
      --panel: #ffffff;
      --text: #111827;
      --muted: #5f6b7a;
      --line: #d6dce5;
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
      padding: 8px 10px;
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
      padding: 9px 8px;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-weight: 700;
      background: #f8fafc;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    tbody tr:hover {
      background: #fbfcfe;
    }
    .tablewrap {
      max-height: 680px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .pager {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 8px;
      margin: 10px 0 16px;
      color: var(--muted);
      font-size: 13px;
    }
    .pager button {
      padding: 6px 10px;
    }
    .compact-input {
      min-width: 76px;
      padding: 6px 8px;
    }
    .provider-models {
      min-width: 220px;
      min-height: 70px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
    }
    .stack {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .muted {
      color: var(--muted);
    }
    .cell-main {
      font-weight: 700;
      margin-bottom: 3px;
    }
    .cell-sub {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .chiprow {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      max-width: 520px;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 2px 6px;
      background: #fff;
      white-space: nowrap;
      font-size: 12px;
    }
    .chip.ok {
      color: var(--ok);
      border-color: #abefc6;
      background: #ecfdf3;
    }
    .chip.warn {
      color: var(--warn);
      border-color: #fedf89;
      background: #fffaeb;
    }
    .chip.dark {
      color: #344054;
      border-color: #cbd5e1;
      background: #f8fafc;
    }
    .provider-selects select {
      padding: 6px 8px;
    }
    .provider-base textarea {
      min-height: 54px;
      font-size: 12px;
      line-height: 1.35;
    }
    .policy-hero {
      display: grid;
      grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
      gap: 14px;
      margin-bottom: 14px;
    }
    .policy-filter {
      display: grid;
      gap: 10px;
      align-content: start;
    }
    .route-board {
      display: grid;
      grid-template-columns: repeat(5, minmax(190px, 1fr));
      gap: 10px;
    }
    .route-lane {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfe;
      min-height: 120px;
      overflow: hidden;
    }
    .lane-head {
      padding: 10px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }
    .lane-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-weight: 800;
      font-size: 13px;
    }
    .lane-sub {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      margin-top: 4px;
    }
    .lane-body {
      padding: 8px;
      display: grid;
      gap: 8px;
    }
    .route-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 9px;
    }
    .route-card.top {
      border-color: #99f6e4;
      box-shadow: inset 3px 0 0 var(--accent);
    }
    .route-card-title {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      font-weight: 750;
      font-size: 13px;
      line-height: 1.35;
    }
    .route-meta {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
      margin-top: 5px;
    }
    .models-mini {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 7px;
    }
    .models-mini .chip {
      font-size: 11px;
      padding: 1px 5px;
      max-width: 180px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .policy-table th:nth-child(1), .policy-table td:nth-child(1) { min-width: 220px; }
    .policy-table th:nth-child(2), .policy-table td:nth-child(2) { min-width: 170px; }
    .policy-table th:nth-child(3), .policy-table td:nth-child(3) { min-width: 120px; }
    .policy-table th:nth-child(4), .policy-table td:nth-child(4) { min-width: 280px; }
    .policy-table th:nth-child(5), .policy-table td:nth-child(5) { min-width: 260px; }
    .policy-table th:nth-child(6), .policy-table td:nth-child(6) { min-width: 140px; }
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
    .help {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
      margin-top: 8px;
    }
    .help strong {
      color: var(--text);
      font-weight: 700;
    }
    @media (max-width: 920px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .provider-grid, .provider-wide { grid-template-columns: 1fr; }
      .policy-hero { grid-template-columns: 1fr; }
      .route-board { grid-template-columns: 1fr; }
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
        <button id="refreshBtn" title="只刷新当前管理页展示数据，不触发同步或探测">刷新</button>
        <button id="logoutBtn" title="清除当前浏览器保存的 Admin Token">退出</button>
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
            <button id="syncBtn" class="primary" title="从 New API 读取源池渠道；没有标签的新启用 default 渠道会自动纳入机会源池">同步 New API 源池</button>
            <button id="probeBtn" class="primary" title="重新加载本地配置，并按冷却策略只探测到期或变化的模型通道">重载配置并增量探测</button>
          </div>
          <div class="help">
            <strong>同步 New API 源池</strong>：把 New API 源池渠道同步成 Gateway 上游；新启用且未打标签的 default 渠道会自动纳入机会源池。
            <strong>重载配置并增量探测</strong>：只重载并启动后台健康探测，不改 New API 渠道；探测遵守冷却策略，结果稍后点刷新查看。
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
                <th>上游摘要</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody id="modelsBody"></tbody>
          </table>
        </div>
        <div id="modelsPager" class="pager"></div>
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
        <div id="matrixPager" class="pager"></div>
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
        <div id="logsPager" class="pager"></div>
      </section>

      <section id="tab-providers" class="tabpane hidden">
        <div class="row between" style="margin-bottom: 12px;">
          <div class="sub">源池策略会回写 New API 渠道。新增/删除上游、修改 key、模型权限、用户分组和订阅仍在 New API 管理。</div>
          <div class="row">
            <button id="savePolicyBtn" class="primary" title="保存当前页的启停、路由桶、成本层级、优先级、权重、Base URL 和声明模型">保存源池策略</button>
            <button id="syncBtnProviders" class="primary" title="从 New API 重新拉取源池渠道；没有标签的新启用 default 渠道会自动纳入机会源池">同步 New API 源池</button>
            <button id="probeBtnProviders" class="primary" title="重新加载本地配置，并按冷却策略启动后台增量探测">重载配置并增量探测</button>
          </div>
        </div>
        <div class="help">
          <strong>保存源池策略</strong>：把本页策略写回 New API 渠道标签并同步到 Gateway。
          <strong>同步 New API 源池</strong>：以 New API 渠道为准重新生成源池；新启用且未打标签的 default 渠道会自动纳入机会源池。
          <strong>重载配置并增量探测</strong>：不保存页面改动，只让 Gateway 重新读取配置并后台检测到期通道。
        </div>
        <div class="policy-hero">
          <div class="panel policy-filter">
            <h2>路由视图</h2>
            <div class="notice">同模型同策略层级内，先用最高优先级；最高优先级内再按权重分流。付费兜底永远最后。</div>
            <label for="modelFilter">按模型查看实际可走上游</label>
            <input id="modelFilter" list="modelOptions" placeholder="输入或选择模型；留空显示全部启用上游">
            <datalist id="modelOptions"></datalist>
            <div id="routeHint" class="help"></div>
          </div>
          <div id="routeBoard" class="route-board"></div>
        </div>
        <div class="notice">维护流程：New API 录入真实上游和 key；这里调整启停、策略层级、成本类型、优先级、权重和声明模型。保存后会自动写回 New API 渠道标签并同步 Smart Gateway。</div>
        <div class="tablewrap">
          <table class="policy-table">
            <thead>
              <tr>
                <th>上游</th>
                <th>策略层级</th>
                <th>优先/权重</th>
                <th>Base URL</th>
                <th>模型</th>
                <th>健康</th>
              </tr>
            </thead>
            <tbody id="providersBody"></tbody>
          </table>
        </div>
        <div id="providersPager" class="pager"></div>
      </section>
    </section>
  </main>

  <script>
    const tokenKey = "ai-smart-gateway-admin-token";
    let state = null;
    let providers = [];
    let logsData = { logs: [] };
    let providerDrafts = {};
    const pageSize = 25;
    const pages = { models: 1, matrix: 1, logs: 1, providers: 1 };

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

    const editableRoutes = [
      { value: "primary", label: "1 主力优先", short: "主力", desc: "正常首选，适合稳定且希望优先消耗的上游" },
      { value: "backup", label: "2 备份补位", short: "备份", desc: "主力没有健康通道时使用" },
      { value: "opportunistic", label: "3 机会利用", short: "机会", desc: "不稳定或临时上游，默认排在备份之后" },
      { value: "other", label: "4 低优先其他", short: "其他", desc: "特殊来源或暂不明确策略的上游" },
      { value: "paid_fallback", label: "5 付费兜底", short: "付费兜底", desc: "所有非付费路径不可用后才使用" }
    ];

    const runtimeRoutes = [
      { value: "explore", label: "自动探索", short: "探索", desc: "系统小概率试用待验证来源" },
      { value: "probe_retry", label: "探测重试", short: "重试", desc: "Responses 特定错误的自动重试桶" },
      { value: "shadow", label: "影子验证", short: "影子", desc: "非健康或待验证来源，不作为常规首选" }
    ];

    const routeMeta = Object.fromEntries([...editableRoutes, ...runtimeRoutes].map((item, index) => [item.value, { ...item, index }]));

    function routeLabel(value) {
      return routeMeta[value]?.short || value || "";
    }

    function costLabel(value, fallbackOnly = false) {
      const label = ({
        free: "免费",
        metered: "计量",
        paid: "付费"
      })[value] || value || "";
      return fallbackOnly ? `${label} 仅兜底` : label;
    }

    const routeOrder = {
      explore: -1,
      primary: 0,
      backup: 1,
      opportunistic: 2,
      other: 3,
      probe_retry: 4,
      shadow: 5,
      paid_fallback: 6
    };

    const costOrder = {
      free: 0,
      metered: 1,
      paid: 2,
      unknown: 3
    };

    function compareText(a, b) {
      return String(a || "").localeCompare(String(b || ""));
    }

    function paginate(name, items) {
      const total = items.length;
      const totalPages = Math.max(1, Math.ceil(total / pageSize));
      pages[name] = Math.min(Math.max(1, pages[name] || 1), totalPages);
      const start = (pages[name] - 1) * pageSize;
      return { items: items.slice(start, start + pageSize), total, totalPages };
    }

    function renderPager(name, total, totalPages) {
      const el = $(name + "Pager");
      if (!el) return;
      const page = pages[name] || 1;
      el.innerHTML = `
        <span>第 ${page} / ${totalPages} 页，共 ${total} 条</span>
        <button data-page="${name}" data-dir="-1" ${page <= 1 ? "disabled" : ""}>上一页</button>
        <button data-page="${name}" data-dir="1" ${page >= totalPages ? "disabled" : ""}>下一页</button>
      `;
    }

    function healthyModelProviders(model) {
      const items = [];
      for (const kind of ["chat", "responses"]) {
        const group = (state?.health?.[kind] || {})[model] || {};
        for (const item of Object.values(group)) {
          if (!item.healthy) continue;
          items.push({
            kind,
            provider_id: item.provider_id || "",
            provider: item.provider_name || item.provider_id || "",
            actual_model: item.actual_model || "",
            route_group: item.route_group || "",
            cost_tier: item.cost_tier || "",
            priority: item.priority ?? 0,
            weight: item.weight ?? 0,
            latency_ms: item.latency_ms
          });
        }
      }
      return items.sort((a, b) =>
        (routeOrder[a.route_group] ?? 99) - (routeOrder[b.route_group] ?? 99) ||
        Number(b.priority) - Number(a.priority) ||
        Number(b.weight) - Number(a.weight) ||
        Number(a.latency_ms ?? 999999) - Number(b.latency_ms ?? 999999) ||
        compareText(a.provider, b.provider)
      );
    }

    function providerHealthyModelDetails(providerId, selectedModel = "") {
      const items = [];
      for (const kind of ["chat", "responses"]) {
        const health = state?.health?.[kind] || {};
        for (const model of Object.keys(health)) {
          if (selectedModel && model !== selectedModel) continue;
          for (const item of Object.values(health[model] || {})) {
            if (item.healthy && item.provider_id === providerId) {
              items.push({ model, kind, item });
            }
          }
        }
      }
      return items.sort((a, b) =>
        compareText(a.model, b.model) ||
        compareText(a.kind, b.kind)
      );
    }

    function enabledProviderRows() {
      syncVisibleProviderDrafts();
      return providers
        .filter((p) => {
          const policy = p.editable_policy || {};
          return String(providerValue(p, "enabled", String((policy.enabled ?? p.enabled) !== false))) === "true";
        })
        .map((p) => {
          const policy = p.editable_policy || {};
          const route = providerValue(p, "route_group", policy.route_group || p.route_group || "primary");
          const cost = providerValue(p, "cost_tier", policy.cost_tier || p.cost_tier || "free");
          const fallback = String(providerValue(p, "fallback_only", String((policy.fallback_only ?? p.fallback_only) === true))) === "true" || route === "paid_fallback" || cost === "paid";
          const runtime = p.runtime || {};
          return {
            provider: p,
            route_group: fallback ? "paid_fallback" : route,
            display_route: route,
            cost_tier: cost,
            fallback_only: fallback,
            priority: Number(providerValue(p, "priority", policy.priority ?? p.priority ?? 0) || 0),
            weight: Number(providerValue(p, "weight", policy.weight ?? p.weight ?? 0) || 0),
            healthy: Number(runtime.healthy ?? 0),
            unhealthy: Number(runtime.unhealthy ?? 0),
            avg_latency_ms: runtime.avg_latency_ms
          };
        });
    }

    function candidateRowsForModel(model) {
      if (!model) return [];
      const rows = [];
      for (const item of healthyModelProviders(model)) {
        const provider = providers.find((p) => p.id === item.provider_id) || providers.find((p) => p.name === item.provider);
        rows.push({
          provider,
          provider_name: item.provider,
          route_group: item.route_group || "primary",
          cost_tier: item.cost_tier || "",
          priority: Number(item.priority || 0),
          weight: Number(item.weight || 0),
          latency_ms: item.latency_ms,
          kind: item.kind,
          actual_model: item.actual_model
        });
      }
      return rows;
    }

    function sortedRouteRows(rows) {
      return [...rows].sort((a, b) =>
        (routeOrder[a.route_group] ?? 99) - (routeOrder[b.route_group] ?? 99) ||
        Number(b.priority) - Number(a.priority) ||
        Number(b.weight) - Number(a.weight) ||
        Number(a.latency_ms ?? a.avg_latency_ms ?? 999999) - Number(b.latency_ms ?? b.avg_latency_ms ?? 999999) ||
        compareText(a.provider?.name || a.provider_name || a.provider?.id, b.provider?.name || b.provider_name || b.provider?.id)
      );
    }

    function modelProviderSummary(model) {
      const upstreams = healthyModelProviders(model);
      if (!upstreams.length) return '<span class="muted">无健康上游</span>';
      const byProvider = new Map();
      for (const item of upstreams) {
        const current = byProvider.get(item.provider);
        if (!current || Number(item.priority) > Number(current.priority) || Number(item.weight) > Number(current.weight)) {
          byProvider.set(item.provider, item);
        }
      }
      const items = Array.from(byProvider.values()).sort((a, b) =>
        Number(b.priority) - Number(a.priority) ||
        Number(b.weight) - Number(a.weight) ||
        compareText(a.provider, b.provider)
      );
      return `
        <div class="chiprow">
          ${items.map((item) => `<span class="chip ok">${escapeHtml(item.provider)} W${item.weight}</span>`).join("")}
        </div>
      `;
    }

    function providerHealthyModels(providerId) {
      const models = new Set();
      for (const kind of ["chat", "responses"]) {
        const health = state?.health?.[kind] || {};
        for (const model of Object.keys(health)) {
          for (const item of Object.values(health[model] || {})) {
            if (item.healthy && item.provider_id === providerId) {
              models.add(`${model} (${kind})`);
            }
          }
        }
      }
      return Array.from(models).sort();
    }

    function updateModelOptions() {
      const models = new Set((state?.models || []).map((m) => m.id).filter(Boolean));
      $("modelOptions").innerHTML = Array.from(models).sort().map((model) => `<option value="${escapeHtml(model)}"></option>`).join("");
    }

    function smallModelChips(items, limit = 8) {
      const shown = items.slice(0, limit);
      const rest = items.length - shown.length;
      return `
        <div class="models-mini">
          ${shown.map((entry) => `<span class="chip ok mono" title="${escapeHtml(entry.model + " / " + entry.kind)}">${escapeHtml(entry.model)} ${entry.kind}</span>`).join("")}
          ${rest > 0 ? `<span class="chip dark">+${rest}</span>` : ""}
        </div>
      `;
    }

    function routeCard(row, selectedModel, isTop) {
      const provider = row.provider || {};
      const name = row.provider_name || provider.name || provider.id || "unknown";
      const latency = row.latency_ms ?? row.avg_latency_ms;
      const models = selectedModel
        ? [{ model: selectedModel, kind: row.kind || "" }]
        : providerHealthyModelDetails(provider.id || "", "");
      return `
        <div class="route-card ${isTop ? "top" : ""}">
          <div class="route-card-title">
            <span>${escapeHtml(name)}</span>
            <span class="pill ${row.fallback_only || row.cost_tier === "paid" ? "warn" : "ok"}">${escapeHtml(costLabel(row.cost_tier, row.fallback_only))}</span>
          </div>
          <div class="route-meta">
            优先级 ${row.priority} / 权重 ${row.weight}${latency == null ? "" : ` / ${latency} ms`}<br>
            ${selectedModel && row.actual_model ? `实际模型 <span class="mono">${escapeHtml(row.actual_model)}</span>` : `健康 ${row.healthy ?? models.length} / 异常 ${row.unhealthy ?? 0}`}
          </div>
          ${smallModelChips(models)}
        </div>
      `;
    }

    function renderRouteBoard() {
      const selectedModel = $("modelFilter")?.value.trim() || "";
      const sourceRows = selectedModel ? candidateRowsForModel(selectedModel) : enabledProviderRows();
      const rows = sortedRouteRows(sourceRows);
      const groups = editableRoutes.map((route) => {
        const items = rows.filter((row) => row.route_group === route.value);
        return { ...route, items };
      });
      const firstNonEmpty = groups.find((group) => group.items.length > 0);
      $("routeHint").innerHTML = selectedModel
        ? `当前模型：<span class="mono">${escapeHtml(selectedModel)}</span>，共 ${rows.length} 条健康可用上游。`
        : `显示所有启用上游；选择模型后会按该模型真实健康通道排序。`;
      $("routeBoard").innerHTML = groups.map((group) => {
        const topPriority = Math.max(-1, ...group.items.map((item) => Number(item.priority || 0)));
        const cardHtml = group.items.length
          ? group.items.map((row) => routeCard(row, selectedModel, group === firstNonEmpty && Number(row.priority || 0) === topPriority)).join("")
          : '<div class="muted">暂无启用健康上游</div>';
        return `
          <section class="route-lane">
            <div class="lane-head">
              <div class="lane-title"><span>${escapeHtml(group.label)}</span><span class="pill ${group.items.length ? "ok" : "bad"}">${group.items.length}</span></div>
              <div class="lane-sub">${escapeHtml(group.desc)}</div>
            </div>
            <div class="lane-body">${cardHtml}</div>
          </section>
        `;
      }).join("");
    }

    function providerKey(p) {
      return String(p.new_api_channel_id || p.editable_policy?.id || p.id || "");
    }

    function providerValue(p, field, fallback) {
      const draft = providerDrafts[providerKey(p)] || {};
      return draft[field] ?? fallback;
    }

    function syncVisibleProviderDrafts() {
      document.querySelectorAll(".provider").forEach((node) => {
        const get = (field) => node.querySelector(`[data-field="${field}"]`)?.value || "";
        const id = get("id");
        if (!id) return;
        providerDrafts[id] = {
          id,
          enabled: get("enabled"),
          route_group: get("route_group"),
          cost_tier: get("cost_tier"),
          fallback_only: get("fallback_only"),
          priority: get("priority"),
          weight: get("weight"),
          base_url: get("base_url"),
          models: get("models")
        };
      });
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
      const ordered = [...data.models].sort((a, b) =>
        (b.chat_ok + b.responses_ok) - (a.chat_ok + a.responses_ok) ||
        compareText(a.id, b.id)
      );
      const page = paginate("models", ordered);
      $("modelsBody").innerHTML = page.items.map((m) => {
        return `
        <tr>
          <td class="mono">${m.id}</td>
          <td>${m.chat_ok}</td>
          <td>${m.responses_ok}</td>
          <td>${modelProviderSummary(m.id)}</td>
          <td>${statusPill(m.chat_ok > 0 || m.responses_ok > 0, m.chat_ok === 0 || m.responses_ok === 0)}</td>
        </tr>
      `;
      }).join("");
      renderPager("models", page.total, page.totalPages);
    }

    function renderMatrix(data) {
      const rows = [];
      const items = [];
      for (const kind of ["chat", "responses"]) {
        const group = data.health[kind] || {};
        for (const model of Object.keys(group).sort()) {
          for (const item of Object.values(group[model])) {
            items.push({ kind, model, item });
          }
        }
      }
      items.sort((a, b) =>
        Number(b.item.checked_at || 0) - Number(a.item.checked_at || 0) ||
        Number(a.item.next_probe_at || 0) - Number(b.item.next_probe_at || 0) ||
        compareText(a.kind, b.kind) ||
        compareText(a.model, b.model) ||
        compareText(a.item.provider_name || a.item.provider_id, b.item.provider_name || b.item.provider_id)
      );
      const page = paginate("matrix", items);
      for (const row of page.items) {
        const kind = row.kind;
        const model = row.model;
        const item = row.item;
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
      $("matrixBody").innerHTML = rows.join("");
      renderPager("matrix", page.total, page.totalPages);
    }

    function renderLogs(data) {
      const page = paginate("logs", data.logs || []);
      $("logsBody").innerHTML = page.items.map((row) => {
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
      renderPager("logs", page.total, page.totalPages);
    }

    function providerTemplate(p) {
      const policy = p.editable_policy || {};
      const key = providerKey(p);
      const models = providerValue(p, "models", policy.models || (p.declared_models || []).join(","));
      const runtime = p.runtime || {};
      const baseUrls = (policy.base_urls || p.base_urls || [policy.base_url || p.base_url || ""]).join("\\n");
      const enabledValue = String(providerValue(p, "enabled", String((policy.enabled ?? p.enabled) !== false)));
      const routeValue = providerValue(p, "route_group", policy.route_group || p.route_group);
      const costValue = providerValue(p, "cost_tier", policy.cost_tier || p.cost_tier);
      const fallbackValue = String(providerValue(p, "fallback_only", String((policy.fallback_only ?? p.fallback_only) === true)));
      const priorityValue = providerValue(p, "priority", policy.priority ?? p.priority ?? 0);
      const weightValue = providerValue(p, "weight", policy.weight ?? p.weight ?? 100);
      const baseUrlValue = providerValue(p, "base_url", policy.base_url || p.base_url || "");
      const healthyModels = providerHealthyModels(p.id);
      const routeOptions = editableRoutes.map((route) => option(route.value, route.label, routeValue)).join("");
      return `
        <tr class="provider" data-index="${escapeHtml(p.id || "")}">
          <td>
            <div class="stack">
              <div class="cell-main">${escapeHtml(p.name || p.id || "provider")}</div>
              <div class="cell-sub mono">${escapeHtml(p.id || "")}</div>
              <div class="cell-sub">${escapeHtml(p.api_key_preview || "")}</div>
              <div>${p.enabled !== false ? '<span class="pill ok">启用</span>' : '<span class="pill bad">停用</span>'}</div>
              <input type="hidden" data-field="id" value="${escapeHtml(key)}">
            </div>
          </td>
          <td>
            <div class="stack provider-selects">
              <select data-field="enabled">${option("true", "启用", enabledValue)}${option("false", "停用", enabledValue)}</select>
              <select data-field="route_group">${routeOptions}</select>
              <select data-field="cost_tier">${option("free", "免费", costValue)}${option("metered", "计量", costValue)}${option("paid", "付费", costValue)}${option("unknown", "未知", costValue)}</select>
              <select data-field="fallback_only">${option("false", "非仅兜底", fallbackValue)}${option("true", "仅兜底", fallbackValue)}</select>
            </div>
          </td>
          <td>
            <div class="stack">
              <input class="compact-input" data-field="priority" type="number" min="0" max="10000" value="${escapeHtml(priorityValue)}">
              <input class="compact-input" data-field="weight" type="number" min="1" max="10000" value="${escapeHtml(weightValue)}">
            </div>
          </td>
          <td>
            <div class="stack provider-base">
              <input data-field="base_url" value="${escapeHtml(baseUrlValue)}">
              <textarea readonly>${escapeHtml(baseUrls)}</textarea>
            </div>
          </td>
          <td>
            <div class="stack">
              <label>声明模型</label>
              <textarea class="provider-models" data-field="models">${escapeHtml(models)}</textarea>
              <label>实际健康模型</label>
              <div class="chiprow">${healthyModels.length ? healthyModels.slice(0, 18).map((m) => `<span class="chip ok mono">${escapeHtml(m)}</span>`).join("") + (healthyModels.length > 18 ? `<span class="chip dark">+${healthyModels.length - 18}</span>` : "") : '<span class="muted">暂无健康模型</span>'}</div>
            </div>
          </td>
          <td>
            <div class="stack">
              <span>健康 ${runtime.healthy ?? 0}</span>
              <span>异常 ${runtime.unhealthy ?? 0}</span>
              <span>${runtime.avg_latency_ms == null ? "" : runtime.avg_latency_ms + " ms"}</span>
              <span class="mono">${escapeHtml(policy.tag || p.tag || "")}</span>
            </div>
          </td>
        </tr>
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
      const ordered = [...providers].sort((a, b) => {
        const ap = a.editable_policy || {};
        const bp = b.editable_policy || {};
        const aEnabled = (ap.enabled ?? a.enabled) !== false;
        const bEnabled = (bp.enabled ?? b.enabled) !== false;
        const aFallback = (ap.fallback_only ?? a.fallback_only) === true;
        const bFallback = (bp.fallback_only ?? b.fallback_only) === true;
        const ar = a.runtime || {};
        const br = b.runtime || {};
        return Number(bEnabled) - Number(aEnabled) ||
          (routeOrder[ap.route_group || a.route_group] ?? 99) - (routeOrder[bp.route_group || b.route_group] ?? 99) ||
          Number(aFallback) - Number(bFallback) ||
          (costOrder[ap.cost_tier || a.cost_tier] ?? 99) - (costOrder[bp.cost_tier || b.cost_tier] ?? 99) ||
          Number(bp.priority ?? b.priority ?? 0) - Number(ap.priority ?? a.priority ?? 0) ||
          Number(bp.weight ?? b.weight ?? 0) - Number(ap.weight ?? a.weight ?? 0) ||
          Number(br.healthy ?? 0) - Number(ar.healthy ?? 0) ||
          Number(ar.unhealthy ?? 0) - Number(br.unhealthy ?? 0) ||
          compareText(a.name || a.id, b.name || b.id);
      });
      const page = paginate("providers", ordered);
      $("providersBody").innerHTML = page.items.map(providerTemplate).join("");
      renderPager("providers", page.total, page.totalPages);
    }

    function collectPolicyUpdates() {
      syncVisibleProviderDrafts();
      return providers.map((provider) => {
        const policy = provider.editable_policy || {};
        const key = providerKey(provider);
        const draft = providerDrafts[key] || {};
        const get = (field, fallback) => draft[field] ?? fallback ?? "";
        return {
          id: Number(key),
          enabled: String(get("enabled", String((policy.enabled ?? provider.enabled) !== false))) === "true",
          route_group: get("route_group", policy.route_group || provider.route_group),
          cost_tier: get("cost_tier", policy.cost_tier || provider.cost_tier),
          fallback_only: String(get("fallback_only", String((policy.fallback_only ?? provider.fallback_only) === true))) === "true",
          priority: Number(get("priority", policy.priority ?? provider.priority ?? 0) || 0),
          weight: Number(get("weight", policy.weight ?? provider.weight ?? 100) || 100),
          base_url: get("base_url", policy.base_url || provider.base_url || ""),
          models: get("models", policy.models || (provider.declared_models || []).join(","))
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
      providerDrafts = {};
      logsData = logs;
      renderOverview(overview);
      renderModels(overview);
      renderMatrix(overview);
      renderLogs(logs);
      renderProviders();
      updateModelOptions();
      renderRouteBoard();
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
        setNotice("已重载配置，并启动后台增量探测。探测遵守冷却策略，稍后点刷新查看最新结果。");
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
        setNotice("已重载配置，并启动后台增量探测。探测遵守冷却策略，稍后点刷新查看最新结果。");
      } finally {
        $("probeBtnProviders").disabled = false;
      }
    });

    document.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-page]");
      if (!btn) return;
      const name = btn.dataset.page;
      if (name === "providers") syncVisibleProviderDrafts();
      pages[name] = (pages[name] || 1) + Number(btn.dataset.dir || 0);
      if (name === "models") renderModels(state);
      if (name === "matrix") renderMatrix(state);
      if (name === "logs") renderLogs(logsData);
      if (name === "providers") {
        renderProviders();
        renderRouteBoard();
      }
    });

    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
        document.querySelectorAll(".tabpane").forEach((x) => x.classList.add("hidden"));
        tab.classList.add("active");
        $("tab-" + tab.dataset.tab).classList.remove("hidden");
        if (tab.dataset.tab === "providers") renderRouteBoard();
      });
    });

    $("modelFilter").addEventListener("input", renderRouteBoard);

    document.addEventListener("input", (event) => {
      if (!event.target.closest("#tab-providers")) return;
      if (!event.target.matches("input, textarea, select")) return;
      syncVisibleProviderDrafts();
      renderRouteBoard();
    });

    document.addEventListener("change", (event) => {
      if (!event.target.closest("#tab-providers")) return;
      if (!event.target.matches("input, textarea, select")) return;
      syncVisibleProviderDrafts();
      renderRouteBoard();
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
