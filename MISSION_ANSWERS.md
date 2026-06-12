# Day 12 Lab - Mission Answers

> **Student Name:** _(điền tên của bạn)_  
> **Student ID:** _(điền MSSV)_  
> **Date:** 12/06/2026

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

1. **API key hardcode** — `OPENAI_API_KEY` và `DATABASE_URL` ghi trực tiếp trong source code; push lên Git sẽ lộ secret.
2. **Không có config management** — `DEBUG`, `MAX_TOKENS` cố định, không đọc từ environment.
3. **Logging không an toàn** — dùng `print()` và log cả API key ra console.
4. **Không có health check** — platform không biết khi nào cần restart container.
5. **Port và host cố định** — `host="localhost"`, `port=8000`, không đọc `PORT` từ env (Railway/Render inject `PORT`).
6. **Debug reload trong production** — `reload=True` không phù hợp khi deploy.
7. **Không xử lý graceful shutdown** — tắt process đột ngột, request đang xử lý có thể bị cắt.

### Exercise 1.3: Comparison table

| Feature | Basic (develop) | Production (advanced) | Tại sao quan trọng? |
|---------|-----------------|----------------------|---------------------|
| Config | Hardcode trong code | Environment variables (`config.py` + `.env`) | Tách secret khỏi code, deploy linh hoạt giữa dev/staging/prod |
| Health check | Không có | `GET /health` + `GET /ready` | Platform biết khi restart hoặc ngừng route traffic |
| Logging | `print()` debug | Structured JSON logging | Dễ parse, search, alert trong Datadog/Loki |
| Shutdown | Đột ngột | Graceful via `lifespan` + SIGTERM | Hoàn thành request trước khi container tắt |
| Host binding | `localhost` | `0.0.0.0` | Container nhận traffic từ bên ngoài |
| Port | Cố định 8000 | `PORT` env var | Tương thích Railway, Render, Cloud Run |
| CORS | Không có | Configurable origins | Kiểm soát client nào được gọi API |
| Secrets in logs | Log API key | Không log secrets | Tránh lộ credential trong log aggregator |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. **Base image:** `python:3.11` (full image ~1 GB)
2. **Working directory:** `/app`
3. **Tại sao COPY requirements.txt trước?** Docker layer cache — nếu chỉ code thay đổi, layer `pip install` được tái sử dụng, build nhanh hơn.
4. **CMD vs ENTRYPOINT:**
   - `CMD` — lệnh mặc định, có thể override khi `docker run`
   - `ENTRYPOINT` — executable cố định; args từ `docker run` được append vào
   - Kết hợp: ENTRYPOINT định nghĩa binary, CMD định nghĩa args mặc định

### Exercise 2.3: Image size comparison

| Image | Size |
|-------|------|
| Develop (`my-agent:develop`) | **1660 MB** (1.66 GB) |
| Production (`my-agent:production`) | **236 MB** |
| Lab 06 complete (`06-lab-complete-agent`) | **247 MB** |

- **Difference:** Production nhỏ hơn ~**86%** so với develop
- **Lý do:** Multi-stage build — stage `builder` chứa gcc/build tools; stage `runtime` chỉ copy `site-packages` + source code lên `python:3.11-slim`

### Exercise 2.4: Docker Compose architecture

```
Client → Nginx (:80) → Agent (FastAPI :8000)
                    ↘ Redis (:6379)
                    ↘ Qdrant (:6333)  [trong stack 02-docker/production]
```

- **Services:** `agent`, `redis`, `qdrant`, `nginx`
- **Communication:** Nginx reverse proxy tới `agent:8000`; agent dùng `REDIS_URL=redis://redis:6379` qua Docker internal network
- **Test:** `curl http://localhost/health` qua Nginx

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- **URL:** _(deploy bằng `railway up` trong `06-lab-complete` — xem DEPLOYMENT.md)_
- **Local stack (đã verify):** `http://localhost` qua Docker Compose + Nginx

**Lệnh deploy Railway:**

```bash
cd 06-lab-complete
railway login
railway init
railway variables set AGENT_API_KEY=your-secret-key
railway variables set REDIS_URL=redis://...
railway up
railway domain
```

### Exercise 3.2: So sánh `render.yaml` vs `railway.toml`

| Khía cạnh | Railway (`railway.toml`) | Render (`render.yaml`) |
|-----------|--------------------------|------------------------|
| Format | TOML, gọn | YAML Blueprint, mô tả full infrastructure |
| Build | `builder = "DOCKERFILE"` | `buildCommand` hoặc auto-detect runtime |
| Start | `startCommand` explicit | `startCommand` trong service definition |
| Health | `healthcheckPath` | `healthCheckPath` |
| Redis | Add-on riêng, set `REDIS_URL` manual | Khai báo `type: redis` trong cùng blueprint |
| Secrets | Dashboard / CLI | `sync: false`, `generateValue: true` |
| Region | Railway chọn auto | Chỉ định `region: singapore` |

---

## Part 4: API Security

### Exercise 4.1-4.3: Test results

**Không có API key → 401:**

```json
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

**Có API key → 200:**

```json
{
  "question": "What is Docker?",
  "answer": "Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!",
  "user_id": "student1",
  "turn": 1,
  "history_count": 2
}
```

**Rate limiting (10 req/min) → 429 từ request thứ 11:**

```
Request 1-10 : 200
Request 11-15 : 429
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":58}}
```

**JWT (production `04-api-gateway`):**

- Algorithm trong `rate_limiter.py`: **Sliding Window** (deque timestamps)
- Limit user: **10 req/phút**; admin: **100 req/phút** (`rate_limiter_admin`)
- Bypass admin: dùng `rate_limiter_admin` thay vì `rate_limiter_user` khi role = admin

### Exercise 4.4: Cost guard implementation

Đã implement trong `06-lab-complete/app/cost_guard.py`:

- Mỗi user có budget **$10/tháng** (`MONTHLY_BUDGET_USD`)
- Key Redis: `budget:{user_id}:{YYYY-MM}`
- Trước khi gọi LLM: đọc spending hiện tại, nếu `current + estimated_cost > 10` → **HTTP 402**
- Sau khi pass: `INCRBYFLOAT` + `EXPIRE` 32 ngày (tự reset đầu tháng mới)

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health & Readiness

- **`GET /health`** — liveness: process OK, Redis ping (status `ok` / `degraded`)
- **`GET /ready`** — readiness: `_is_ready == True` và Redis available; trả **503** nếu chưa sẵn sàng

**Test result:**

```json
{"status":"ok","redis_connected":true,"uptime_seconds":16.8}
{"ready":true,"instance_id":"instance-1"}
```

### Exercise 5.2: Graceful shutdown

- `lifespan` shutdown: set `_is_ready = False`, chờ `_in_flight_requests` về 0 (timeout 30s)
- `signal.signal(SIGTERM, _handle_signal)` — log event, uvicorn `timeout_graceful_shutdown=30`

### Exercise 5.3: Stateless design

- Conversation history lưu Redis: `history:{user_id}` (list, max 20 messages)
- Rate limit: Redis sorted set `ratelimit:{user_id}`
- Budget: Redis key `budget:{user_id}:{month}`
- **Không** lưu state trong Python dict/memory → scale nhiều instance an toàn

### Exercise 5.4: Load balancing

```bash
docker compose up -d --scale agent=3
```

- 3 agent containers + 1 Nginx upstream `agent:8000` (Docker DNS round-robin)
- Header `X-Served-By` / `X-Instance-Id` cho thấy instance nào xử lý request

### Exercise 5.5: Stateless test

- Request 1 với `user_id=student1` → `turn: 1`
- Request 2 cùng `user_id` → `turn: 2`, `history_count` tăng
- History persist trong Redis — bất kỳ instance nào cũng đọc được

---

## Part 6: Final Project

### Production readiness check

```bash
cd 06-lab-complete
python check_production_ready.py
# Result: 20/20 checks passed (100%)
```

### Checklist hoàn thành

- [x] Multi-stage Dockerfile (< 500 MB) — **247 MB**
- [x] API key authentication
- [x] Rate limiting 10 req/min (Redis sliding window)
- [x] Cost guard $10/month/user (Redis)
- [x] Health + readiness endpoints
- [x] Graceful shutdown (SIGTERM)
- [x] Stateless design (Redis)
- [x] Structured JSON logging
- [x] Docker Compose + Nginx load balancer
- [x] `railway.toml` + `render.yaml`
