# AdaCascade Docker Compose 部署指南

本文是 AdaCascade 的通用 Docker Compose 部署说明，适用于课题组服务器和其他具备 Docker + GPU 运行环境的主机。实验室目标服务器的硬件、网络、端口和磁盘约束单独记录在 [`LAB_SERVER.md`](LAB_SERVER.md)。

> 本文描述 Docker 部署流程；本地非 Docker 开发流程见仓库顶层 [`README.md`](../README.md)。

---

## 1. 部署前提

- Docker Engine 与 Docker Compose plugin；
- NVIDIA Container Toolkit，可让 Docker 容器访问 GPU；
- 已拉取 AdaCascade 仓库；
- 可用的运行时数据目录，推荐使用数据盘，例如 `/data/xiaoyunhao/adacascade/runtime`；
- 可用的 OpenAI-compatible LLM endpoint，或宿主机本地 vLLM 服务。

课题组服务器上 Docker Root Dir 当前位于系统盘 `/var/lib/docker`，系统盘空间紧张时应联系管理员迁移 Docker `data-root` 到 `/data/docker`，或谨慎清理悬空镜像。

---

## 2. Compose 服务结构

仓库根目录的 [`docker-compose.yml`](../docker-compose.yml) 定义三个服务：

| 服务 | 作用 | 端口/网络 |
|---|---|---|
| `qdrant` | 表级与列级向量存储 | 仅在 Compose 网络内可见，默认不发布宿主机端口 |
| `backend` | FastAPI + LangGraph 后端，内部端口 `8080` | 通过 frontend Nginx 的 `/api/` 代理访问 |
| `frontend` | React 静态资源 + Nginx | 默认发布为 `${ADACASCADE_FRONTEND_PORT:-13000}:80` |

[`deploy/nginx.conf`](nginx.conf) 的行为：

- `/` 使用 SPA fallback：`try_files $uri $uri/ /index.html`；
- `/api/` 代理到 `http://backend:8080/`；
- 关闭代理缓冲，支持任务事件流；
- 上传大小限制为 `256m`。

Qdrant 不对宿主机发布端口，部署后通过 backend 在 Compose 网络内访问 `http://qdrant:6333`。

---

## 3. 配置与 `.env`

`.env` 对 `docker compose config` 是可选的，因为 Compose 文件使用了 `env_file.required: false`。真实部署仍建议创建 `.env`，并在部署主机本地保存。

```bash
cp .env.example .env
# 编辑 .env；不要提交真实 .env
```

部署时重点配置项：

| 配置项 | 用途 |
|---|---|
| `API_KEY` | 后端鉴权 token；frontend 构建时会嵌入同一个值 |
| `ADACASCADE_FRONTEND_PORT` | frontend 对外端口，默认 `13000` |
| `ADACASCADE_RUNTIME_DIR` | 容器挂载的运行时数据根目录 |
| `CORS_ALLOW_ORIGINS` | 允许访问后端的前端来源 |
| `LLM_BASE_URL` | API 模型 OpenAI-compatible endpoint |
| `LLM_MODEL` | API 模型名称 |
| `LLM_LOCAL_BASE_URL` | local 模型 endpoint，Compose 默认指向宿主机 `8000` |
| `PYTORCH_BASE_IMAGE` | backend 基础镜像，可按服务器驱动兼容性覆盖 |
| `NVIDIA_VISIBLE_DEVICES` | 指定容器可见 GPU |
| `SBERT_DEVICE` | SBERT 运行设备，例如容器内 `cuda:0` |
| `HF_ENDPOINT` | HuggingFace 镜像地址 |
| `PIP_INDEX_URL` | PyPI 镜像地址 |
| `NPM_CONFIG_REGISTRY` | npm 镜像地址 |
| `NO_PROXY` / `no_proxy` | localhost、Qdrant 和 host gateway 代理绕过列表 |

安全要求：

- 真实 `.env`、API token、外部 LLM 凭据和代理凭据都不能提交到 git；
- 修改 `API_KEY` 后必须重新构建 frontend，因为 demo UI 的 bearer token 在构建时注入；
- 不要把开发默认 token 用于公网部署。

---

## 4. 运行时数据目录

默认运行时目录：

```text
${ADACASCADE_RUNTIME_DIR:-/data/xiaoyunhao/adacascade/runtime}
```

建议提前创建：

```bash
mkdir -p /data/xiaoyunhao/adacascade/runtime/{tables,artifacts,qdrant,logs}
```

主要内容：

| 子路径 | 用途 |
|---|---|
| `tables/` | 上传表转存后的 Parquet 文件 |
| `artifacts/` | TF-IDF、相似度矩阵等 pickle 制品 |
| `qdrant/` | Qdrant 向量库持久化数据 |
| `metadata.db` | SQLite 元数据库 |
| `ckpt.db` | LangGraph checkpoint SQLite 数据库 |
| `logs/` | 本地 vLLM 或服务日志 |

---

## 5. 镜像、CUDA 与依赖策略

后端默认基础镜像：

```text
pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime
```

这样可以避免默认使用 CUDA 12.4+，以适配 NVIDIA Driver 535 这类最高只支持 CUDA 12.2 的服务器。

后端 Docker 镜像安装 [`requirements.backend.txt`](../requirements.backend.txt)，而不是完整的 [`requirements.txt`](../requirements.txt)。原因：

- Docker 后端默认连接外部 OpenAI-compatible LLM endpoint；
- 不需要在 backend 容器内安装本地 vLLM；
- 避免 `vllm==0.8.5` / `torch==2.6.0` 触发 CUDA 12.4 wheel 栈；
- PyTorch/CUDA runtime 由 `PYTORCH_BASE_IMAGE` 提供。

如果目标服务器已经验证了其他 CUDA 12.1/12.2 兼容镜像，可以在 `.env` 中覆盖 `PYTORCH_BASE_IMAGE`。在 Driver 535 服务器上不要使用 CUDA 12.4+ 镜像。

---

## 6. 国内网络镜像与代理

Compose 默认配置了国内可用的镜像源：

| 类型 | 默认值 |
|---|---|
| PyPI | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| HuggingFace | `https://hf-mirror.com` |
| npm | `https://registry.npmmirror.com` |

代理绕过列表需要包含容器内部服务名和宿主机 gateway：

```text
localhost,127.0.0.1,qdrant,host.docker.internal
```

如果宿主机有 HTTP/SOCKS 代理，容器访问宿主机代理时通常使用 `host.docker.internal:<proxy-port>`。同时保留 `NO_PROXY` / `no_proxy`，避免 Qdrant、localhost 和 host gateway 被错误代理。

---

## 7. LLM 运行时矩阵

| 场景 | endpoint | 用途 | 说明 |
|---|---|---|---|
| 本地 vLLM 开发 | `http://localhost:8000/v1` | 本地模型调试 | 通过 `bash scripts/start_llm.sh` 启动 |
| Docker 连接宿主机 vLLM | `http://host.docker.internal:8000/v1` | 容器访问宿主机本地模型 | Compose 默认 `LLM_LOCAL_BASE_URL` / `LLM_BASE_URL` 使用该地址 |
| 外部 API 模型 | 部署本地配置 | 生产或公网可访问服务 | 可使用 DeepSeek 或其他 OpenAI-compatible endpoint |

后端支持 local/API runtime switching：

- 切换到 local 时，会等待本地 vLLM ready；
- 如果本地 vLLM 未启动，冷启动会较慢；
- 切换到 API 时，会停止由 AdaCascade manager 托管启动的本地 vLLM；
- 本地 vLLM 无请求超过默认 `900s` 会 idle stop；
- 前端会显示本地 vLLM 状态，便于判断切换是否会冷启动。

---

## 8. 启动流程

从仓库根目录执行：

```bash
docker compose config
docker compose build
docker compose up -d qdrant
docker compose run --rm backend python scripts/init_db.py
docker compose run --rm backend python scripts/init_qdrant.py
docker compose up -d
docker compose logs -f backend
```

如果只更新代码：

```bash
git pull
docker compose build backend frontend
docker compose up -d
```

如果仅重启后端：

```bash
docker compose restart backend
docker compose logs -f backend
```

---

## 9. TF-IDF 重建

上传数据或批量导入 demo / benchmark 数据后，运行 Discover / Integrate 前显式重建 TF-IDF。

默认租户：

```bash
docker compose run --rm backend python scripts/rebuild_tfidf.py --tenant-id default --corpus all
```

Benchmark JOIN / UNION 语料：

```bash
docker compose run --rm backend python scripts/rebuild_tfidf.py --tenant-id benchmark --corpus join
docker compose run --rm backend python scripts/rebuild_tfidf.py --tenant-id benchmark --corpus union
```

---

## 10. Smoke test

1. 打开：

   ```text
   http://SERVER_IP:13000/?tenant_id=default
   ```

2. 确认 Dataset selector 可见且可切换。
3. 确认模型切换区域显示 local/API 后端和本地 vLLM 状态。
4. 上传或选择一组 READY 表。
5. 运行一个小规模 Discover 或 Integrate 任务。
6. 查看候选排序、列映射和四智能体执行轨迹。
7. 观察后端日志：

   ```bash
   docker compose logs -f backend
   ```

8. 检查后端健康接口：

   ```bash
   docker compose exec backend python - <<'PY'
   import urllib.request
   print(urllib.request.urlopen('http://localhost:8080/healthz', timeout=5).read().decode())
   PY
   ```

如果使用宿主机本地 vLLM，还应在宿主机检查：

```bash
curl --noproxy '*' http://localhost:8000/v1/models
```

---

## 11. 常见问题

### 前端页面能打开，但 API 请求失败

检查：

- frontend 是否按最新 `API_KEY` 重新构建；
- Nginx `/api/` 是否代理到 `backend:8080`；
- `CORS_ALLOW_ORIGINS` 是否包含实际访问入口；
- backend 日志是否出现鉴权或路由错误。

### Qdrant 连接失败

检查：

```bash
docker compose ps qdrant
docker compose logs qdrant
docker compose exec backend python scripts/init_qdrant.py
```

确认 backend 中的 `QDRANT_URL` 是 `http://qdrant:6333`，且 `NO_PROXY` 包含 `qdrant`。

### 切换到本地模型耗时很久

如果前端显示本地 vLLM 状态为“未启动”或“启动中”，切换到 local 会触发冷启动和 readiness 轮询。状态为“已启动 / ready”时切换应明显更快。

### GPU / CUDA 不兼容

Driver 535 服务器不要使用 CUDA 12.4+ 镜像。优先使用 CUDA 12.1/12.2 兼容的 `PYTORCH_BASE_IMAGE`，并确认 `NVIDIA_VISIBLE_DEVICES` 指向可用 GPU。

### Docker 构建或拉取镜像导致系统盘不足

当前 Docker Root Dir 如果在 `/var/lib/docker`，会占用系统盘。建议联系管理员迁移到 `/data/docker`。临时缓解可查看空间并清理悬空镜像：

```bash
docker system df
docker image prune -f
```

不要删除共享服务正在使用的镜像、卷或容器。

### 后端不要开多 worker

FastAPI backend 必须保持单 worker。不要为了吞吐量把 uvicorn 改成多 worker，否则 LangGraph 状态、BackgroundTasks 和本地 LLM runtime manager 可能出现进程间状态不一致。

---

## 12. 课题组服务器

课题组服务器的已知事实、端口占用、GPU 约束、访问方式和本地运维命令见 [`LAB_SERVER.md`](LAB_SERVER.md)。其中的服务器 profile 可能包含已验证的服务器专用镜像或路径；通用部署默认值与服务器 profile 不一致时，以服务器实际验证结果为准，但必须保持 Driver 535 的 CUDA 12.1/12.2 兼容约束。
