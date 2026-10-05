<script>
  let session = null;
  let view = "logs"; // logs | blasting
  let logs = [];
  let windows = [];
  let blockades = [];
  let serverNow = null;
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let deltaMm = "";
  // 爆破窗表单
  let winChainage = "";
  let winStart = "";
  let winEnd = "";
  let error = "";
  let winError = "";
  let notice = "";
  let loading = false;
  let timer;

  $: isWriter = session?.role === "writer";
  // 报送页顶部告警：服务端此刻正处于封锁中的断面（内联判断以追踪 serverNow）
  $: activeChains = serverNow
    ? windows
        .filter((w) => serverNow >= new Date(w.starts_at) && serverNow <= new Date(w.ends_at))
        .map((w) => w.chainage)
    : [];

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function refreshLogs() {
    if (!session) return;
    const res = await fetch("/api/logs", { headers: headers() });
    if (res.status === 401) { logout(); return; }
    if (res.ok) logs = await res.json();
  }

  async function refreshBlasting() {
    if (!session) return;
    const [wres, bres, tres] = await Promise.all([
      fetch("/api/blasting-windows", { headers: headers() }),
      fetch("/api/blockade-logs", { headers: headers() }),
      fetch("/api/time"),
    ]);
    if (wres.status === 401 || bres.status === 401) { logout(); return; }
    if (wres.ok) windows = await wres.json();
    if (bres.ok) blockades = await bres.json();
    if (tres.ok) {
      const t = await tres.json();
      serverNow = new Date(t.now);
    }
  }

  async function refresh() {
    await refreshLogs();
    // 报送页也要拿到窗口与服务端时钟，才能提示哪些断面正锁死。
    await refreshBlasting();
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
    blockades = [];
    localStorage.removeItem("tunnel_session");
  }

  async function submit() {
    error = "";
    notice = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ chainage, delta_mm: Number(deltaMm) }),
      });
      const data = await res.json();
      if (!res.ok) {
        // 不是光改提示：服务端已真实拦截并写封锁日志，这里原样展示拒收理由。
        error = data.detail || "提交失败";
        if (res.status === 423) await refreshBlasting();
        return;
      }
      chainage = "";
      deltaMm = "";
      notice = "报送已进入待认领队列";
      await refreshLogs();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  function localInputToIso(value) {
    // datetime-local 给的是本机无时区时间，提交时打上本地偏移换算成绝对时刻。
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
  }

  async function addWindow() {
    winError = "";
    const section = (winChainage || "").trim();
    const startsAt = localInputToIso(winStart);
    const endsAt = localInputToIso(winEnd);
    if (!section) { winError = "断面不能为空"; return; }
    if (!startsAt || !endsAt) { winError = "请填完整起止时刻"; return; }
    try {
      const res = await fetch("/api/blasting-windows", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ chainage: section, starts_at: startsAt, ends_at: endsAt }),
      });
      const data = await res.json();
      if (!res.ok) { winError = data.detail || "创建失败"; return; }
      winChainage = "";
      winStart = "";
      winEnd = "";
      await refreshBlasting();
    } catch {
      winError = "创建时网络异常";
    }
  }

  async function removeWindow(id) {
    try {
      const res = await fetch(`/api/blasting-windows/${id}`, {
        method: "DELETE",
        headers: headers(),
      });
      if (res.status === 401) { logout(); return; }
      if (res.ok) await refreshBlasting();
    } catch {
      winError = "删除时网络异常";
    }
  }

  function fmt(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  }

  function windowState(w) {
    if (!serverNow) return "";
    const s = new Date(w.starts_at), e = new Date(w.ends_at);
    if (serverNow >= s && serverNow <= e) return "active";
    if (serverNow < s) return "upcoming";
    return "past";
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
  main { max-width: 980px; margin: 0 auto; padding: 1.5rem; }
  header.bar {
    display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
    border-bottom: 1px solid #44403c; margin-bottom: 1.25rem; padding-bottom: 0.75rem;
  }
  h1 { color: #fbbf24; margin: 0; font-size: 1.3rem; }
  nav { display: flex; gap: 0.5rem; }
  nav button { background: #44403c; }
  nav button.on { background: #d97706; }
  .spacer { flex: 1; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  section h2 { margin: 0 0 0.75rem; font-size: 1.05rem; color: #fbbf24; }
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
  button.secondary { background: #57534e; }
  button.danger { background: #b91c1c; padding: 0.25rem 0.6rem; font-size: 0.8rem; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .err { color: #fb7185; }
  .ok-msg { color: #86efac; }
  .clock { font-size: 0.85rem; color: #a8a29e; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; vertical-align: top; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; white-space: nowrap; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .active { background: #7f1d1d; color: #fecaca; }
  .upcoming { background: #1e3a8a; color: #bfdbfe; }
  .past { background: #44403c; color: #a8a29e; }
</style>

<main>
  {#if !session}
    <h1>隧道收敛测缝台</h1>
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
    <header class="bar">
      <h1>隧道收敛测缝台</h1>
      <nav>
        <button class:on={view === "logs"} on:click={() => (view = "logs")}>测缝报送</button>
        <button class:on={view === "blasting"} on:click={() => (view = "blasting")}>爆破窗</button>
      </nav>
      <div class="spacer"></div>
      <span class="clock">{session.username}（{isWriter ? "可提交" : "只读 · 巡检员"}）</span>
      <button class="secondary" on:click={logout}>退出</button>
    </header>

    {#if view === "logs"}
      <section>
        <button class="secondary" disabled={loading} on:click={refreshLogs}>刷新列表</button>
      </section>
      {#if isWriter}
        <section>
          <h2>报送收敛读数</h2>
          {#if activeChains.length > 0}
            <p class="err">
              ⚠ 服务端当前时刻有断面正处于爆破封锁窗：{activeChains.join("、")}。
              这些断面的报送会被服务端直接拒收，请挪到窗外再提交。
            </p>
          {/if}
          <label>里程桩号 / 断面</label>
          <input placeholder="例如 K20+050" bind:value={chainage} />
          <label>收敛（毫米，可正可负）</label>
          <input type="number" step="0.1" bind:value={deltaMm} />
          <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
          {#if error}<p class="err">{error}</p>{/if}
          {#if notice}<p class="ok-msg">{notice}</p>{/if}
        </section>
      {/if}
      <section>
        <h2>测缝记录</h2>
        <table>
          <thead>
            <tr><th>编号</th><th>桩号</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th></tr>
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
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {:else}
      <section>
        <h2>掌子面爆破封锁窗</h2>
        <p class="clock">
          判定以服务端时钟为准（本机改时间无效）。服务端当前时刻：
          {serverNow ? serverNow.toLocaleString("zh-CN", { hour12: false }) : "读取中…"}
        </p>
        <table>
          <thead>
            <tr><th>断面</th><th>起</th><th>止</th><th>状态</th><th>配置人</th>{#if isWriter}<th></th>{/if}</tr>
          </thead>
          <tbody>
            {#each windows as w}
              <tr>
                <td>{w.chainage}</td>
                <td>{fmt(w.starts_at)}</td>
                <td>{fmt(w.ends_at)}</td>
                <td>
                  {#if windowState(w) === "active"}
                    <span class="tag active">封锁中 · 报送锁死</span>
                  {:else if windowState(w) === "upcoming"}
                    <span class="tag upcoming">未开始</span>
                  {:else}
                    <span class="tag past">已结束</span>
                  {/if}
                </td>
                <td>{w.created_by}</td>
                {#if isWriter}
                  <td><button class="danger" on:click={() => removeWindow(w.id)}>删除</button></td>
                {/if}
              </tr>
            {/each}
            {#if windows.length === 0}
              <tr><td colspan="6" class="clock">暂无爆破窗配置</td></tr>
            {/if}
          </tbody>
        </table>
      </section>

      {#if isWriter}
        <section>
          <h2>配置爆破窗</h2>
          <label>断面（桩号）</label>
          <input placeholder="例如 K20+050" bind:value={winChainage} />
          <div class="row">
            <div>
              <label>起始时刻</label>
              <input type="datetime-local" step="1" bind:value={winStart} />
            </div>
            <div>
              <label>结束时刻</label>
              <input type="datetime-local" step="1" bind:value={winEnd} />
            </div>
          </div>
          <button on:click={addWindow}>配好时段并锁死该断面</button>
          {#if winError}<p class="err">{winError}</p>{/if}
        </section>
      {:else}
        <section>
          <p class="clock">巡检员只读：可查看爆破窗与封锁日志，不能配置或删除。</p>
        </section>
      {/if}

      <section>
        <h2>封锁日志（真实拒收留痕）</h2>
        <table>
          <thead>
            <tr><th>编号</th><th>窗口</th><th>断面</th><th>收敛mm</th><th>拒收时刻(服务端)</th><th>报送人</th><th>拒收说明</th></tr>
          </thead>
          <tbody>
            {#each blockades as b}
              <tr>
                <td>{b.id}</td>
                <td>#{b.window_id}</td>
                <td>{b.chainage}</td>
                <td>{b.delta_mm}</td>
                <td>{fmt(b.server_time)}</td>
                <td>{b.blocked_by}</td>
                <td>{b.reason}</td>
              </tr>
            {/each}
            {#if blockades.length === 0}
              <tr><td colspan="7" class="clock">暂无封锁拒收记录</td></tr>
            {/if}
          </tbody>
        </table>
      </section>
    {/if}
  {/if}
</main>
