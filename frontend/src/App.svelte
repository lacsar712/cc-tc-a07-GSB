<script>
  let session = null;
  let view = "logs";
  let logs = [];
  let windows = [];
  let blocks = [];
  let serverNow = null;
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let deltaMm = "";
  let winChainage = "";
  let winStart = "";
  let winEnd = "";
  let error = "";
  let notice = "";
  let winError = "";
  let winNotice = "";
  let loading = false;
  let timer;

  $: isWriter = session?.role === "writer";
  $: blockingNow = windows.filter((w) => w.state === "blocking");
  $: chainageBlocked = blockingNow.some(
    (w) => w.chainage === chainage.trim()
  );
  $: knownChainages = [
    ...new Set([...logs.map((r) => r.chainage), ...windows.map((w) => w.chainage)]),
  ];

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  const pad = (n) => String(n).padStart(2, "0");
  function localInputValue(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
      d.getHours()
    )}:${pad(d.getMinutes())}`;
  }
  function fmtLocal(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  }

  async function getJSON(path) {
    const res = await fetch(path, { headers: headers() });
    if (res.status === 401) {
      logout();
      return null;
    }
    return res.ok ? await res.json() : null;
  }

  async function refresh() {
    if (!session) return;
    const [logsData, winData, blockData, clockData] = await Promise.all([
      getJSON("/api/logs"),
      getJSON("/api/blast-windows"),
      getJSON("/api/blast-blocks"),
      getJSON("/api/clock"),
    ]);
    if (logsData) logs = logsData;
    if (winData) windows = winData;
    if (blockData) blocks = blockData;
    if (clockData) serverNow = clockData.now;
  }

  async function login() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "登录失败";
        return;
      }
      session = { token: data.access_token, username: data.username, role: data.role };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      await refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      error = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    windows = [];
    blocks = [];
    serverNow = null;
    localStorage.removeItem("tunnel_session");
  }

  function gotoBlast() {
    view = "blast";
    winError = "";
    winNotice = "";
    // 默认给一个覆盖当前时刻的窗模板，方便配窗；真正是否生效仍由服务端判
    if (!winStart && serverNow) {
      const start = new Date(serverNow);
      start.setSeconds(0, 0);
      const end = new Date(start.getTime() + 60 * 60 * 1000);
      winStart = localInputValue(start);
      winEnd = localInputValue(end);
    }
  }

  async function submit() {
    error = "";
    notice = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        // client_clock 仅留档：服务端不采信，本机改时间糊弄不过去
        body: JSON.stringify({
          chainage,
          delta_mm: Number(deltaMm),
          client_clock: new Date().toISOString(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        // 409 = 服务端真实拒收，原因由服务端时钟判定后给出
        error = data.detail || "提交失败";
        await refresh();
        return;
      }
      chainage = "";
      deltaMm = "";
      notice = "报送已进入待认领队列。";
      await refresh();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  async function createWindow() {
    winError = "";
    winNotice = "";
    if (!winChainage.trim()) {
      winError = "断面（桩号）不能为空";
      return;
    }
    let startsISO, endsISO;
    try {
      startsISO = new Date(winStart).toISOString();
      endsISO = new Date(winEnd).toISOString();
    } catch {
      winError = "起止时刻格式不正确";
      return;
    }
    try {
      const res = await fetch("/api/blast-windows", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({
          chainage: winChainage.trim(),
          starts_at: startsISO,
          ends_at: endsISO,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        winError = data.detail || "配窗失败";
        return;
      }
      winNotice =
        data.state === "blocking"
          ? `爆破窗已下发且即刻生效：断面 ${data.chainage} 此刻起报送一律拒收，直到窗结束。`
          : `爆破窗已下发：${data.chainage}，到点自动封锁。`;
      winChainage = "";
      await refresh();
    } catch {
      winError = "配窗时网络异常";
    }
  }

  async function revokeWindow(id) {
    winError = "";
    winNotice = "";
    try {
      const res = await fetch(`/api/blast-windows/${id}`, {
        method: "DELETE",
        headers: headers(),
      });
      const data = await res.json();
      if (!res.ok) {
        winError = data.detail || "解除失败";
        return;
      }
      winNotice = `爆破窗 #${id} 已解除，该断面报送恢复。`;
      await refresh();
    } catch {
      winError = "解除时网络异常";
    }
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      localStorage.removeItem("tunnel_session");
    }
  }
</script>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #1c1917;
    color: #f5f5f4;
  }
  main { max-width: 1100px; margin: 0 auto; padding: 1.5rem; }
  .topbar {
    display: flex; align-items: center; justify-content: space-between;
    gap: 1rem; margin-bottom: 1.25rem;
  }
  .brand { color: #fbbf24; font-size: 1.25rem; font-weight: 700; }
  nav { display: flex; gap: 0.5rem; }
  nav button { background: #44403c; font-weight: 500; }
  nav button.active { background: #d97706; font-weight: 700; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  .row { display: flex; gap: 0.75rem; }
  .row > div { flex: 1; }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  button.secondary { background: #57534e; }
  button.danger { background: #b91c1c; }
  .err { color: #fb7185; white-space: pre-wrap; }
  .ok-msg { color: #86efac; }
  .lock-banner {
    border: 1px solid #ef4444; background: #450a0a; color: #fecaca;
    border-radius: 6px; padding: 0.6rem 0.8rem; margin-bottom: 0.75rem; font-size: 0.9rem;
  }
  .clock {
    font-size: 0.9rem; color: #a8a29e; margin-bottom: 0.9rem;
  }
  .clock b { color: #fde68a; font-variant-numeric: tabular-nums; }
  .readonly-note {
    border: 1px dashed #78716c; color: #d6d3d1; border-radius: 6px;
    padding: 0.55rem 0.8rem; font-size: 0.88rem; margin-bottom: 0.75rem;
  }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; vertical-align: top; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .blocking { background: #7f1d1d; color: #fecaca; }
  .ended { background: #44403c; color: #a8a29e; }
  .mono { font-size: 0.75rem; color: #a8a29e; font-variant-numeric: tabular-nums; }
  h2 { font-size: 1.05rem; margin: 0 0 0.75rem; color: #fbbf24; }
  .empty { color: #78716c; font-size: 0.88rem; }
</style>

<main>
  {#if !session}
    <h1 class="brand">隧道收敛测缝台</h1>
    <p class="sub">测量员提交桩号与收敛毫米值，接口进程内线程认领后出结论。登录框已预填可写账号 surveyor / surv123456。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else}
    <div class="topbar">
      <span class="brand">隧道收敛测缝台</span>
      <nav>
        <button class:active={view === "logs"} on:click={() => (view = "logs")}>测缝报送</button>
        <button class:active={view === "blast"} on:click={gotoBlast}>爆破窗</button>
      </nav>
    </div>
    <p class="sub">
      已登录：{session.username}（{isWriter ? "测量员·可提交/可配窗" : "巡检员·只读，可查看不能修改"}）
      <button class="secondary" style="margin-left:0.75rem" on:click={logout}>退出</button>
    </p>

    {#if view === "logs"}
      {#if isWriter}
        <section>
          <h2>测缝报送</h2>
          {#if chainageBlocked}
            <div class="lock-banner">
              ⛔ 断面 {chainage.trim()} 正处于掌子面爆破窗内（按服务端时钟判定）。即使点提交，服务端也会真实拒收，
              请把测缝作业挪到窗外时段再送。
            </div>
          {/if}
          <label>里程桩号 / 断面</label>
          <input placeholder="例如 K20+050" bind:value={chainage} list="chainage-options" />
          <datalist id="chainage-options">
            {#each knownChainages as c}<option value={c} />{/each}
          </datalist>
          <label>收敛（毫米，可正可负）</label>
          <input type="number" step="0.1" bind:value={deltaMm} />
          <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
          {#if error}<p class="err">⛔ {error}</p>{/if}
          {#if notice}<p class="ok-msg">{notice}</p>{/if}
        </section>
      {:else}
        <section class="readonly-note">巡检员账号只读：不能提交测缝、不能配置爆破窗。下列数据与爆破窗、封锁日志均可查看。</section>
      {/if}
      <section>
        <h2>测缝记录</h2>
        <table>
          <thead>
            <tr><th>编号</th><th>桩号</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th><th>提交人</th></tr>
          </thead>
          <tbody>
            {#each logs as row}
              <tr>
                <td>{row.id}</td>
                <td>{row.chainage}</td>
                <td>{row.delta_mm}</td>
                <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待处理' : '已完成'}</span></td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
                <td>{row.reason ?? "—"}</td>
                <td>{row.created_by}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {:else}
      <section>
        <h2>爆破窗（掌子面测缝封锁）</h2>
        <div class="clock">
          服务端权威时钟：<b>{serverNow ? fmtLocal(serverNow) : "同步中…"}</b>
          （能否进窗只认此时钟，本机改时间无效）
        </div>
        {#if isWriter}
          <label>断面（桩号）</label>
          <input placeholder="选择或输入要锁死的断面，例如 K20+050" bind:value={winChainage} list="win-chainage-options" />
          <datalist id="win-chainage-options">
            {#each knownChainages as c}<option value={c} />{/each}
          </datalist>
          <div class="row">
            <div>
              <label>起始时刻</label>
              <input type="datetime-local" bind:value={winStart} />
            </div>
            <div>
              <label>结束时刻</label>
              <input type="datetime-local" bind:value={winEnd} />
            </div>
          </div>
          <button on:click={createWindow}>下发爆破窗</button>
          {#if winError}<p class="err">⛔ {winError}</p>{/if}
          {#if winNotice}<p class="ok-msg">{winNotice}</p>{/if}
        {:else}
          <div class="readonly-note">巡检员只读：爆破窗配置与解除仅测量员可操作。</div>
        {/if}
      </section>

      <section>
        <h2>当前爆破窗</h2>
        {#if windows.length === 0}
          <p class="empty">暂无爆破窗，所有断面测缝报送正常接收。</p>
        {:else}
          <table>
            <thead>
              <tr><th>编号</th><th>断面</th><th>起始</th><th>结束</th><th>状态</th><th>配置人</th>{#if isWriter}<th>操作</th>{/if}</tr>
            </thead>
            <tbody>
              {#each windows as w}
                <tr>
                  <td>{w.id}</td>
                  <td>{w.chainage}</td>
                  <td>{fmtLocal(w.starts_at)}</td>
                  <td>{fmtLocal(w.ends_at)}</td>
                  <td>
                    {#if w.state === "blocking"}
                      <span class="tag blocking">⛔ 封锁中</span>
                    {:else if w.state === "pending"}
                      <span class="tag pending">未开始</span>
                    {:else}
                      <span class="tag ended">已结束</span>
                    {/if}
                  </td>
                  <td>{w.created_by}</td>
                  {#if isWriter}
                    <td>
                      {#if w.state !== "ended"}
                        <button class="danger" on:click={() => revokeWindow(w.id)}>解除封锁</button>
                      {:else}—{/if}
                    </td>
                  {/if}
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>

      <section>
        <h2>封锁日志（窗内真实拒收流水）</h2>
        {#if blocks.length === 0}
          <p class="empty">暂无拒收记录。每次窗内报送被挡下都会在此留痕，与拒收动作同时写入。</p>
        {:else}
          <table>
            <thead>
              <tr><th>拒收时刻</th><th>断面</th><th>收敛mm</th><th>提交人</th><th>命中爆破窗</th><th>拒收原因</th><th>本机自报时刻（未采信）</th></tr>
            </thead>
            <tbody>
              {#each blocks as b}
                <tr>
                  <td><span class="mono">{fmtLocal(b.blocked_at)}</span></td>
                  <td>{b.chainage}</td>
                  <td>{b.delta_mm}</td>
                  <td>{b.submitted_by}</td>
                  <td>
                    #{b.window_id ?? "—"}<br />
                    <span class="mono">{fmtLocal(b.window_start)}<br />至 {fmtLocal(b.window_end)}</span>
                  </td>
                  <td>{b.reason}</td>
                  <td><span class="mono">{b.client_clock ? fmtLocal(b.client_clock) : "—"}</span></td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    {/if}
  {/if}
</main>
