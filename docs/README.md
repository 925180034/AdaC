# AdaCascade 文档索引

本目录保存 AdaCascade 的系统设计、算法规格、运维指南和前端设计说明。顶层 [`README.md`](../README.md) 是项目入口；本文件用于说明每份文档的用途和推荐阅读路径。

---

## 推荐阅读路径

### 新用户 / 评审老师

1. [`../README.md`](../README.md)：项目概览、功能模式、快速开始、文档导航。
2. [`AdaCascade_System_Design.md`](AdaCascade_System_Design.md)：系统架构、API、数据库、部署和目录结构。
3. [`AdaCascade_Algorithm_Spec.md`](AdaCascade_Algorithm_Spec.md)：算法流程、公式、默认超参和实验指标。

### 开发者

1. [`AdaCascade_System_Design.md`](AdaCascade_System_Design.md)：先确认工程约束和模块边界。
2. [`AdaCascade_Algorithm_Spec.md`](AdaCascade_Algorithm_Spec.md)：再确认智能体、TLCF、Matcher 和 LLM JSON Schema 的算法要求。
3. [`frontend_demo_design.md`](frontend_demo_design.md)：理解前端工作台交互和展示逻辑。
4. [`M4_Operations_Guide.md`](M4_Operations_Guide.md)：理解本地 demo、运行时切换和 UAT 操作。

### 部署 / 运维人员

1. [`../deploy/README.md`](../deploy/README.md)：Docker Compose 通用部署流程。
2. [`../deploy/LAB_SERVER.md`](../deploy/LAB_SERVER.md)：课题组实验室服务器专用环境档案。
3. [`M4_Operations_Guide.md`](M4_Operations_Guide.md)：本地非 Docker 运行、demo 验证和常用运维操作。

### Demo 数据使用者

1. [`../demo_data/agri_lake/README.md`](../demo_data/agri_lake/README.md)：农业 demo 数据集、推荐任务和预期匹配关系。
2. [`../README.md#8-demo-数据`](../README.md#8-demo-数据)：快速入口和 TF-IDF 重建提示。

---

## 文档清单

| 文档 | 用途 | 适合读者 |
|---|---|---|
| [`../README.md`](../README.md) | 项目入口、快速开始、架构概览、验证命令和文档导航 | 所有人 |
| [`AdaCascade_System_Design.md`](AdaCascade_System_Design.md) | 工程架构、API 契约、数据库 schema、部署方式、目录结构和依赖版本 | 开发者、部署人员、评审 |
| [`AdaCascade_Algorithm_Spec.md`](AdaCascade_Algorithm_Spec.md) | Planner / Profiling / Retrieval / Matcher 的算法细节、公式、默认超参、提示词模板和测试指标 | 算法开发者、论文复现实验人员 |
| [`M4_Operations_Guide.md`](M4_Operations_Guide.md) | 本地 demo、运行时切换、操作验证、常用检查命令 | 开发者、演示人员、运维人员 |
| [`frontend_demo_design.md`](frontend_demo_design.md) | 前端工作台布局、交互、状态展示和 UX 设计 | 前端开发者、产品/演示人员 |
| [`frontend_demo_implementation_plan.md`](frontend_demo_implementation_plan.md) | 前端 demo 实施计划留档；不是当前前端的唯一说明源 | 维护人员 |
| [`../deploy/README.md`](../deploy/README.md) | Docker Compose 通用部署流程、配置、镜像、代理、健康检查和故障排查 | 部署人员、运维人员 |
| [`../deploy/LAB_SERVER.md`](../deploy/LAB_SERVER.md) | 课题组实验室服务器硬件、网络、Docker、GPU、路径和约束 | 部署人员、后续接手会话 |
| [`../demo_data/agri_lake/README.md`](../demo_data/agri_lake/README.md) | 农业 demo 数据集说明和任务示例 | 演示人员、测试人员 |

---

## 文档维护原则

1. **顶层 README 只做入口和快速开始**：不要在顶层 README 复制完整算法公式或数据库 schema，详细内容链接到权威文档。
2. **系统设计文档裁决工程问题**：API、目录、依赖、数据库、部署、降级策略以 [`AdaCascade_System_Design.md`](AdaCascade_System_Design.md) 为准。
3. **算法规格文档裁决算法问题**：公式、默认超参、提示词、JSON Schema 和实验指标以 [`AdaCascade_Algorithm_Spec.md`](AdaCascade_Algorithm_Spec.md) 为准。
4. **部署文档分层维护**：[`../deploy/README.md`](../deploy/README.md) 写通用 Docker Compose 部署；[`../deploy/LAB_SERVER.md`](../deploy/LAB_SERVER.md) 写实验室服务器专用约束。
5. **本地开发与 Docker 部署分开描述**：本地脚本启动流程不要混入服务器 Compose 步骤，避免误操作。
6. **真实密钥不入库**：任何 `.env`、API token、外部服务凭据和代理凭据都只能保留在部署本地。
7. **内部计划文档不作为用户入口**：历史实施计划、代码评审跟进和 superpowers 过程文档可以留档，但不要放在主要阅读路径中。
