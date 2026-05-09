# KnowEngine — 企业级智能知识引擎

> 基于 RAG 架构的企业知识管理与智能问答引擎，面向汽车行业场景，实现从文档接入、智能切片、向量化存储到多源检索、意图路由、流式对话的全链路闭环。

---

## 架构总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                          用户交互层 (SSE)                            │
│                     ChatController / upload.html                     │
└────────────┬─────────────────────────────────────────────┬──────────┘
             │                                             │
    ┌────────▼────────┐                          ┌────────▼────────┐
    │   智能对话管道    │                          │   知识管理管道    │
    │  (Streaming RAG) │                          │  (Ingestion)    │
    └────────┬────────┘                          └────────┬────────┘
             │                                             │
  ┌──────────┼──────────┐                    ┌─────────────┼──────────┐
  │          │          │                    │             │          │
┌─▼─┐   ┌──▼──┐   ┌──▼───┐           ┌────▼────┐  ┌────▼────┐  ┌──▼──┐
│意图│   │查询  │   │查询   │           │文件上传  │  │文档切片  │  │向量化│
│识别│   │改写  │   │路由   │           │+格式转换 │  │+父子分段 │  │嵌入  │
└─┬─┘   └──┬──┘   └──┬───┘           └────┬────┘  └────┬────┘  └──┬──┘
  │         │         │                    │             │          │
  │    ┌────▼─────────▼────┐          ┌────▼─────────────▼──────────▼──┐
  │    │   多源内容检索      │          │        Spring 事件驱动          │
  │    │ ES / SQL / Neo4j  │          │  Converted → Chunked → Stored  │
  │    └────────┬──────────┘          └────────────────────────────────┘
  │             │
  │    ┌────────▼──────────┐
  │    │  Reranking + 聚合  │
  │    │  BGE-RERANKER(本地) │
  │    └────────┬──────────┘
  │             │
  │    ┌────────▼──────────┐
  └───►│   LLM 流式生成     │
       │  (Prompt 动态注入) │
       └───────────────────┘
```

---

## 核心功能

### 1. 全链路知识接入 (Ingestion Pipeline)

从原始文档到可检索知识，全程自动化：

- **多格式解析**：支持 PDF（MinerU 深度解析）、Word、Excel、Markdown、TXT、Excel等
- **智能切片**：
  - `MarkdownHeaderParentTextSplitter` — 基于标题层级切片，保留父子分段关系（Parent-Child Chunking），支持 chunkSize / overlap 精细控制
  - `MarkdownHeaderBrotherTextSplitter` — 兄弟分段关联，检索时自动补全同级上下文
  - `ExcelSplitter` — 针对结构化数据的行级切片，按 chunkSize 分块
- **事件驱动处理**：Spring `ApplicationEvent` 串联 文档转换 → 切片 → 向量化，每个阶段独立解耦
- **补偿机制**：XXL-Job 定时扫表，自动重试失败任务，保障最终一致性

### 2. 多源 RAG 检索 (Retrieval-Augmented Generation)

三路由检索架构，由 LLM 智能判断数据源：

| 数据源 | 检索方式 | 适用场景 |
|--------|---------|---------|
| **Elasticsearch** | KNN 向量检索 + 全文检索 + 混合检索 | 语义相似性匹配、非结构化知识 |
| **MySQL** | Text2SQL（LLM 生成 SQL） | 结构化数据查询，如订单、保险 |
| **Neo4j** | Text2Cypher（LLM 生成 Cypher） | 实体关系查询，如车型图谱、影响链 |

**关键检索增强**：
- 查询改写（`KnowEngineQueryTransformer`）：4 维改写策略 — 简洁改写、抽象概念改写、错别字纠正、车型信息标准化
- 父子分段扩展（`KnowEngineElasticsearchContentRetriever`）：命中子分段时，自动回溯父分段获取完整语义上下文
- 本地 Reranking（`BgeScoringModel`）：基于 ONNX Runtime 加载 BGE-RERANKER 模型，进程内推理，零网络延迟

### 3. 意图识别与动态 Prompt

- **7 大意图分类**：售前咨询、售后维修、技术指导、投诉维权、营销政策、闲聊、其他
- **结构化实体提取**：车型、订单号、经销商、故障描述、预约时间、零部件、车辆功能
- **Prompt 动态路由**：根据识别结果加载对应的领域 Prompt 文件，实现回答风格的精准适配

### 4. 流式对话体验

- **SSE 实时推送**：基于 Reactor `Flux` 的全链路流式输出，Token 级逐字推送
- **进度可见**：RAG 管道每个环节（意图识别 → 问题改写 → 问题路由 → 排序筛选 → 生成回答）均向前端推送 `[PROGRESS]` 事件，消除等待焦虑
- **RAG 引用溯源**：检索结果携带文档来源、分片内容、Rerank 分数，支持可解释性审查
- **异步标题生成**：新对话自动以虚拟线程异步生成摘要标题，不阻塞首 Token 延迟

### 5. 知识库管理

- **双类型知识库**：`DOCUMENT_SEARCH`（语义检索型）和 `DATA_QUERY`（数据查询型）
- **完整文档生命周期**：INIT → UPLOADED → CONVERTING → CONVERTED → CHUNKED → VECTOR_STORED
- **MinIO 对象存储**：文档文件统一存储，支持 URL 直接访问
- **乐观锁 + 逻辑删除**：数据安全，防并发冲突

---

## 技术亮点

### 🔥 本地 Reranking — 零外部依赖的精排方案

基于 ONNX Runtime 在 JVM 进程内直接运行 BGE-RERANKER 模型，无需部署独立的 Reranking 微服务。采用双重检查锁单例模式，模型仅加载一次，全生命周期复用。解决了 macOS Monterey 兼容性问题（降级 onnxruntime 至 1.17.1），并支持 JAR 包内模型文件的 classpath 自动解析与临时文件释放。

### 🔥 父子分段检索 — 语义完整性的关键保障

检索时命中细粒度子分段后，自动通过 `parentChunkId` 回溯到父分段的完整文本进行替换，同时通过 `brotherChunkId` 补全同级的兄弟分段。这一机制解决了"切片后语义截断"的 RAG 经典痛点，在保持检索精度的同时，为 LLM 提供完整的上下文窗口。

### 🔥 三源智能路由 — 一句话自动选数据源

`KnowEngineQueryRouter` 利用 LLM 对用户 Query 进行语义分析，输出 `{intent, strategy, confidence}` 结构化决策，自动路由到 Elasticsearch / MySQL / Neo4j 中最合适的数据源。路由失败自动降级为空结果，保障系统鲁棒性。

### 🔥 流式 RAG 管道 — 进度感知的端到端流式架构

在 `DefaultRetrievalAugmentor` 的标准流程中，通过装饰器模式（`ProgressAwareContentRetriever` / `ProgressAwareContentAggregator`）注入进度回调，将阻塞式 RAG 操作调度到 `Schedulers.boundedElastic()`，通过 `Flux.create()` + `publishOn(Schedulers.parallel())` 实现进度消息与 LLM Token 的有序混合推送。

### 🔥 Spring 事件驱动 — 文档处理的优雅编排

文档从上传到入库全程通过 Spring `ApplicationEvent` 串联，Controller 只负责发布事件，业务逻辑完全由 EventListener 异步驱动。结合 XXL-Job 补偿任务，实现"事件驱动 + 定时兜底"的最终一致性保障。

### 🔥 分布式锁注解 — 声明式并发控制

基于 Redisson + AOP 实现的 `@DistributeLock` 注解，支持 SpEL 表达式动态 Key、超时自动续期、等待超时等策略，一行注解即可保护关键业务操作（如文档上传、切片）的幂等性。

---

## 技术栈

| 分类 | 技术 | 说明 |
|------|------|------|
| **语言/框架** | Java 21 + Spring Boot 3.5 | 虚拟线程、Record 模式匹配 |
| **AI 框架** | LangChain4j 1.11.0 | RAG 管道、AI Services、流式对话 |
| **LLM** | 通义千问 (qwen-max-latest) | 意图识别、查询改写、路由决策、流式生成 |
| **向量存储** | Elasticsearch | KNN / 全文 / 混合检索 |
| **图数据库** | Neo4j + APOC | Text2Cypher 实体关系查询 |
| **关系数据库** | MySQL + MyBatis-Plus | 业务数据 + Text2SQL 结构化查询 |
| **对象存储** | MinIO | 文档文件存储 |
| **缓存** | Redis + Redisson | 分布式锁、父分段缓存 |
| **Reranking** | BGE-RERANKER (ONNX Runtime) | 进程内本地推理，零网络开销 |
| **Embedding** | text-embedding-v4 (通义) | 1536 维向量 |
| **文件解析** | MinerU (PDF)、Apache Tika (类型检测)、EasyExcel | 多格式文档解析 |
| **任务调度** | XXL-Job 2.4 | 补偿任务定时触发 |
| **响应式** | Project Reactor | SSE 流式推送、非阻塞调度 |
| **连接池** | Druid | SQL 监控、慢查询检测 |

---

## 项目结构

```
know-engine/
├── ai/                          # AI 能力层
│   ├── config/                  #   Memory 配置
│   ├── constant/                #   意图枚举
│   ├── model/                   #   意图识别结果模型
│   └── service/                 #   意图识别、通用对话、Prompt 路由、标题摘要
├── chat/                        # 对话管理层
│   ├── constant/                #   会话状态、消息类型、检索来源
│   ├── controller/              #   对话/会话/消息 REST 接口
│   ├── entity/                  #   会话与消息实体
│   ├── mapper/                  #   MyBatis-Plus Mapper
│   └── service/                 #   对话应用服务（RAG 管道编排）
├── config/                      # 全局配置
│   ├── AsyncConfig              #   线程池配置
│   ├── MyMetaObjectHandler      #   自动填充时间戳
│   ├── MybatisPlusConfig        #   分页插件、乐观锁插件
│   └── XxlJobConfig             #   XXL-Job 执行器配置
├── document/                    # 知识文档管理层
│   ├── config/                  #   MinIO 配置
│   ├── constant/                #   文档状态、文件类型、知识库类型
│   ├── controller/              #   文档/切片 REST 接口
│   ├── entity/                  #   文档与切片实体
│   ├── event/                   #   Spring 事件（Converted/Chunked）
│   ├── job/                     #   XXL-Job 补偿任务
│   ├── mapper/                  #   MyBatis-Plus Mapper
│   ├── service/                 #   文档处理、切片、向量化、文件存储
│   └── util/                    #   文件类型检测 (Tika)
├── infra/                       # 基础设施
│   ├── json/                    #   JSON 工具
│   ├── lock/                    #   分布式锁注解 + AOP 切面
│   └── snowflake/               #   雪花 ID 生成器
└── rag/                         # RAG 检索增强层
    ├── config/                   #   ES / Neo4j 配置
    ├── constant/                 #   元数据 Key 常量
    ├── controller/               #   检索测试接口
    ├── model/                    #   路由结果模型
    └── modules/                  #   RAG 核心模块
        ├── KnowEngineQueryTransformer   # 查询改写器
        ├── KnowEngineQueryRouter        # 三源路由器
        ├── KnowEngineElasticsearchContentRetriever  # ES 检索器（父子分段扩展）
        ├── ProgressAwareContentAggregator          # 进度感知聚合器
        ├── reranker/              #   BGE-RERANKER 本地单例
        └── splitter/              #   文档切片器（Markdown/Excel）
```

---

## 快速开始

### 环境依赖

- JDK 21+
- MySQL 8.0+
- Redis 7.0+
- Elasticsearch 8.x（需开启 KNN 向量检索）
- Neo4j 5.x（需安装 APOC 插件）
- MinIO
- XXL-Job Admin 2.4+

### 配置

1. 修改 `src/main/resources/application.yml`，填入各中间件连接信息和 LLM API Key
2. 执行 `src/main/resources/sql/tables.sql` 初始化数据库表

### 构建 & 运行

```bash
mvn clean package -DskipTests
java -jar target/know-engine-1.0.0-SNAPSHOT.jar
```

### 接口速览

| 接口 | 方法 | 说明 |
|------|------|------|
| `/chat/send` | POST | 流式对话（SSE），支持进度推送和 RAG 引用溯源 |
| `/chat/list` | GET | 查询用户会话列表 |
| `/chat/messages` | GET | 查询会话消息历史 |
| `/api/document/upload` | POST | 上传知识文档 |
| `/api/document/split/{id}` | POST | 手动触发文档切片 |
| `/api/document/embedding` | POST | 手动触发向量化 |

---

## 设计原则

- **事件驱动优于直接调用**：文档处理流程通过 Spring Event 解耦，Controller 瘦身，职责清晰
- **最终一致性**：事件驱动 + XXL-Job 补偿，"异步优先，定时兜底"
- **流式优先**：全链路 Reactor 响应式，SSE 逐 Token 推送，进度可见
- **声明式并发控制**：`@DistributeLock` 注解一行搞定幂等保护
- **本地推理优先**：Reranking 在 JVM 进程内完成，省去网络往返，降低延迟
