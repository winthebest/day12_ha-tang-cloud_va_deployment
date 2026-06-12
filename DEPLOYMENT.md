# Deployment Information

## Public URL

### Local production stack (đã verify)

```
http://localhost
```

Stack chạy bằng Docker Compose trong `06-lab-complete/`:

```bash
cd 06-lab-complete
docker compose up -d --scale agent=3
```

### Cloud URL (Railway / Render)

Sau khi deploy lên cloud, cập nhật URL tại đây:

```
https://giving-wholeness-production-554f.up.railway.app/
```



## Platform

- **Local:** Docker Compose (agent × 3 + Redis + Nginx)
- **Cloud:** Railway (khuyến nghị) hoặc Render (`render.yaml` có sẵn)

## Test Commands

### Health Check

```bash
curl https://giving-wholeness-production-554f.up.railway.app/health
```

Expected:

```json
{"status":"ok","redis_connected":true,"version":"1.0.0"}
```

### Readiness Check

```bash
curl https://giving-wholeness-production-554f.up.railway.app/ready
```

Expected:

```json
{"ready":true,"instance_id":"instance-2"}
```

### Authentication required (401)
![Authentication_required](Authentication_required.png)

### API Test (with authentication)



Expected: HTTP 200 với `answer`, `turn`, `history_count`.

### Rate limiting (429 after 10 requests)





## Self-Test Results (12/06/2026)

| Test | Result |
|------|--------|
| `check_production_ready.py` | 20/20 ✅ |
| `GET /health` | 200 ✅ |
| `GET /ready` | 200 ✅ |
| `POST /ask` without key | 401 ✅ |
| `POST /ask` with key | 200 ✅ |
| Rate limit 11th request | 429 ✅ |
| Image size | 247 MB (< 500 MB) ✅ |
