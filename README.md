# 隧道收敛测缝台

测量员登记里程桩号与收敛毫米值。接口进程内后台线程认领待判行（不另起 worker 容器），按绝对值是否不超过 3.0 mm 给出合格或超限。页面是 Svelte。

## 技术栈

- 后端：Flask、Gunicorn、SQLAlchemy、进程内认领线程
- 前端：Svelte、Vite、nginx 反代 `/api`
- 数据库：PostgreSQL 16

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3201 |
| 接口 | http://localhost:8201 |
| PostgreSQL | localhost:54401（库名 `tunnelconv`） |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| surveyor | surv123456 | 可提交 |
| inspector | insp123456 | 只读 |

## 启动

```bash
cd projects/21-tunnel-convergence-desk
docker compose up --build
```

健康检查：`GET http://localhost:8201/api/health`

## 爆破封锁窗

掌子面爆破时段，该断面的测缝报送整体锁死。

- 页眉「爆破窗」专页：测量员选断面、填起止时刻配窗，下方挂封锁日志；巡检员能看不能改（写操作返回 403）。
- 服务端时钟是唯一判定依据（`GET /api/time`），客户端本机时间无法绕过。
- 当前服务端时刻落在该断面任一窗内时，`POST /api/logs` 一律返回 **423 Locked**，不创建测缝记录，同时写入一条封锁日志（`blockade_logs`）；提示把报送挪到窗外再收。
- 删除窗口或等时刻移出窗外后，同断面报送恢复 201，正常进待认领队列。

接口：`GET/POST /api/blasting-windows`、`DELETE /api/blasting-windows/<id>`、`GET /api/blockade-logs`、`GET /api/time`。

## 种子

| 桩号 | 收敛 | 结论 |
|------|------|------|
| K12+180 | 1.2 mm | 合格 |
| K18+040 | 5.6 mm | 超限 |
