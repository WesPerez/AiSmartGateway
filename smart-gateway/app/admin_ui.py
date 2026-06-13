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
      width: min(1760px, calc(100vw - 32px));
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
    .upstream-toolbar {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .upstream-filters {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 0 0 auto;
    }
    .upstream-filters input {
      width: 180px;
    }
    .availability-toolbar {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 12px;
      align-items: center;
      margin-bottom: 12px;
    }
    .segmented {
      display: inline-flex;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
      width: fit-content;
    }
    .segmented button {
      border: 0;
      border-right: 1px solid var(--line);
      border-radius: 0;
      padding: 8px 12px;
      white-space: nowrap;
    }
    .segmented button:last-child {
      border-right: 0;
    }
    .segmented button.active {
      background: var(--accent);
      color: #fff;
    }
    .availability-filters {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }
    .availability-filters input {
      width: 190px;
    }
    .matrix-toolbar {
      display: grid;
      grid-template-columns: auto auto minmax(0, 1fr);
      gap: 10px;
      align-items: center;
      margin-bottom: 12px;
    }
    .matrix-filters {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }
    .matrix-filters input {
      width: 190px;
    }
    .logs-toolbar {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 10px;
      align-items: center;
      margin-bottom: 12px;
    }
    .logs-filters {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }
    .logs-filters input,
    .logs-filters select {
      width: 153px;
      flex: 0 1 153px;
    }
    .logs-filters .wide-filter {
      width: 207px;
      flex-basis: 207px;
    }
    .filter-count {
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .availability-summary {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      margin-bottom: 10px;
    }
    .availability-table,
    .upstream-availability-table {
      table-layout: fixed;
    }
    .availability-table { min-width: 1520px; }
    .availability-table th:nth-child(1), .availability-table td:nth-child(1) { width: 190px; }
    .availability-table th:nth-child(2), .availability-table td:nth-child(2) { width: 140px; }
    .availability-table th:nth-child(3), .availability-table td:nth-child(3) { width: 300px; }
    .availability-table th:nth-child(4), .availability-table td:nth-child(4) { width: 260px; }
    .availability-table th:nth-child(5), .availability-table td:nth-child(5) { width: 110px; }
    .availability-table th:nth-child(6), .availability-table td:nth-child(6) { width: 170px; }
    .availability-table th:nth-child(7), .availability-table td:nth-child(7) { width: 170px; }
    .availability-table th:nth-child(8), .availability-table td:nth-child(8) { width: 180px; }
    .upstream-availability-table { min-width: 1760px; }
    .upstream-availability-table th:nth-child(1), .upstream-availability-table td:nth-child(1) { width: 240px; }
    .upstream-availability-table th:nth-child(2), .upstream-availability-table td:nth-child(2) { width: 130px; }
    .upstream-availability-table th:nth-child(3), .upstream-availability-table td:nth-child(3) { width: 210px; }
    .upstream-availability-table th:nth-child(4), .upstream-availability-table td:nth-child(4) { width: 250px; }
    .upstream-availability-table th:nth-child(5), .upstream-availability-table td:nth-child(5) { width: 105px; }
    .upstream-availability-table th:nth-child(6), .upstream-availability-table td:nth-child(6) { width: 95px; }
    .upstream-availability-table th:nth-child(7), .upstream-availability-table td:nth-child(7) { width: 165px; }
    .upstream-availability-table th:nth-child(8), .upstream-availability-table td:nth-child(8) { width: 165px; }
    .upstream-availability-table th:nth-child(9), .upstream-availability-table td:nth-child(9) { width: 230px; }
    .upstream-availability-table th:nth-child(10), .upstream-availability-table td:nth-child(10) { width: 170px; }
    .logs-table {
      width: 100%;
      min-width: 0;
      table-layout: fixed;
    }
    .logs-table th:nth-child(1), .logs-table td:nth-child(1) { width: 17%; }
    .logs-table th:nth-child(2), .logs-table td:nth-child(2) { width: 13%; }
    .logs-table th:nth-child(3), .logs-table td:nth-child(3) { width: 18%; }
    .logs-table th:nth-child(4), .logs-table td:nth-child(4) { width: 21%; }
    .logs-table th:nth-child(5), .logs-table td:nth-child(5) { width: 10%; }
    .logs-table th:nth-child(6), .logs-table td:nth-child(6) { width: 21%; }
    .logs-table td {
      height: 58px;
      padding-top: 7px;
      padding-bottom: 7px;
      vertical-align: middle;
    }
    .logs-tablewrap {
      max-height: none;
      overflow: hidden;
    }
    .logs-table .log-cell {
      display: flex;
      min-width: 0;
      max-height: 46px;
      flex-direction: column;
      justify-content: center;
      gap: 2px;
      overflow: hidden;
    }
    .logs-table .cell-main,
    .logs-table .cell-sub,
    .logs-table .log-line {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .logs-table .chiprow {
      max-width: 100%;
      flex-wrap: nowrap;
      overflow: hidden;
    }
    .logs-table .chip {
      max-width: 110px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .matrix-helpbar {
      display: grid;
      grid-template-columns: minmax(220px, auto) minmax(0, 1fr);
      gap: 12px;
      align-items: start;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      margin-bottom: 12px;
    }
    .matrix-help-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 800;
      line-height: 1.4;
    }
    .matrix-help-summary {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }
    .help-popover {
      position: relative;
      display: inline-flex;
      align-items: center;
    }
    .help-dot {
      width: 20px;
      height: 20px;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #f8fafc;
      color: var(--accent-dark);
      font-weight: 900;
      font-size: 12px;
      cursor: help;
    }
    .help-popover-panel {
      position: absolute;
      left: 0;
      top: calc(100% + 8px);
      width: min(680px, calc(100vw - 48px));
      max-height: min(70vh, 620px);
      overflow: auto;
      opacity: 0;
      visibility: hidden;
      transform: translateY(-4px);
      transition: opacity .12s ease, transform .12s ease;
      z-index: 20;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      box-shadow: 0 16px 32px rgba(15, 23, 42, .14);
      padding: 12px;
      color: var(--text);
      font-size: 12px;
      line-height: 1.6;
    }
    .help-popover:hover .help-popover-panel,
    .help-popover:focus-within .help-popover-panel {
      opacity: 1;
      visibility: visible;
      transform: translateY(0);
    }
    .help-popover-panel h3 {
      margin: 0 0 8px;
      font-size: 13px;
    }
    .policy-list {
      display: grid;
      gap: 6px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .policy-list li {
      display: grid;
      grid-template-columns: 140px minmax(0, 1fr);
      gap: 8px;
    }
    .policy-key {
      color: var(--muted);
      font-weight: 700;
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
    .pager select {
      width: auto;
      padding: 6px 8px;
    }
    .inline-toggle {
      display: inline-flex;
      align-items: center;
      margin: 0;
    }
    .inline-toggle input {
      width: auto;
      margin: 0;
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
    .policy-hero {
      display: grid;
      grid-template-columns: minmax(280px, 380px) minmax(0, 1fr);
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
      grid-template-columns: repeat(5, minmax(220px, 1fr));
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
      max-width: 220px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .model-kind {
      color: var(--muted);
      font-size: 10px;
      margin-left: 4px;
      font-family: ui-sans-serif, system-ui, sans-serif;
    }
    .wide-table {
      max-height: 760px;
    }
    .policy-table th:nth-child(1), .policy-table td:nth-child(1) { min-width: 240px; }
    .policy-table th:nth-child(2), .policy-table td:nth-child(2) { min-width: 190px; }
    .policy-table th:nth-child(3), .policy-table td:nth-child(3) { min-width: 120px; }
    .policy-table th:nth-child(4), .policy-table td:nth-child(4) { min-width: 340px; }
    .policy-table th:nth-child(5), .policy-table td:nth-child(5) { min-width: 320px; }
    .policy-table th:nth-child(6), .policy-table td:nth-child(6) { min-width: 360px; }
    .policy-table th:nth-child(7), .policy-table td:nth-child(7) { min-width: 140px; }
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
      .matrix-helpbar { grid-template-columns: 1fr; }
      .availability-toolbar { grid-template-columns: 1fr; }
      .availability-filters { justify-content: flex-start; }
      .matrix-toolbar { grid-template-columns: 1fr; }
      .matrix-filters { justify-content: flex-start; }
      .logs-toolbar { grid-template-columns: 1fr; }
      .logs-filters { justify-content: flex-start; }
      .help-popover-panel { left: auto; right: 0; }
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
        <div class="sub">New API 后置智能路由层：运行观测、模型可用性、探测矩阵、最终流向和兜底策略</div>
      </div>
      <div class="row">
        <label class="inline-toggle" title="每 10 秒自动刷新管理页数据">
          <input id="autoRefresh" type="checkbox">
          <span>自动刷新 <span id="autoRefreshCountdown"></span></span>
        </label>
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
        <button class="tab active" data-tab="logs">路由日志</button>
        <button class="tab" data-tab="overview">运行概览</button>
        <button class="tab" data-tab="models">模型可用性</button>
        <button class="tab" data-tab="matrix">探测矩阵</button>
        <button class="tab" data-tab="providers">源池策略</button>
      </div>

      <section id="tab-logs" class="tabpane">
        <div class="logs-toolbar">
          <div class="segmented" role="group" aria-label="路由日志结果筛选">
            <button type="button" class="active" data-log-success="all">全部结果</button>
            <button type="button" data-log-success="success">成功</button>
            <button type="button" data-log-success="failure">失败</button>
          </div>
          <div class="logs-filters">
            <input id="logSearchFilter" class="wide-filter" placeholder="搜索请求ID / 模型 / 上游 / 错误">
            <input id="logModelFilter" list="upstreamModelOptions" placeholder="筛选模型">
            <input id="logUpstreamFilter" list="upstreamOptions" placeholder="筛选上游">
            <select id="logKindFilter" title="客户端接口">
              <option value="all">全部接口</option>
              <option value="chat">Chat</option>
              <option value="responses">Responses</option>
            </select>
            <select id="logStreamFilter" title="流式模式">
              <option value="all">全部模式</option>
              <option value="stream">流式</option>
              <option value="nonstream">非流式</option>
            </select>
            <select id="logAdapterFilter" title="格式转换">
              <option value="all">全部转换</option>
              <option value="native">原生</option>
              <option value="adapted">跨格式</option>
              <option value="codex_responses_to_chat">Codex 兼容</option>
              <option value="responses_to_chat">Responses -> Chat</option>
              <option value="chat_to_responses">Chat -> Responses</option>
            </select>
            <select id="logShapeFilter" title="请求形态">
              <option value="all">全部形态</option>
              <option value="image">带图片</option>
              <option value="tools">带工具</option>
              <option value="client_invalid_input">输入无效</option>
            </select>
            <input id="logErrorFilter" list="logErrorOptions" placeholder="错误类型">
            <datalist id="logErrorOptions"></datalist>
            <span id="logsFilterCount" class="filter-count">-</span>
            <button id="logsClearFilters" type="button">清空</button>
          </div>
        </div>
        <div class="tablewrap logs-tablewrap">
          <table class="logs-table">
            <thead>
              <tr>
                <th>请求</th>
                <th>接口 / 状态</th>
                <th>模型</th>
                <th>流向</th>
                <th>耗时 / Token</th>
                <th>详情</th>
              </tr>
            </thead>
            <tbody id="logsBody"></tbody>
          </table>
        </div>
        <div id="logsPager" class="pager"></div>
      </section>

      <section id="tab-overview" class="tabpane hidden">
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
        <div class="availability-toolbar">
          <div class="segmented" role="tablist" aria-label="模型可用性视图">
            <button type="button" class="active" data-availability-view="model">按模型</button>
            <button type="button" data-availability-view="upstream">按上游</button>
          </div>
          <div class="availability-filters">
            <input id="availabilityModelFilter" list="upstreamModelOptions" placeholder="输入或选择模型">
            <input id="availabilityUpstreamFilter" list="upstreamOptions" placeholder="输入或选择上游">
            <label class="inline-toggle" title="默认只显示至少一个接口健康的模型/上游；勾选后显示异常和无健康项。">
              <input id="showUnhealthyAvailability" type="checkbox" aria-label="显示异常和无健康项">
              <span>显示异常</span>
            </label>
          </div>
        </div>
        <datalist id="upstreamOptions"></datalist>
        <datalist id="upstreamModelOptions"></datalist>
        <div id="availabilityModelView">
          <div class="availability-summary">默认按对外模型汇总可用性；排障时切到“按上游”查看每个上游模型的检测、冷却和详情。</div>
          <div class="tablewrap wide-table">
            <table class="availability-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>接口健康</th>
                  <th>首选上游</th>
                  <th>备份/兜底</th>
                  <th>最低延迟</th>
                  <th>最近检测</th>
                  <th>下次探测</th>
                  <th>主要状态</th>
                </tr>
              </thead>
              <tbody id="modelsBody"></tbody>
            </table>
          </div>
          <div id="modelsPager" class="pager"></div>
        </div>
        <div id="availabilityUpstreamView" class="hidden">
          <div class="availability-summary">按上游展开模型明细，用于定位某个源池渠道贡献了哪些模型、哪些接口异常、当前处于什么冷却策略。</div>
          <div class="tablewrap wide-table">
            <table class="upstream-availability-table">
              <thead>
                <tr>
                  <th>上游</th>
                  <th>策略</th>
                  <th>模型</th>
                  <th>接口</th>
                  <th>状态</th>
                  <th>延迟</th>
                  <th>最近检测</th>
                  <th>下次探测</th>
                  <th>检测/冷却策略</th>
                  <th>详情</th>
                </tr>
              </thead>
              <tbody id="upstreamsBody"></tbody>
            </table>
          </div>
          <div id="upstreamsPager" class="pager"></div>
        </div>
      </section>

      <section id="tab-matrix" class="tabpane hidden">
        <div id="matrixPolicyHelp" class="matrix-helpbar"></div>
        <div class="matrix-toolbar">
          <div class="segmented" role="group" aria-label="接口类型筛选">
            <button type="button" class="active" data-matrix-kind="all">全部接口</button>
            <button type="button" data-matrix-kind="chat">Chat</button>
            <button type="button" data-matrix-kind="responses">Responses</button>
          </div>
          <div class="segmented" role="group" aria-label="健康状态筛选">
            <button type="button" class="active" data-matrix-status="all">全部状态</button>
            <button type="button" data-matrix-status="healthy">健康</button>
            <button type="button" data-matrix-status="unhealthy">不健康</button>
          </div>
          <div class="matrix-filters">
            <input id="matrixModelFilter" list="upstreamModelOptions" placeholder="筛选模型">
            <input id="matrixUpstreamFilter" list="upstreamOptions" placeholder="筛选上游">
            <span id="matrixFilterCount" class="filter-count">-</span>
            <button id="matrixClearFilters" type="button">清空</button>
          </div>
        </div>
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
                <th>新鲜度</th>
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

      <section id="tab-providers" class="tabpane hidden">
        <div class="row between" style="margin-bottom: 12px;">
          <div class="sub">源池策略会回写 New API 渠道。新增/删除上游、修改 key、模型权限、用户分组和订阅仍在 New API 管理。</div>
          <div class="row">
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
        <div class="notice">维护流程：New API 录入真实上游和 key；这里调整启停、策略层级、优先级、权重和声明模型。付费兜底只由策略层级“5 付费兜底”决定。</div>
        <div class="row" style="margin-bottom: 14px;">
          <button id="savePolicyBtn" class="primary" title="保存当前页的启停、路由桶、优先级、权重、Base URL 和声明模型">保存源池策略</button>
        </div>
        <div class="tablewrap">
          <table class="policy-table">
            <thead>
              <tr>
                <th>上游</th>
                <th>策略层级</th>
                <th>优先/权重</th>
                <th>Base URL</th>
                <th>声明模型</th>
                <th>实际健康模型</th>
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
    const autoRefreshKey = "ai-smart-gateway-auto-refresh";
    let state = null;
    let providers = [];
    let logsData = { logs: [] };
    let providerDrafts = {};
    let availabilityView = "model";
    let matrixKindFilter = "all";
    let matrixStatusFilter = "all";
    let logSuccessFilter = "all";
    const pageSizeOptions = [10, 25, 50, 100, 200];
    const pageSizes = { models: 10, matrix: 10, upstreams: 10, logs: 10, providers: 10 };
    const pages = { models: 1, matrix: 1, upstreams: 1, logs: 1, providers: 1 };

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

    function logStatusPill(success) {
      return `<span class="pill ${success ? "ok" : "bad"}">${success ? "成功" : "失败"}</span>`;
    }

    function formatTs(ts, empty = "") {
      return ts ? new Date(ts * 1000).toLocaleString() : empty;
    }

    function formatDuration(seconds) {
      if (seconds == null || seconds === "") return "";
      const value = Math.max(0, Number(seconds));
      if (value >= 86400) return `${Math.round(value / 86400)} 天`;
      if (value >= 3600) return `${Math.round(value / 3600)} 小时`;
      if (value >= 60) return `${Math.round(value / 60)} 分钟`;
      return `${value} 秒`;
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

    const routeOrder = {
      primary: 0,
      backup: 1,
      opportunistic: 2,
      other: 3,
      explore: 4,
      probe_retry: 5,
      shadow: 6,
      paid_fallback: 7
    };

    function compareText(a, b) {
      return String(a || "").localeCompare(String(b || ""));
    }

    function paginate(name, items) {
      const total = items.length;
      const size = pageSizes[name] || 25;
      const totalPages = Math.max(1, Math.ceil(total / size));
      pages[name] = Math.min(Math.max(1, pages[name] || 1), totalPages);
      const start = (pages[name] - 1) * size;
      return { items: items.slice(start, start + size), total, totalPages };
    }

    function renderPager(name, total, totalPages) {
      const el = $(name + "Pager");
      if (!el) return;
      const page = pages[name] || 1;
      el.innerHTML = `
        <span>第 ${page} / ${totalPages} 页，共 ${total} 条</span>
        <select data-page-size="${name}" title="每页条数">
          ${pageSizeOptions.map((size) => `<option value="${size}" ${Number(pageSizes[name] || 25) === size ? "selected" : ""}>${size} / 页</option>`).join("")}
        </select>
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
        compareModelId(a.model, b.model) ||
        compareText(a.kind, b.kind)
      );
    }

    function mergeModelKinds(items) {
      const byModel = new Map();
      for (const entry of items) {
        const row = byModel.get(entry.model) || { model: entry.model, kinds: new Set(), bestLatency: null };
        if (entry.kind) row.kinds.add(entry.kind);
        const latency = entry.item?.latency_ms;
        if (latency != null && (row.bestLatency == null || latency < row.bestLatency)) row.bestLatency = latency;
        byModel.set(entry.model, row);
      }
      return Array.from(byModel.values()).sort((a, b) => compareModelId(a.model, b.model));
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
          const fallback = route === "paid_fallback" || (policy.fallback_only ?? p.fallback_only) === true;
          const runtime = p.runtime || {};
          return {
            provider: p,
            route_group: fallback ? "paid_fallback" : route,
            display_route: route,
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
      const byProvider = new Map();
      for (const item of healthyModelProviders(model)) {
        const provider = providers.find((p) => p.id === item.provider_id) || providers.find((p) => p.name === item.provider);
        const key = item.provider_id || item.provider;
        const existing = byProvider.get(key);
        const row = existing || {
          provider,
          provider_name: item.provider,
          route_group: item.route_group || "primary",
          priority: Number(item.priority || 0),
          weight: Number(item.weight || 0),
          latency_ms: item.latency_ms,
          kinds: new Set(),
          actual_models: new Set(),
          fallback_only: false
        };
        row.kinds.add(item.kind);
        if (item.actual_model) row.actual_models.add(item.actual_model);
        if (item.latency_ms != null && (row.latency_ms == null || item.latency_ms < row.latency_ms)) row.latency_ms = item.latency_ms;
        byProvider.set(key, row);
      }
      return Array.from(byProvider.values());
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
        const current = byProvider.get(item.provider) || {
          provider: item.provider,
          priority: Number(item.priority || 0),
          weight: Number(item.weight || 0),
          latency_ms: item.latency_ms,
          kinds: new Set()
        };
        current.kinds.add(item.kind);
        current.priority = Math.max(Number(current.priority || 0), Number(item.priority || 0));
        current.weight = Math.max(Number(current.weight || 0), Number(item.weight || 0));
        if (item.latency_ms != null && (current.latency_ms == null || item.latency_ms < current.latency_ms)) {
          current.latency_ms = item.latency_ms;
        }
        byProvider.set(item.provider, current);
      }
      const items = Array.from(byProvider.values()).sort((a, b) =>
        Number(b.priority) - Number(a.priority) ||
        Number(b.weight) - Number(a.weight) ||
        Number(a.latency_ms ?? 999999) - Number(b.latency_ms ?? 999999) ||
        compareText(a.provider, b.provider)
      );
      return `
        <div class="chiprow">
          ${items.map((item) => `<span class="chip ok">${escapeHtml(item.provider)} <span class="model-kind">${escapeHtml(Array.from(item.kinds).sort().join("+"))}</span> W${item.weight}</span>`).join("")}
        </div>
      `;
    }

    function modelStatusPill(model) {
      const chatOk = Number(model.chat_ok || 0);
      const responsesOk = Number(model.responses_ok || 0);
      if (chatOk > 0 && responsesOk > 0) return '<span class="pill ok">全健康</span>';
      if (chatOk > 0 || responsesOk > 0) return '<span class="pill warn">部分健康</span>';
      return '<span class="pill bad">不可用</span>';
    }

    function modelSortRank(modelId) {
      const id = String(modelId || "").toLowerCase();
      if (id.startsWith("gpt") || id.includes("/gpt")) return 0;
      if (id.startsWith("claude") || id.includes("/claude")) return 1;
      if (id.startsWith("gemini") || id.includes("/gemini")) return 2;
      if (id.startsWith("deepseek") || id.includes("/deepseek")) return 3;
      if (id.startsWith("glm") || id.includes("/glm")) return 4;
      return 9;
    }

    function modelVersionParts(modelId) {
      return (String(modelId || "").match(/\\d+/g) || []).map((value) => Number(value));
    }

    function compareModelId(a, b) {
      const rank = modelSortRank(a) - modelSortRank(b);
      if (rank !== 0) return rank;
      const av = modelVersionParts(a);
      const bv = modelVersionParts(b);
      const max = Math.max(av.length, bv.length);
      for (let i = 0; i < max; i += 1) {
        const diff = Number(bv[i] ?? -1) - Number(av[i] ?? -1);
        if (diff !== 0) return diff;
      }
      return compareText(a, b);
    }

    function providerHealthyModels(providerId) {
      const byModel = new Map();
      for (const kind of ["chat", "responses"]) {
        const health = state?.health?.[kind] || {};
        for (const model of Object.keys(health)) {
          for (const item of Object.values(health[model] || {})) {
            if (item.healthy && item.provider_id === providerId) {
              const kinds = byModel.get(model) || new Set();
              kinds.add(kind);
              byModel.set(model, kinds);
            }
          }
        }
      }
      return Array.from(byModel.entries())
        .map(([model, kinds]) => ({ model, kinds: Array.from(kinds).sort() }))
        .sort((a, b) => compareModelId(a.model, b.model));
    }

    function updateModelOptions() {
      const models = new Set((state?.models || []).map((m) => m.id).filter(Boolean));
      $("modelOptions").innerHTML = Array.from(models).sort(compareModelId).map((model) => `<option value="${escapeHtml(model)}"></option>`).join("");
    }

    function updateUpstreamOptions() {
      const upstreams = new Set();
      const models = new Set((state?.models || []).map((m) => m.id).filter(Boolean));
      for (const row of enabledProviderRows()) {
        if (row.provider?.name) upstreams.add(row.provider.name);
        if (row.provider?.id) upstreams.add(String(row.provider.id));
        for (const model of row.provider?.declared_models || []) models.add(model);
      }
      for (const kind of ["chat", "responses"]) {
        const health = state?.health?.[kind] || {};
        for (const model of Object.keys(health)) {
          models.add(model);
          for (const item of Object.values(health[model] || {})) {
            if (item.provider_name) upstreams.add(item.provider_name);
            if (item.provider_id) upstreams.add(item.provider_id);
            if (item.actual_model) models.add(item.actual_model);
          }
        }
      }
      $("upstreamOptions").innerHTML = Array.from(upstreams).sort().map((item) => `<option value="${escapeHtml(item)}"></option>`).join("");
      $("upstreamModelOptions").innerHTML = Array.from(models).sort(compareModelId).map((item) => `<option value="${escapeHtml(item)}"></option>`).join("");
    }

    function smallModelChips(items, limit = 8) {
      const merged = mergeModelKinds(items);
      const shown = merged.slice(0, limit);
      const rest = merged.length - shown.length;
      return `
        <div class="models-mini">
          ${shown.map((entry) => {
            const kinds = Array.from(entry.kinds).sort();
            return `<span class="chip ok mono" title="${escapeHtml(entry.model + " / " + kinds.join(", "))}">${escapeHtml(entry.model)}<span class="model-kind">${escapeHtml(kinds.join("+"))}</span></span>`;
          }).join("")}
          ${rest > 0 ? `<span class="chip dark">+${rest}</span>` : ""}
        </div>
      `;
    }

    function routeCard(row, selectedModel, isTop) {
      const provider = row.provider || {};
      const name = row.provider_name || provider.name || provider.id || "unknown";
      const latency = row.latency_ms ?? row.avg_latency_ms;
      const models = selectedModel
        ? [{ model: selectedModel, kind: Array.from(row.kinds || []).sort().join("+") }]
        : providerHealthyModelDetails(provider.id || "", "");
      const actualModels = row.actual_models ? Array.from(row.actual_models).sort(compareModelId) : [];
      return `
        <div class="route-card">
          <div class="route-card-title">
            <span>${escapeHtml(name)}</span>
            <span class="pill ${row.fallback_only || row.route_group === "paid_fallback" ? "warn" : "ok"}">${escapeHtml(routeLabel(row.route_group))}</span>
          </div>
          <div class="route-meta">
            优先级 ${row.priority} / 权重 ${row.weight}${latency == null ? "" : ` / ${latency} ms`}<br>
            ${selectedModel && actualModels.length ? `实际模型 <span class="mono">${escapeHtml(actualModels.join(", "))}</span>` : `健康 ${row.healthy ?? models.length} / 异常 ${row.unhealthy ?? 0}`}
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

    function availabilityFilters() {
      return {
        modelKeyword: ($("availabilityModelFilter")?.value || "").trim().toLowerCase(),
        upstreamKeyword: ($("availabilityUpstreamFilter")?.value || "").trim().toLowerCase(),
        showUnhealthy: $("showUnhealthyAvailability")?.checked === true
      };
    }

    function rowKindLabels(row) {
      const kinds = [];
      if (row.kinds.chat?.healthy) kinds.push("chat");
      if (row.kinds.responses?.healthy) kinds.push("responses");
      return kinds;
    }

    function routeRowChips(rows, limit = 4) {
      if (!rows.length) return '<span class="muted">无健康上游</span>';
      const shown = rows.slice(0, limit);
      const rest = rows.length - shown.length;
      return `
        <div class="chiprow">
          ${shown.map((row) => {
            const latency = row.best_healthy_latency ?? row.best_failed_latency;
            const kindText = rowKindLabels(row).join("+") || "无健康接口";
            const cls = row.healthy_count > 0 ? "ok" : "warn";
            return `<span class="chip ${cls}" title="${escapeHtml(row.provider_name + " / " + row.model)}">${escapeHtml(row.provider_name)}<span class="model-kind">${escapeHtml(routeLabel(row.route_group))} ${escapeHtml(kindText)}${latency == null ? "" : " " + latency + "ms"}</span></span>`;
          }).join("")}
          ${rest > 0 ? `<span class="chip dark">+${rest}</span>` : ""}
        </div>
      `;
    }

    function reasonSummary(reasons) {
      const values = Array.from(reasons || []).filter((reason) => reason && reason !== "ok");
      if (!values.length) return "";
      const priority = [
        "runtime_failure:real_shape_invalid",
        "real_shape_invalid",
        "auth_or_forbidden",
        "quota",
        "rate_limited",
        "server_unavailable",
        "exception:ReadTimeout",
        "model_unsupported",
        "not_found",
        "responses_request_shape_unverified"
      ];
      values.sort((a, b) => {
        const ai = priority.findIndex((item) => a === item || a.startsWith(item));
        const bi = priority.findIndex((item) => b === item || b.startsWith(item));
        return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || compareText(a, b);
      });
      return values.slice(0, 3).join(", ");
    }

    function buildModelAvailabilityRows() {
      const rows = buildUpstreamRows();
      const filters = availabilityFilters();
      const byModel = new Map();
      for (const row of rows) {
        const current = byModel.get(row.model) || {
          id: row.model,
          chat_ok: 0,
          responses_ok: 0,
          rows: [],
          healthy_rows: [],
          checked_at: 0,
          next_probe_at: null,
          best_latency: null,
          reasons: new Set()
        };
        current.rows.push(row);
        if (row.healthy_count > 0) current.healthy_rows.push(row);
        if (row.kinds.chat?.healthy) current.chat_ok += 1;
        if (row.kinds.responses?.healthy) current.responses_ok += 1;
        if (row.checked_at && row.checked_at > current.checked_at) current.checked_at = row.checked_at;
        if (row.next_probe_at && (current.next_probe_at == null || row.next_probe_at < current.next_probe_at)) current.next_probe_at = row.next_probe_at;
        const latency = row.best_healthy_latency ?? row.best_failed_latency;
        if (latency != null && (current.best_latency == null || latency < current.best_latency)) current.best_latency = latency;
        for (const reason of row.reasons) current.reasons.add(reason);
        byModel.set(row.model, current);
      }
      if (!filters.upstreamKeyword) {
        for (const model of state?.models || []) {
          const id = model.id || "";
          if (!id) continue;
          if (filters.modelKeyword && !id.toLowerCase().includes(filters.modelKeyword)) continue;
          if (!filters.showUnhealthy && Number(model.chat_ok || 0) + Number(model.responses_ok || 0) <= 0) continue;
          if (!byModel.has(id)) {
            byModel.set(id, {
              id,
              chat_ok: Number(model.chat_ok || 0),
              responses_ok: Number(model.responses_ok || 0),
              rows: [],
              healthy_rows: [],
              checked_at: 0,
              next_probe_at: null,
              best_latency: null,
              reasons: new Set()
            });
          }
        }
      }
      return Array.from(byModel.values()).sort((a, b) =>
        compareModelId(a.id, b.id) ||
        Number(b.chat_ok + b.responses_ok) - Number(a.chat_ok + a.responses_ok) ||
        Number(a.best_latency ?? 999999) - Number(b.best_latency ?? 999999)
      );
    }

    function renderModels(data) {
      const ordered = buildModelAvailabilityRows();
      const page = paginate("models", ordered);
      $("modelsBody").innerHTML = page.items.map((m) => {
        const healthyRows = sortedRouteRows(m.healthy_rows);
        const primary = healthyRows.filter((row) => row.route_group !== "paid_fallback" && !row.fallback_only);
        const first = primary[0] || healthyRows[0];
        const secondary = healthyRows.filter((row) => row !== first);
        const detail = reasonSummary(m.reasons);
        return `
        <tr>
          <td class="mono">${escapeHtml(m.id)}</td>
          <td>
            <div class="chiprow">
              <span class="chip ${m.chat_ok > 0 ? "ok" : "dark"}">chat ${m.chat_ok}</span>
              <span class="chip ${m.responses_ok > 0 ? "ok" : "dark"}">responses ${m.responses_ok}</span>
            </div>
          </td>
          <td>${first ? routeRowChips([first], 1) : '<span class="muted">无健康首选</span>'}</td>
          <td>${routeRowChips(secondary, 4)}</td>
          <td>${m.best_latency == null ? "" : m.best_latency + " ms"}</td>
          <td>${formatTs(m.checked_at, "未检测")}</td>
          <td>${formatTs(m.next_probe_at)}</td>
          <td>
            ${modelStatusPill(m)}
            ${detail ? `<div class="cell-sub mono">${escapeHtml(detail)}</div>` : ""}
          </td>
        </tr>
      `;
      }).join("");
      renderPager("models", page.total, page.totalPages);
    }

    function renderAvailability() {
      $("availabilityModelView").classList.toggle("hidden", availabilityView !== "model");
      $("availabilityUpstreamView").classList.toggle("hidden", availabilityView !== "upstream");
      document.querySelectorAll("[data-availability-view]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.availabilityView === availabilityView);
      });
      renderModels(state);
      renderUpstreams();
    }

    function renderMatrixPolicy(data) {
      const el = $("matrixPolicyHelp");
      if (!el) return;
      const policy = data.health_policy || {};
      const cooldowns = policy.cooldowns || {};
      const interval = formatDuration(policy.probe_interval_seconds);
      const maxPerCycle = Number(policy.probe_max_per_cycle || 0);
      const confirmations = Number(policy.responses_invalid_request_confirmations || 3);
      const responsesProbe = policy.enable_responses_probe === false ? "Responses 探测关闭" : "Responses 开启二段形态验证";
      const freshTtl = formatDuration(policy.health_fresh_ttl_seconds);
      const adaptiveRouting = policy.adaptive_format_routing === false ? "跨格式路由关闭" : `跨格式自适应开启，转换延迟惩罚 ${Number(policy.adapter_latency_penalty_ms || 0)}ms`;
      const cooldown = (key) => formatDuration(cooldowns[key]);
      const visible = [
        `每 ${interval || "-"} 增量探测，最多 ${maxPerCycle || "-"} 项`,
        `实时新鲜窗口 ${freshTtl || "-"}`,
        "健康 = 2xx 且响应无 error",
        `${responsesProbe}`,
        adaptiveRouting,
        `真实请求成功会立即刷新健康；Responses 同形态 ${confirmations} 次失败才确认不兼容`
      ];
      el.innerHTML = `
        <div class="matrix-help-title">
          <span>健康判定 / 冷却策略</span>
          <div class="help-popover">
            <button type="button" class="help-dot" aria-label="查看探测矩阵规则">?</button>
            <div class="help-popover-panel" role="tooltip">
              <h3>探测矩阵怎么读</h3>
              <ul class="policy-list">
                <li><span class="policy-key">记录粒度</span><span>每一行是接口类型、网关模型、上游、实际模型的组合。Chat 和 Responses 独立判定。</span></li>
                <li><span class="policy-key">探测节奏</span><span>后台每 ${escapeHtml(interval || "-")} 跑增量探测；每轮最多 ${escapeHtml(maxPerCycle || "-")} 项。新记录、到期记录、配置签名变化优先探测，未到期记录保留上次结果。</span></li>
                <li><span class="policy-key">Chat 判定</span><span>按配置请求 ${escapeHtml((data.health_policy || {}).chat_path || "/chat/completions")}；HTTP 2xx 且响应 JSON 没有 error 就是健康。</span></li>
                <li><span class="policy-key">Responses 判定</span><span>先用轻量探测请求 ${escapeHtml((data.health_policy || {}).responses_path || "/responses")}；如果上游返回 invalid codex request，会追加一次 Codex 真实诊断形态探测，诊断成功就标健康。</span></li>
                <li><span class="policy-key">运行时反馈</span><span>真实业务请求成功会把对应上游立即标为 ok；运行时失败会写入 runtime_failure 并进入对应冷却。</span></li>
                <li><span class="policy-key">健康新鲜度</span><span>最近 ${escapeHtml(freshTtl || "-")} 内成功验证显示为实时健康；超过该窗口但仍在成功 TTL 内显示为缓存健康，表示可路由但需要关注复查时间。</span></li>
                <li><span class="policy-key">跨格式路由</span><span>${escapeHtml(adaptiveRouting)}。客户端请求格式保持不变，网关会把 OpenAI Chat、Responses、Codex 和 Claude 工具/图片/工具结果历史规范化后，按健康、延迟和权重选择可用上游，再把响应转回客户端格式；无法映射的 hosted tool 或高级字段才会被排除。</span></li>
                <li><span class="policy-key">形态确认</span><span>Responses 的真实请求同一形态连续 ${escapeHtml(confirmations)} 次 invalid_request 后，才确认为 real_shape_invalid；确认前仍会在付费兜底前做验证。</span></li>
                <li><span class="policy-key">路由使用</span><span>常规路由优先使用健康项；pending/probe_budget_exhausted 或待验证 Responses 可进入影子/探测重试桶；real_shape_invalid 冷却期内不自动抢在付费兜底前。</span></li>
              </ul>
              <h3 style="margin-top: 12px;">冷却时间</h3>
              <ul class="policy-list">
                <li><span class="policy-key">健康 ok</span><span>${escapeHtml(cooldown("success") || "-")} 后到期重探。</span></li>
                <li><span class="policy-key">模型不支持</span><span>${escapeHtml(cooldown("model_unsupported") || "-")}，对应 not_found / model_unsupported。</span></li>
                <li><span class="policy-key">鉴权失败</span><span>${escapeHtml(cooldown("auth_or_forbidden") || "-")}，对应 401 / 403。</span></li>
                <li><span class="policy-key">额度不足</span><span>${escapeHtml(cooldown("quota") || "-")}。</span></li>
                <li><span class="policy-key">限流</span><span>${escapeHtml(cooldown("rate_limited") || "-")}。</span></li>
                <li><span class="policy-key">服务异常</span><span>${escapeHtml(cooldown("server_unavailable") || "-")}，对应 5xx / empty_stream。</span></li>
                <li><span class="policy-key">网络异常</span><span>${escapeHtml(cooldown("exception") || "-")}，对应超时、连接错误等 exception。</span></li>
                <li><span class="policy-key">形态待确认</span><span>${escapeHtml(cooldown("responses_shape_retry") || "-")} 后快速重试。</span></li>
                <li><span class="policy-key">形态不兼容</span><span>${escapeHtml(cooldown("responses_real_shape_invalid") || "-")} 后再尝试。</span></li>
                <li><span class="policy-key">未知错误</span><span>${escapeHtml(cooldown("unknown") || "-")}。</span></li>
              </ul>
            </div>
          </div>
        </div>
        <div class="matrix-help-summary">
          ${visible.map((text) => `<span class="chip dark">${escapeHtml(text)}</span>`).join("")}
        </div>
      `;
    }

    function matrixFilters() {
      return {
        kind: matrixKindFilter,
        status: matrixStatusFilter,
        modelKeyword: ($("matrixModelFilter")?.value || "").trim().toLowerCase(),
        upstreamKeyword: ($("matrixUpstreamFilter")?.value || "").trim().toLowerCase()
      };
    }

    function matrixTextMatches(keyword, values) {
      if (!keyword) return true;
      return values.some((value) => String(value || "").toLowerCase().includes(keyword));
    }

    function matrixItemMatchesFilters(entry, filters) {
      const item = entry.item || {};
      if (filters.kind !== "all" && entry.kind !== filters.kind) return false;
      if (filters.status === "healthy" && !item.healthy) return false;
      if (filters.status === "unhealthy" && item.healthy) return false;
      if (!matrixTextMatches(filters.modelKeyword, [entry.model, item.actual_model])) return false;
      return matrixTextMatches(filters.upstreamKeyword, [item.provider_name, item.provider_id]);
    }

    function freshnessChip(data) {
      const status = data?.health_freshness || "";
      const age = data?.health_age_seconds == null ? "" : ` ${formatDuration(data.health_age_seconds)}`;
      const labels = {
        fresh_ok: ["ok", "实时"],
        stale_ok: ["warn", "缓存"],
        cooldown: ["warn", "冷却"],
        probing: ["dark", "待探测"],
        stale_fail: ["bad", "过期异常"],
        unknown: ["dark", "未知"]
      };
      const [cls, text] = labels[status] || labels.unknown;
      return `<span class="chip ${cls}" title="距离最近检测${escapeHtml(age || '未知')}">${text}${escapeHtml(age)}</span>`;
    }

    function renderMatrixFilterState(total, filtered) {
      document.querySelectorAll("[data-matrix-kind]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.matrixKind === matrixKindFilter);
      });
      document.querySelectorAll("[data-matrix-status]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.matrixStatus === matrixStatusFilter);
      });
      const count = $("matrixFilterCount");
      if (count) count.textContent = `显示 ${filtered} / ${total}`;
    }

    function renderMatrix(data) {
      renderMatrixPolicy(data);
      const rows = [];
      const allItems = [];
      for (const kind of ["chat", "responses"]) {
        const group = data.health[kind] || {};
        for (const model of Object.keys(group).sort(compareModelId)) {
          for (const item of Object.values(group[model])) {
            allItems.push({ kind, model, item });
          }
        }
      }
      const filters = matrixFilters();
      const items = allItems.filter((entry) => matrixItemMatchesFilters(entry, filters));
      renderMatrixFilterState(allItems.length, items.length);
      items.sort((a, b) =>
        Number(b.item.checked_at || 0) - Number(a.item.checked_at || 0) ||
        Number(a.item.next_probe_at || 0) - Number(b.item.next_probe_at || 0) ||
        compareText(a.kind, b.kind) ||
        compareModelId(a.model, b.model) ||
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
                <td>${freshnessChip(item)}</td>
                <td>${item.latency_ms == null ? "" : item.latency_ms + " ms"}</td>
                <td>${formatTs(item.checked_at, "未检测")}</td>
                <td>${formatTs(item.next_probe_at)}</td>
                <td class="mono">${item.reason || item.skip_reason || ""}</td>
              </tr>
            `);
      }
      $("matrixBody").innerHTML = rows.length ? rows.join("") : '<tr><td colspan="13" class="muted">无匹配探测记录</td></tr>';
      renderPager("matrix", page.total, page.totalPages);
    }

    function buildUpstreamRows() {
      const enabledIds = new Set(enabledProviderRows().map((row) => row.provider.id).filter(Boolean));
      const byKey = new Map();
      for (const kind of ["chat", "responses"]) {
        const group = state?.health?.[kind] || {};
        for (const model of Object.keys(group)) {
          for (const item of Object.values(group[model] || {})) {
            const providerId = item.provider_id || "";
            if (!enabledIds.has(providerId)) continue;
            const key = `${providerId}::${model}`;
            const provider = providers.find((p) => p.id === providerId) || {};
            const policy = provider.editable_policy || {};
            const row = byKey.get(key) || {
              provider,
              provider_id: providerId,
              provider_name: item.provider_name || provider.name || providerId,
              model,
              route_group: item.route_group || policy.route_group || provider.route_group || "",
              priority: Number(item.priority ?? policy.priority ?? provider.priority ?? 0),
              weight: Number(item.weight ?? policy.weight ?? provider.weight ?? 0),
              kinds: {},
              checked_at: 0,
              next_probe_at: null,
              best_healthy_latency: null,
              best_failed_latency: null,
              healthy_count: 0,
              total_count: 0,
              reasons: new Set(),
              actual_models: new Set()
            };
            row.kinds[kind] = {
              healthy: !!item.healthy,
              latency_ms: item.latency_ms,
              checked_at: item.checked_at,
              next_probe_at: item.next_probe_at,
              reason: item.reason || item.skip_reason || "",
              actual_model: item.actual_model || "",
              shape_status: item.shape_status || "",
              shape_invalid_count: Number(item.shape_invalid_count || 0),
              shape_invalid_required: Number(item.shape_invalid_required || 3),
              shape_invalid_last_at: item.shape_invalid_last_at,
              shape_verification_source: item.shape_verification_source || "",
              health_freshness: item.health_freshness || "",
              health_age_seconds: item.health_age_seconds,
              health_fresh: item.health_fresh === true
            };
            row.total_count += 1;
            if (item.healthy) row.healthy_count += 1;
            if (item.reason || item.skip_reason) row.reasons.add(item.reason || item.skip_reason);
            if (item.actual_model) row.actual_models.add(item.actual_model);
            if (item.checked_at && item.checked_at > row.checked_at) row.checked_at = item.checked_at;
            if (item.next_probe_at && (row.next_probe_at == null || item.next_probe_at < row.next_probe_at)) row.next_probe_at = item.next_probe_at;
            if (item.latency_ms != null && item.healthy && (row.best_healthy_latency == null || item.latency_ms < row.best_healthy_latency)) row.best_healthy_latency = item.latency_ms;
            if (item.latency_ms != null && !item.healthy && (row.best_failed_latency == null || item.latency_ms < row.best_failed_latency)) row.best_failed_latency = item.latency_ms;
            byKey.set(key, row);
          }
        }
      }
      const { upstreamKeyword, modelKeyword, showUnhealthy } = availabilityFilters();
      return Array.from(byKey.values()).filter((row) => {
        if (!showUnhealthy && row.healthy_count <= 0) return false;
        const upstreamText = `${row.provider_name} ${row.provider_id}`.toLowerCase();
        const modelText = `${row.model} ${Array.from(row.actual_models).join(" ")}`.toLowerCase();
        return (!upstreamKeyword || upstreamText.includes(upstreamKeyword)) && (!modelKeyword || modelText.includes(modelKeyword));
      }).sort((a, b) =>
        compareText(a.provider_name, b.provider_name) ||
        compareText(a.provider_id, b.provider_id) ||
        compareModelId(a.model, b.model) ||
        (routeOrder[a.route_group] ?? 99) - (routeOrder[b.route_group] ?? 99) ||
        Number(b.priority) - Number(a.priority) ||
        Number(b.weight) - Number(a.weight) ||
        Number(b.healthy_count > 0) - Number(a.healthy_count > 0) ||
        Number((a.best_healthy_latency ?? a.best_failed_latency) ?? 999999) - Number((b.best_healthy_latency ?? b.best_failed_latency) ?? 999999)
      );
    }

    function kindStatusChip(kind, data) {
      if (!data) return `<span class="chip dark">${kind} 无记录</span>`;
      const requestShapeUnverified = kind === "responses" && ["invalid_request", "responses_request_shape_unverified", "runtime_failure:invalid_request", "runtime_failure:responses_request_shape_unverified"].includes(data.reason || "");
      const realShapeInvalid = kind === "responses" && ["real_shape_invalid", "runtime_failure:real_shape_invalid"].includes(data.reason || "");
      const cls = data.healthy ? "ok" : (requestShapeUnverified ? "dark" : "warn");
      const text = data.healthy ? "健康" : (realShapeInvalid ? "形态不兼容" : (requestShapeUnverified ? "待真实请求验证" : "异常"));
      const freshness = data.health_freshness === "fresh_ok" ? "实时" : data.health_freshness === "stale_ok" ? "缓存" : data.health_freshness === "cooldown" ? "冷却" : "";
      return `<span class="chip ${cls}">${kind} ${text}${freshness ? " " + freshness : ""}${data.latency_ms == null ? "" : " " + data.latency_ms + "ms"}</span>`;
    }

    function cooldownSeconds(data) {
      if (!data || !data.checked_at || !data.next_probe_at) return null;
      return Math.max(0, Number(data.next_probe_at) - Number(data.checked_at));
    }

    function upstreamPolicyDetail(row) {
      const responses = row.kinds.responses;
      if (responses) {
        const reason = responses.reason || "";
        const count = Number(responses.shape_invalid_count || 0);
        const required = Number(responses.shape_invalid_required || 3);
        if (["real_shape_invalid", "runtime_failure:real_shape_invalid"].includes(reason)) {
          return `真实请求确认 ${required}/${required} 失败；自动冷却至 ${formatTs(responses.next_probe_at)}`;
        }
        if (["invalid_request", "responses_request_shape_unverified", "runtime_failure:invalid_request", "runtime_failure:responses_request_shape_unverified"].includes(reason)) {
          const current = count > 0 ? count : 0;
          const source = responses.shape_status === "probe_unverified" || current === 0 ? "探活形态不可信" : "真实请求确认中";
          return `${source}；真实请求失败 ${current}/${required}，未满 ${required} 次仍会在付费兜底前验证`;
        }
      }
      const data = responses || row.kinds.chat;
      const ttl = formatDuration(cooldownSeconds(data));
      if (row.healthy_count > 0) return `健康缓存${ttl ? " " + ttl : ""}；到期后增量探测`;
      if (!data) return "暂无检测记录；等待增量探测";
      const reason = data.reason || "";
      if (["not_found", "model_unsupported"].includes(reason)) return `模型不支持长冷却${ttl ? " " + ttl : ""}`;
      if (["auth_or_forbidden", "quota", "rate_limited", "server_unavailable", "empty_stream"].includes(reason)) return `异常冷却${ttl ? " " + ttl : ""}；到期后重试`;
      if (reason.startsWith("runtime_failure:")) return `运行时失败冷却${ttl ? " " + ttl : ""}`;
      return `按原因冷却${ttl ? " " + ttl : ""}`;
    }

    function upstreamDetail(row) {
      const reasons = Array.from(row.reasons).filter((reason) => reason && reason !== "ok").slice(0, 3);
      if (reasons.some((reason) => ["real_shape_invalid", "runtime_failure:real_shape_invalid"].includes(reason))) {
        return "真实 Codex Responses 请求连续确认失败，冷却期内不自动选用";
      }
      if (reasons.some((reason) => ["invalid_request", "responses_request_shape_unverified", "runtime_failure:invalid_request", "runtime_failure:responses_request_shape_unverified"].includes(reason))) {
        return "Responses 探活或真实请求形态被拒，按三次真实请求确认后再判不可用";
      }
      if (row.healthy_count <= 0 && reasons.length) return reasons.join(", ");
      const mapped = Array.from(row.actual_models).filter((actual) => actual && actual !== row.model).sort(compareModelId);
      if (mapped.length) return `映射 ${mapped.join(", ")}`;
      if (row.healthy_count > 0 && row.healthy_count < row.total_count && reasons.length) return reasons.join(", ");
      return "";
    }

    function renderUpstreams() {
      const rows = buildUpstreamRows();
      const page = paginate("upstreams", rows);
      $("upstreamsBody").innerHTML = page.items.map((row) => {
        const detail = upstreamDetail(row);
        const latency = row.best_healthy_latency ?? row.best_failed_latency;
        return `
          <tr>
            <td>
              <div class="cell-main">${escapeHtml(row.provider_name)}</div>
              <div class="cell-sub mono">${escapeHtml(row.provider_id)}</div>
            </td>
            <td>
              <div>${routeLabel(row.route_group)}</div>
              <div class="cell-sub">优先 ${row.priority} / 权重 ${row.weight}</div>
            </td>
            <td class="mono">${escapeHtml(row.model)}</td>
            <td><div class="chiprow">${kindStatusChip("chat", row.kinds.chat)}${kindStatusChip("responses", row.kinds.responses)}</div></td>
            <td>${statusPill(row.healthy_count > 0, row.healthy_count > 0 && row.healthy_count < row.total_count)}</td>
            <td>${latency == null ? "" : latency + " ms"}</td>
            <td>${formatTs(row.checked_at, "未检测")}</td>
            <td>${formatTs(row.next_probe_at)}</td>
            <td>${escapeHtml(upstreamPolicyDetail(row))}</td>
            <td class="mono">${escapeHtml(detail)}</td>
          </tr>
        `;
      }).join("");
      renderPager("upstreams", page.total, page.totalPages);
    }

    function logsFilters() {
      return {
        success: logSuccessFilter,
        search: ($("logSearchFilter")?.value || "").trim().toLowerCase(),
        model: ($("logModelFilter")?.value || "").trim().toLowerCase(),
        upstream: ($("logUpstreamFilter")?.value || "").trim().toLowerCase(),
        kind: $("logKindFilter")?.value || "all",
        stream: $("logStreamFilter")?.value || "all",
        adapter: $("logAdapterFilter")?.value || "all",
        shape: $("logShapeFilter")?.value || "all",
        error: ($("logErrorFilter")?.value || "").trim().toLowerCase()
      };
    }

    function textMatches(keyword, values) {
      if (!keyword) return true;
      return values.some((value) => String(value || "").toLowerCase().includes(keyword));
    }

    function logUsesAdapter(row) {
      const adapter = row.format_adapter || "native";
      if (adapter && adapter !== "native") return true;
      return Boolean(row.upstream_kind && row.kind && row.upstream_kind !== row.kind);
    }

    function logMatchesFilters(row, filters) {
      const shape = row.request_shape || {};
      if (filters.success === "success" && !row.success) return false;
      if (filters.success === "failure" && row.success) return false;
      if (filters.kind !== "all" && row.kind !== filters.kind) return false;
      if (filters.stream === "stream" && !row.stream) return false;
      if (filters.stream === "nonstream" && row.stream) return false;
      if (filters.adapter === "native" && logUsesAdapter(row)) return false;
      if (filters.adapter === "adapted" && !logUsesAdapter(row)) return false;
      if (!["all", "native", "adapted"].includes(filters.adapter) && (row.format_adapter || "native") !== filters.adapter) return false;
      if (filters.shape === "image" && !shape.has_image_content) return false;
      if (filters.shape === "tools" && Number(shape.tools_count || 0) <= 0) return false;
      if (filters.shape === "client_invalid_input" && row.error_type !== "client_invalid_input") return false;
      if (!textMatches(filters.model, [row.requested_model, row.actual_model])) return false;
      if (!textMatches(filters.upstream, [row.provider_id, row.provider_name, row.endpoint_url])) return false;
      if (!textMatches(filters.error, [row.error_type, row.error_sample])) return false;
      return textMatches(filters.search, [
        row.request_id,
        row.kind,
        row.requested_model,
        row.actual_model,
        row.provider_id,
        row.provider_name,
        row.path,
        row.endpoint_url,
        row.route_bucket,
        row.route_group,
        row.upstream_kind,
        row.format_adapter,
        row.error_type,
        row.error_sample,
        (shape.message_content_types || []).join(" "),
        (shape.body_keys || []).join(" ")
      ]);
    }

    function logShapeSummary(row) {
      const shape = row.request_shape || {};
      const chips = [];
      if (row.upstream_kind && row.upstream_kind !== row.kind) chips.push(`<span class="chip warn">上游 ${escapeHtml(row.upstream_kind)}</span>`);
      if (row.format_adapter && row.format_adapter !== "native") chips.push(`<span class="chip dark">${escapeHtml(row.format_adapter)}</span>`);
      if (shape.has_image_content) chips.push('<span class="chip ok">图片</span>');
      if (Number(shape.tools_count || 0) > 0) chips.push(`<span class="chip ok">tools ${Number(shape.tools_count || 0)}</span>`);
      if (shape.message_content_types?.length) chips.push(`<span class="chip dark">${escapeHtml(shape.message_content_types.join("+"))}</span>`);
      return chips.length ? `<div class="chiprow">${chips.join("")}</div>` : "";
    }

    function updateLogErrorOptions(rows) {
      const el = $("logErrorOptions");
      if (!el) return;
      const errors = Array.from(new Set(rows.map((row) => row.error_type).filter(Boolean))).sort(compareText);
      el.innerHTML = errors.map((error) => `<option value="${escapeHtml(error)}"></option>`).join("");
    }

    function renderLogsFilterState(total, filtered) {
      document.querySelectorAll("[data-log-success]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.logSuccess === logSuccessFilter);
      });
      const count = $("logsFilterCount");
      if (count) count.textContent = `显示 ${filtered} / ${total}`;
    }

    function renderLogs(data) {
      const allRows = data.logs || [];
      updateLogErrorOptions(allRows);
      const filters = logsFilters();
      const rows = allRows.filter((row) => logMatchesFilters(row, filters));
      renderLogsFilterState(allRows.length, rows.length);
      const page = paginate("logs", rows);
      $("logsBody").innerHTML = page.items.map((row) => {
        const usage = row.usage || {};
        const tokens = usage.total_tokens == null ? "" : usage.total_tokens;
        const requestedModel = row.requested_model || "";
        const actualModel = row.actual_model || "";
        const route = routeLabel(row.route_bucket || row.route_group);
        const adapter = row.format_adapter || "native";
        const upstreamKind = row.upstream_kind || row.kind || "";
        const latency = row.latency_ms == null ? "" : `${row.latency_ms} ms`;
        const endpointStatus = row.status_code ? `HTTP ${row.status_code}` : "";
        return `
          <tr>
            <td title="${escapeHtml(row.request_id || "")}">
              <div class="log-cell">
                <div class="cell-main">${formatTs(row.ts)}</div>
                <div class="cell-sub mono">${escapeHtml(row.request_id || "")}</div>
              </div>
            </td>
            <td>
              <div class="log-cell">
                <div class="log-line">${logStatusPill(!!row.success)} <span class="mono">${escapeHtml(row.kind || "")}${row.stream ? " stream" : ""}</span></div>
                <div class="cell-sub mono">${escapeHtml(endpointStatus)}</div>
              </div>
            </td>
            <td title="${escapeHtml([requestedModel, actualModel].filter(Boolean).join(" -> "))}">
              <div class="log-cell">
                <div class="cell-main mono">${escapeHtml(requestedModel)}</div>
                <div class="cell-sub mono">${actualModel && actualModel !== requestedModel ? `上游 ${escapeHtml(actualModel)}` : escapeHtml(actualModel || "")}</div>
              </div>
            </td>
            <td title="${escapeHtml([row.provider_id, route, upstreamKind, adapter].filter(Boolean).join(" / "))}">
              <div class="log-cell">
                <div class="cell-main">${escapeHtml(row.provider_id || "")}</div>
                <div class="cell-sub mono">${escapeHtml(route)} / ${escapeHtml(upstreamKind)} / ${escapeHtml(adapter)}</div>
              </div>
            </td>
            <td>
              <div class="log-cell">
                <div class="cell-main mono">${escapeHtml(latency)}</div>
                <div class="cell-sub mono">${tokens === "" ? "" : `${escapeHtml(String(tokens))} tokens`}</div>
              </div>
            </td>
            <td title="${escapeHtml(row.error_sample || "")}">
              <div class="log-cell">
                ${logShapeSummary(row) || '<div class="cell-sub">-</div>'}
                <div class="cell-sub mono">${escapeHtml(row.error_type || "")}</div>
              </div>
            </td>
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
      const enabledValue = String(providerValue(p, "enabled", String((policy.enabled ?? p.enabled) !== false)));
      const routeValue = providerValue(p, "route_group", policy.route_group || p.route_group);
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
              <input type="hidden" data-field="fallback_only" value="${escapeHtml(fallbackValue)}">
              <div class="cell-sub">付费兜底只由策略层级决定</div>
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
            </div>
          </td>
          <td>
            <div class="stack">
              <textarea class="provider-models" data-field="models">${escapeHtml(models)}</textarea>
            </div>
          </td>
          <td><div class="chiprow">${healthyModels.length ? healthyModels.slice(0, 18).map((m) => `<span class="chip ok mono">${escapeHtml(m.model)}<span class="model-kind">${escapeHtml(m.kinds.join("+"))}</span></span>`).join("") + (healthyModels.length > 18 ? `<span class="chip dark">+${healthyModels.length - 18}</span>` : "") : '<span class="muted">暂无健康模型</span>'}</div></td>
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
        const routeGroup = get("route_group", policy.route_group || provider.route_group);
        return {
          id: Number(key),
          enabled: String(get("enabled", String((policy.enabled ?? provider.enabled) !== false))) === "true",
          route_group: routeGroup,
          fallback_only: routeGroup === "paid_fallback",
          priority: Number(get("priority", policy.priority ?? provider.priority ?? 0) || 0),
          weight: Number(get("weight", policy.weight ?? provider.weight ?? 100) || 100),
          base_url: get("base_url", policy.base_url || provider.base_url || ""),
          models: get("models", policy.models || (provider.declared_models || []).join(","))
        };
      }).filter((item) => item.id > 0);
    }

    async function loadAll(options = {}) {
      const preserveDrafts = options.preserveDrafts === true;
      if (preserveDrafts) syncVisibleProviderDrafts();
      const previousDrafts = preserveDrafts ? { ...providerDrafts } : {};
      showApp();
      const [overview, providerData] = await Promise.all([
        api("/gateway-admin/api/overview"),
        api("/gateway-admin/api/providers")
      ]);
      const logs = await api("/gateway-admin/api/request-logs?limit=500");
      state = overview;
      providers = providerData.providers;
      providerDrafts = preserveDrafts ? previousDrafts : {};
      logsData = logs;
      renderOverview(overview);
      renderMatrix(overview);
      renderAvailability();
      renderLogs(logs);
      renderProviders();
      updateModelOptions();
      updateUpstreamOptions();
      renderRouteBoard();
    }

    function activateTab(tab) {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".tabpane").forEach((x) => x.classList.add("hidden"));
      tab.classList.add("active");
      $("tab-" + tab.dataset.tab).classList.remove("hidden");
      if (tab.dataset.tab === "models") renderAvailability();
      if (tab.dataset.tab === "providers") renderRouteBoard();
    }

    const AUTO_REFRESH_MS = 10000;
    let autoRefreshTimer = null;
    let autoRefreshCountdownTimer = null;
    let autoRefreshRemaining = 0;

    function clearAutoRefresh() {
      if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null; }
      if (autoRefreshCountdownTimer) { clearInterval(autoRefreshCountdownTimer); autoRefreshCountdownTimer = null; }
      autoRefreshRemaining = 0;
      const el = $("autoRefreshCountdown");
      if (el) el.textContent = "";
    }

    function startAutoRefresh() {
      clearAutoRefresh();
      autoRefreshRemaining = Math.round(AUTO_REFRESH_MS / 1000);
      const countdownEl = $("autoRefreshCountdown");
      if (countdownEl) countdownEl.textContent = `${autoRefreshRemaining}s`;
      autoRefreshCountdownTimer = setInterval(() => {
        autoRefreshRemaining = Math.max(0, autoRefreshRemaining - 1);
        if (countdownEl) countdownEl.textContent = `${autoRefreshRemaining}s`;
      }, 1000);
      autoRefreshTimer = setInterval(async () => {
        try { await loadAll({ preserveDrafts: true }); } catch {}
        autoRefreshRemaining = Math.round(AUTO_REFRESH_MS / 1000);
        if (countdownEl) countdownEl.textContent = `${autoRefreshRemaining}s`;
      }, AUTO_REFRESH_MS);
    }

    function applyAutoRefreshSetting(enabled) {
      const cb = $("autoRefresh");
      if (cb) cb.checked = enabled;
      if (enabled) startAutoRefresh(); else clearAutoRefresh();
    }

    $("autoRefresh").addEventListener("change", (event) => {
      const enabled = event.target.checked;
      localStorage.setItem(autoRefreshKey, enabled ? "1" : "0");
      applyAutoRefreshSetting(enabled);
    });

    let tabRefreshSeq = 0;
    async function refreshAfterTabClick(tab) {
      const seq = ++tabRefreshSeq;
      const label = tab.textContent.trim();
      try {
        await loadAll({ preserveDrafts: true });
        if (seq === tabRefreshSeq) setNotice(`已自动刷新“${label}”数据。`);
      } catch (err) {
        if (seq === tabRefreshSeq) showLogin(err.message);
      }
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
      const btn = $("refreshBtn");
      btn.disabled = true;
      const oldText = btn.textContent;
      btn.textContent = "刷新中";
      try {
        await loadAll();
        setNotice("已刷新当前页面数据。");
      } catch (err) {
        showLogin(err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = oldText;
      }
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
      if (name === "models") renderAvailability();
      if (name === "matrix") renderMatrix(state);
      if (name === "upstreams") renderAvailability();
      if (name === "logs") renderLogs(logsData);
      if (name === "providers") {
        renderProviders();
        renderRouteBoard();
      }
    });

    document.addEventListener("change", (event) => {
      const select = event.target.closest("[data-page-size]");
      if (!select) return;
      const name = select.dataset.pageSize;
      if (name === "providers") syncVisibleProviderDrafts();
      pageSizes[name] = Number(select.value || 25);
      pages[name] = 1;
      if (name === "models") renderAvailability();
      if (name === "matrix") renderMatrix(state);
      if (name === "upstreams") renderAvailability();
      if (name === "logs") renderLogs(logsData);
      if (name === "providers") {
        renderProviders();
        renderRouteBoard();
      }
    });

    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        activateTab(tab);
        refreshAfterTabClick(tab);
      });
    });

    $("modelFilter").addEventListener("input", renderRouteBoard);
    function handleAvailabilityFilterInput() {
      pages.models = 1;
      pages.upstreams = 1;
      renderAvailability();
    }
    document.querySelectorAll("[data-availability-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        availabilityView = btn.dataset.availabilityView || "model";
        renderAvailability();
      });
    });
    $("availabilityModelFilter").addEventListener("input", handleAvailabilityFilterInput);
    $("availabilityUpstreamFilter").addEventListener("input", handleAvailabilityFilterInput);
    $("showUnhealthyAvailability").addEventListener("change", handleAvailabilityFilterInput);

    function handleMatrixFilterInput() {
      pages.matrix = 1;
      renderMatrix(state);
    }
    document.querySelectorAll("[data-matrix-kind]").forEach((btn) => {
      btn.addEventListener("click", () => {
        matrixKindFilter = btn.dataset.matrixKind || "all";
        handleMatrixFilterInput();
      });
    });
    document.querySelectorAll("[data-matrix-status]").forEach((btn) => {
      btn.addEventListener("click", () => {
        matrixStatusFilter = btn.dataset.matrixStatus || "all";
        handleMatrixFilterInput();
      });
    });
    $("matrixModelFilter").addEventListener("input", handleMatrixFilterInput);
    $("matrixUpstreamFilter").addEventListener("input", handleMatrixFilterInput);
    $("matrixClearFilters").addEventListener("click", () => {
      matrixKindFilter = "all";
      matrixStatusFilter = "all";
      $("matrixModelFilter").value = "";
      $("matrixUpstreamFilter").value = "";
      handleMatrixFilterInput();
    });

    function handleLogFilterInput() {
      pages.logs = 1;
      renderLogs(logsData);
    }
    document.querySelectorAll("[data-log-success]").forEach((btn) => {
      btn.addEventListener("click", () => {
        logSuccessFilter = btn.dataset.logSuccess || "all";
        handleLogFilterInput();
      });
    });
    [
      "logSearchFilter",
      "logModelFilter",
      "logUpstreamFilter",
      "logErrorFilter"
    ].forEach((id) => $(id).addEventListener("input", handleLogFilterInput));
    [
      "logKindFilter",
      "logStreamFilter",
      "logAdapterFilter",
      "logShapeFilter"
    ].forEach((id) => $(id).addEventListener("change", handleLogFilterInput));
    $("logsClearFilters").addEventListener("click", () => {
      logSuccessFilter = "all";
      [
        "logSearchFilter",
        "logModelFilter",
        "logUpstreamFilter",
        "logErrorFilter"
      ].forEach((id) => { $(id).value = ""; });
      $("logKindFilter").value = "all";
      $("logStreamFilter").value = "all";
      $("logAdapterFilter").value = "all";
      $("logShapeFilter").value = "all";
      handleLogFilterInput();
    });

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
      loadAll().then(() => {
        applyAutoRefreshSetting(localStorage.getItem(autoRefreshKey) !== "0");
      }).catch((err) => showLogin(err.message));
    } else {
      showLogin();
    }
  </script>
</body>
</html>
"""
