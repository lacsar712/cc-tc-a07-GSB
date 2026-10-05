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

## 种子

| 桩号 | 收敛 | 结论 |
|------|------|------|
| K12+180 | 1.2 mm | 合格 |
| K18+040 | 5.6 mm | 超限 |

## 掌子面爆破窗封锁

页眉「爆破窗」专页：测量员选断面（桩号）并填起止时刻下发爆破窗，窗内该断面测缝报送整体锁死。

- 窗内报送由**服务端**在 `POST /api/logs` 真实拒收（HTTP 409），拒收与封锁日志（`blast_blocks`）同事务写入，前端不改出“能报”的假象。
- 是否在窗内只看 `GET /api/clock` 的服务端时钟（`datetime.now(UTC)`），请求体里的 `client_clock` 仅留档，不参与判定。
- 拒收提示明确要求把该断面测缝作业挪到窗外时段；窗未开始 / 已结束 / 解除后，报送恢复 201，认领判定照常。
- 巡检员（inspector）可查看爆破窗与封锁日志，不能配窗、不能解除、不能报送（写操作 403）。
- 接口：`GET/POST /api/blast-windows`、`DELETE /api/blast-windows/{id}`、`GET /api/blast-blocks`、`GET /api/clock`。

