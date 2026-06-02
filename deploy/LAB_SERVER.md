# 课题组 AdaCascade 部署服务器档案

**主机名：** kemove-ESC4000-E10

**部署用户：** xiaoyunhao

**信息来源：** 用户提供的服务器巡检信息

**最后更新：** 2026-06-01

> 本文记录课题组目标部署服务器的已知环境约束，供 AdaCascade 后续部署、排障和容量规划使用。不要在本文或仓库中记录 `.env` 的真实密钥、令牌或密码。

---

## 1. 操作系统与基础软件

| 项目 | 值 |
|---|---|
| 发行版 | Ubuntu 20.04.6 LTS (Focal Fossa) |
| 内核版本 | 5.15.0-139-generic |
| 用户权限 | 普通用户，无 sudo |
| 系统包管理 | apt；安装/升级系统包需要管理员 |
| 系统 Python | 3.8.10 |
| Conda | Miniconda，安装于 `/data/xiaoyunhao/miniconda3`（Python 3.13） |
| Node.js | 20.20.2 |
| npm | 10.8.2 |

### 运维影响

- 不能依赖 sudo、systemd 或系统级 apt 安装流程。
- Python 服务优先通过 Docker 或项目自带环境运行，不依赖系统 Python 3.8。
- 前端构建可使用 Docker 中的 Node 镜像；宿主机 Node 版本仅作为参考。

---

## 2. 硬件资源

### CPU 与内存

| 项目 | 值 |
|---|---|
| CPU 核数 | 128 核 |
| 内存 | 251 GB |
| Swap | 无 |

### 磁盘

| 挂载点 | 设备/文件系统 | 容量 | 已用 | 可用 | 备注 |
|---|---|---:|---:|---:|---|
| `/` | `/dev/nvme0n1p2` | 1.8 TB | ~1.65 TB | ~109 GB | 系统盘，约 94% 已用，勿存大文件 |
| `/data` | `/dev/sda` | 3.6 TB | ~2.2 TB | ~1.3 TB | 数据盘，所有项目数据、模型、运行时文件应放这里 |

### GPU

| GPU | 型号 | 显存 | 当前占用 | 备注 |
|---|---|---:|---:|---|
| GPU 0 | NVIDIA A100-SXM4-40GB | 40 GB | ~30 GB | 主要被 sunhuabin 的 vLLM 占用 |
| GPU 1 | NVIDIA A100-SXM4-40GB | 40 GB | ~10 GB | Ollama 占用一部分；AdaCascade 固定使用此卡 |

| 项目 | 值 |
|---|---|
| NVIDIA Driver | 535.230.02 |
| 驱动支持的最高 CUDA | 12.2 |
| NVIDIA Container Toolkit | 已安装，Docker 可用 GPU |

### 关键约束

- Driver 535.x 最高支持 CUDA 12.2，部署镜像禁止默认使用 CUDA 12.4+，例如 `pytorch/pytorch:2.6.0-cuda12.4-*`。
- AdaCascade 后端容器应通过 `NVIDIA_VISIBLE_DEVICES=1` 使用物理 GPU 1；容器内通常表现为 `cuda:0`。
- 系统盘空间紧张，运行时数据、模型缓存、Docker 大对象应尽量放到 `/data/xiaoyunhao/` 或联系管理员迁移 Docker `data-root`。

---

## 3. 网络与端口

| 项目 | 值 |
|---|---|
| 公网 IP | 218.199.69.88 |
| 出口路由 | 218.199.69.254（enp1s0f0） |
| Docker 网桥 IP | 172.17.0.1 / 172.18.0.1 / 172.19.0.1 |
| DeepSeek API | 可直达 |
| HuggingFace | 需使用 `https://hf-mirror.com` |
| PyPI | 需使用清华镜像 `https://pypi.tuna.tsinghua.edu.cn/simple` |
| npm | 需使用 `https://registry.npmmirror.com` |
| HTTP/SOCKS 代理 | Mihomo/Clash，宿主机端口 7897 |

### 已知占用端口

| 端口 | 服务 | 备注 |
|---:|---|---|
| 3306 | MySQL (`bresaas-mysql`) | Docker 容器 |
| 6379 | Redis (`bresaas-redis`) | Docker 容器，仅本地 |
| 7778-7779 | `bresaas-nginx` | Docker 容器 |
| 7897 | Mihomo 代理 | HTTP/SOCKS 代理 |
| 8000 | vLLM（sunhuabin 的 Qwen3-14B） | 公网可访问，但非 AdaCascade 专属 |
| 8088 | 未知服务 | 已占用 |
| 13000 | AdaCascade 前端 | 本项目；防火墙未开放时需 SSH 隧道访问 |

### 代理使用

- PyPI/npm 优先走国内镜像，不需要代理。
- HuggingFace/SBERT 优先走 `hf-mirror.com`，必要时通过宿主机代理。
- 容器访问宿主机代理时使用 `host.docker.internal:7897`，并确保 Compose 配置包含：

```dotenv
NO_PROXY=localhost,127.0.0.1,qdrant,host.docker.internal
no_proxy=localhost,127.0.0.1,qdrant,host.docker.internal
```

---

## 4. Docker 环境

| 项目 | 值 |
|---|---|
| Docker | 28.1.1 |
| Docker Compose | v2.33.1 |
| Docker Root Dir | `/var/lib/docker`（系统盘） |
| NVIDIA Runtime | 已配置（`runtimes: nvidia`） |
| 用户组 | `xiaoyunhao` 已加入 docker 组 |
| 镜像源 | hub.rat.dev、阿里云、DaoCloud 等多个镜像源 |

### 运维影响

- 当前 Docker Root Dir 位于系统盘，构建和拉取镜像会继续消耗 `/` 空间。
- 若系统盘继续告急，需要联系管理员把 Docker `data-root` 迁移到 `/data/docker`。
- 清理悬空镜像可缓解空间压力，但不应删除共享服务正在使用的镜像和卷。

---

## 5. 共享服务

### Docker 容器

| 容器名 | 镜像 | 端口 | 用途 |
|---|---|---|---|
| `bresaas-mysql` | `mysql:8.0.33` | 3306 | 课题组 MySQL |
| `bresaas-redis` | `redis:latest` | 6379（本地） | 课题组 Redis |
| `bresaas-nginx` | `nginx:latest` | 7778-7779 | 课题组 Nginx |
| `mihomo` | `metacubex/mihomo` | 7897 | HTTP/SOCKS 代理 |

### 宿主机非 Docker 服务

| 服务 | 模型 | 端口 | GPU | 用户 | 备注 |
|---|---|---:|---|---|---|
| vLLM | Qwen3-14B-agri-awq（`/data/sunhuabin/...`） | 8000 | GPU 0 | sunhuabin | 共享服务，不稳定，AdaCascade 当前不依赖它作为主 LLM 后端 |
| Ollama | 未知 | - | GPU 1 | 系统 | 与 AdaCascade 共享 GPU 1 显存 |

---

## 6. AdaCascade 部署路径

| 用途 | 路径 |
|---|---|
| 代码仓库 | `~/AdaC`（`/home/xiaoyunhao/AdaC`） |
| 运行时数据根目录 | `/data/xiaoyunhao/adacascade/runtime/` |
| 表文件（Parquet） | `/data/xiaoyunhao/adacascade/runtime/tables/` |
| Qdrant 向量存储 | `/data/xiaoyunhao/adacascade/runtime/qdrant/` |
| SQLite 元数据库 | `/data/xiaoyunhao/adacascade/runtime/metadata.db` |
| 制品（pkl） | `/data/xiaoyunhao/adacascade/runtime/artifacts/` |
| 日志 | `/data/xiaoyunhao/adacascade/runtime/logs/` |
| Qwen3.5-9B 模型目录 | `/data/xiaoyunhao/models/Qwen/Qwen3.5-9B/` |

---

## 7. AdaCascade Docker 服务

| 容器 | 镜像 | 端口 | 说明 |
|---|---|---|---|
| `adac-backend-1` | `adac-backend:latest` | 内部 8080 | FastAPI + LangGraph，单 worker |
| `adac-frontend-1` | `adac-frontend:latest` | 宿主机 13000 | React + Nginx |
| `adac-qdrant-1` | `qdrant/qdrant:v1.17.1` | 内部 6333 | 向量数据库，不对宿主机发布端口 |

---

## 8. AdaCascade `.env` 配置要点

真实 `.env` 必须只保留在部署服务器本地，不能提交到 git。下表只记录非敏感配置和应设置项；API token 的真实值不得写入仓库。

| 配置项 | 推荐/服务器值 | 说明 |
|---|---|---|
| `API_KEY` | 已在服务器 `.env` 配置，真实值不入库 | 前端构建时会嵌入同一个 token；修改后需重建 frontend |
| `LLM_BASE_URL` | `https://api.deepseek.com` | 当前 AdaCascade 主 LLM 后端 |
| `LLM_MODEL` | `deepseek-chat` | DeepSeek chat 模型 |
| `SBERT_DEVICE` | `cuda:0` | 容器内 GPU 编号；对应物理 GPU 1 |
| `NVIDIA_VISIBLE_DEVICES` | `1` | 固定使用物理 GPU 1 |
| `PYTORCH_BASE_IMAGE` | `pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime` | 服务器当前可用的 Driver 535 兼容 PyTorch 镜像；仓库默认也必须保持 CUDA 12.1/12.2 以内 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | HuggingFace 镜像 |
| `PIP_INDEX_URL` | `https://pypi.tuna.tsinghua.edu.cn/simple` | PyPI 清华镜像 |
| `NPM_CONFIG_REGISTRY` | `https://registry.npmmirror.com` | npm 镜像 |
| `ADACASCADE_FRONTEND_PORT` | `13000` | 前端宿主机端口 |
| `CORS_ALLOW_ORIGINS` | `http://218.199.69.88:13000` | 如通过 SSH 隧道访问，也可按实际访问入口调整 |

### 与通用部署文档的差异

本文是课题组服务器 profile，不是通用默认配置。通用 Docker Compose 文档中的默认值适合干净部署起点；本文件记录的是这台服务器已经确认或需要特别遵守的约束。

- 通用 Compose 默认后端基础镜像为 `pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime`。
- 本服务器 profile 可继续使用已验证的 `pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime`，前提是实际构建和运行已验证通过。
- 两者都保持在 CUDA 12.1/12.2 兼容范围内，符合 Driver 535.230.02 的最高 CUDA 12.2 限制。
- 不要在本服务器上改用 CUDA 12.4+ 镜像，例如 `pytorch/pytorch:2.6.0-cuda12.4-*`。
- AdaCascade 仍应使用 `NVIDIA_VISIBLE_DEVICES=1` 固定物理 GPU 1；容器内 SBERT 使用 `cuda:0`。
- 运行时数据仍放在 `/data/xiaoyunhao/adacascade/runtime/`，不要写入系统盘大文件。
- Qdrant 仍只在 Compose 网络内访问，不需要暴露宿主机端口。

---

## 9. 访问方式

服务器防火墙未开放 13000 端口时，前端需通过 SSH 隧道访问。

在本地 Windows PowerShell 执行并保持窗口打开：

```powershell
ssh -L 18000:localhost:13000 xiaoyunhao@218.199.69.88
```

浏览器访问：

```text
http://localhost:18000/?tenant_id=default
```

---

## 10. 常用运维命令

```bash
# 查看服务状态
docker compose -f ~/AdaC/docker-compose.yml ps

# 查看后端日志
docker compose -f ~/AdaC/docker-compose.yml logs -f backend

# 重启后端
docker compose -f ~/AdaC/docker-compose.yml restart backend

# 更新部署
cd ~/AdaC && git pull && docker compose build backend && docker compose up -d

# 显式重建 TF-IDF（上传/批量导入 demo 数据后执行）
docker compose -f ~/AdaC/docker-compose.yml run --rm backend \
  python scripts/rebuild_tfidf.py --tenant-id default --corpus all

# 清理悬空镜像
docker image prune -f

# 查看 Docker 空间占用
docker system df

# 查看系统盘与数据盘空间
df -h / /data

# 查看 GPU 状态
nvidia-smi
```

---

## 11. 注意事项

1. **无 sudo 权限**：不能安装系统包、不能操作 systemd 服务，需要管理员配合。
2. **系统盘勿存数据**：根盘已用约 94%，所有大文件必须放在 `/data/xiaoyunhao/`。
3. **GPU 资源共享**：GPU 0 基本被共享 vLLM 占用，AdaCascade 固定使用 GPU 1。
4. **CUDA 版本约束**：Driver 535 最高支持 CUDA 12.2，Docker 基础镜像不能使用 CUDA 12.4+。
5. **端口访问限制**：非标准端口可能被防火墙拦截，前端访问优先使用 SSH 隧道，或联系管理员开放端口。
6. **代理使用**：宿主机 Mihomo 代理在 7897 端口；容器内通过 `host.docker.internal:7897` 访问，仅在镜像源不可用时启用代理。
7. **vLLM 共享服务不稳定**：端口 8000 的 vLLM 属于共享服务，AdaCascade 当前以 DeepSeek API 作为主 LLM 后端。
8. **单 worker 约束**：后端必须保持 uvicorn `--workers 1`，不要为吞吐量擅自增加 worker。
9. **Qdrant 私有网络**：Qdrant 仅在 Compose 网络内访问，不需要暴露宿主机端口。
10. **密钥不入库**：`.env`、API key、代理密码等真实敏感信息不得写入任何 git 文件。
