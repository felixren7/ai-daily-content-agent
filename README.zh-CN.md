# AI Daily Content Agent

[English](README.md) | **简体中文**

一个生产级、可扩展的开源 AI 内容 Agent。它每天自动收集可信的 AI 新闻和研究信息，或选择一个前沿 AI 概念，完成去重、排序、事实核验、内容生成、质量检查、人工审批与多平台发布。

项目默认处于安全模式：使用本地模板生成器、关闭自动发布并启用 `DRY_RUN`。因此，在未配置真实平台凭据前，你可以完整测试 Agent，但不会向外部平台发送内容。

## 系统流程

```mermaid
flowchart TD
    A[RSS / arXiv / GitHub / 概念库] --> B[采集与标准化]
    B --> C[URL、标题与语义去重]
    C --> D[主题评分与排序]
    D --> E[选择最佳主题]
    E --> F[来源提取与事实核验]
    F --> G[LLM 内容生成]
    G --> H[质量检查]
    H --> T[中英双语发布版本]
    T --> I{是否满足自动发布条件?}
    I -- 否 --> J[保存为待审核或质量未通过]
    I -- 是 --> K[平台格式化与发布]
    J --> L[(SQLite)]
    K --> L
    M[APScheduler 每日调度] --> B
```

## 已实现能力

- 支持 `news`、`concept` 和 `mixed` 三种内容模式。
- 内置多个可信 AI 信息源，包括 OpenAI、Google AI、Google DeepMind、Microsoft Research、NVIDIA AI、Hugging Face、MIT AI News、arXiv 和 GitHub。
- 单个来源失败不会中断整个流水线。
- 支持 URL、规范化标题、内容哈希和语义相似度去重。
- 排名权重全部可通过环境变量配置。
- 保存来源、提取事实、置信度和生成元数据。
- 对低置信度、来源不可用、疑似提示词注入和无证据事实进行拦截。
- 支持模板生成、OpenAI API 和 OpenAI 兼容 API，包括 DeepSeek。
- 内置事实一致性、夸张用语、清晰度、重复度、来源和平台长度检查。
- 支持 X、LinkedIn、Telegram 和通用 Webhook 适配器。
- 支持人工审批、自动发布和全局 Dry Run。
- 提供响应式中英文 Web 控制台，可直观查看流水线、事实来源和质量检查。
- 可从网页立即启动 Agent，运行期间每 5 秒自动刷新进度。
- 支持根据人工意见重新生成新草稿，同时保留原草稿和审计关系。
- 批准后可选择立即发布或指定时间发布，并可明确选择原文或中文版。
- 使用 APScheduler 按时区每日运行，并使用数据库锁防止重复并发执行。
- FastAPI 健康检查、结构化日志、运行历史和发布历史。
- SQLite 默认存储，可通过 `DATABASE_URL` 切换到 PostgreSQL。

## 快速启动

### 前置条件

- Docker Desktop，或其他支持 Docker Compose v2 的 Docker 环境
- 可用端口 `8000`
- 如果不用 Docker，本地开发需要 Python 3.12

检查 Docker：

```bash
docker --version
docker compose version
```

进入项目目录：

```bash
cd "/Users/renhongxu/Documents/小红书自动化"
```

创建本地环境配置：

```bash
cp .env.example .env
```

这条命令只适用于首次初始化。如果 `.env` 已存在，请先备份或直接编辑它，不要用示例文件覆盖已有密钥和配置。也可以安全地执行：

```bash
test -f .env || cp .env.example .env
```

默认 `.env.example` 已使用以下安全设置：

```dotenv
LLM_PROVIDER=template
DRY_RUN=true
AUTO_PUBLISH=false
PUBLISH_PLATFORMS=
```

构建并启动：

```bash
docker compose up --build -d
docker compose ps
```

`docker compose ps` 中的 `app` 应显示为 `healthy`。随后可以运行一次完整 Agent：

```bash
docker compose exec app python -m app.cli run --dry-run
```

### 打开 Web 审核控制台

服务启动后，在浏览器打开：

[http://localhost:8000](http://localhost:8000)

页面直接读取 SQLite 中的真实数据，不是演示数据。日常操作不需要再打开终端：

1. 在顶部确认 `Dry run` 仍然开启。这样即使点击发布，也不会调用任何社交平台 API。
2. 需要手动生成新帖子时，点击顶部 `Run now`。这会真实执行采集、去重、排名、核验和 LLM 生成；如果使用 DeepSeek，会产生一次模型 API 调用。
3. 页面每 5 秒自动刷新。可在 `Today’s run` 查看采集数量、去重数量、候选主题与当前阶段，无需手动刷新浏览器。
4. 点击右上角 `中文`，界面会切换为中文。当前帖子没有中文版时，系统会调用已配置的 LLM 翻译一次，检查来源 URL、数字和事实数量后缓存到数据库；后续切换不会重复收费。`template` 离线提供器不具备翻译能力。
5. 阅读中间的帖子正文，再核对 `Verified facts` 和 `Source evidence`，不要只看质量分。
6. 需要改写时点击 `Regenerate`，输入明确意见。系统只能使用已存储的事实和来源，重新运行质量门禁，创建一条新草稿，并把旧草稿标记为 `superseded`。
7. 确认可发布后点击 `Approve & queue`。此时只会把状态改为 `approved`，不会立即对外发布。
8. 批准后可选 `Publish now` 或 `Schedule publish`。定时发布会把具体时间和语言版本写入 SQLite，后台每 30 秒扫描到期任务。两种方式互斥；已定时的帖子退回修改或重新生成时，旧定时任务会自动取消。
9. 在 `DRY_RUN=true` 时，立即发布和到期的定时发布都只会记录为跳过，不会调用社交平台 API。

Docker Compose 默认只把端口绑定到 `127.0.0.1:8000`，同一局域网中的其他设备不能直接访问。
如果以后部署到服务器并设置 `ENVIRONMENT=production`，必须同时配置一个足够长、随机的
`DASHBOARD_ADMIN_TOKEN`，否则应用会拒绝启动。Web 页面只在当前浏览器会话中保存这个令牌。

## 如何一步步测试 Agent

以下步骤按照风险从低到高排列。建议先完成第 1 至第 9 步，再配置 DeepSeek 或真实发布平台。

### 第 1 步：确认密钥文件不会进入 Git

```bash
git check-ignore .env
```

预期输出为 `.env`。如果没有输出，请先检查 `.gitignore`，不要继续填写任何 API 密钥。

不要把 `.env` 内容粘贴到聊天、Issue、终端截图或日志中，也不要把真实密钥写进 `.env.example`。

### 第 2 步：验证 Compose 配置

```bash
docker compose config --quiet
```

成功时不会输出内容，退出码为 `0`。它只验证 Compose 配置，不代表服务已经成功运行。

### 第 3 步：启动服务并检查健康状态

```bash
docker compose up --build -d
docker compose ps
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
```

预期健康检查返回类似：

```json
{"status":"ok"}
```

如果容器不是 `healthy`，先查看日志：

```bash
docker compose logs --tail=200 app
```

### 第 4 步：查看 Agent 当前状态

```bash
docker compose exec app python -m app.cli status
```

重点确认：

- `dry_run` 为 `true`
- `auto_publish` 为 `false`
- 调度时间、内容模式和最近一次运行状态符合预期

只要 `status` 命令能够完成数据库初始化并读取最近运行记录，就说明 CLI 可以访问数据库。运行锁不会显示在 `status` 输出中；如果已有任务持有锁，启动新流水线时会明确报错。

### 第 5 步：执行一次完整、安全的端到端测试

```bash
docker compose exec app python -m app.cli run --dry-run
```

典型输出会包含：

```text
Fetching AI sources...
Found XX articles
Removed XX duplicates
Ranking XX topics...
Selected: XXXXX
Verifying sources...
Generating post...
Quality score: XX
Saving post...
DRY RUN — publication skipped.
```

最后还会打印生成的社交媒体正文。此命令会真实执行采集、去重、排名、核验、生成、质量检查和数据库保存，但不会调用社交平台发布接口。

注意：`XX` 会随时间和网络情况变化。某个来源失败也不一定代表 Agent 失败；系统会记录来源错误并继续处理其他来源。例如，未配置 `GITHUB_TOKEN` 时，GitHub 可能因匿名请求限流而返回 `403`。

### 第 6 步：检查生成内容和运行历史

查看所有帖子：

```bash
docker compose exec app python -m app.cli list-posts
```

只查看待审核帖子：

```bash
docker compose exec app python -m app.cli list-pending
```

通过 API 查看最近数据：

```bash
curl -s http://localhost:8000/posts
curl -s http://localhost:8000/runs
```

端到端测试完成后，至少应看到一条运行记录。生成帖子可能是以下状态之一：

- `pending_review`：质量合格，但自动发布关闭，等待人工审核。
- `quality_rejected`：质量分或事实置信度未达到阈值。
- `published`：平台发布成功；在默认安全配置下不会出现。
- `failed`：生成或发布发生明确错误，可从运行记录和日志定位。

### 第 7 步：分别测试三种内容模式

测试 AI 新闻：

```bash
docker compose exec app python -m app.cli run --dry-run --mode news
```

测试 AI 前沿概念：

```bash
docker compose exec app python -m app.cli run --dry-run --mode concept
```

测试混合模式：

```bash
docker compose exec app python -m app.cli run --dry-run --mode mixed
```

新闻模式会优先选择近期、高可信度和技术价值高的内容。概念模式会从概念库中选择尚未发布或较少使用的主题。混合模式会结合运行历史和新闻重要度选择模式。

如果新闻模式提示没有可核验的候选主题，通常说明当前候选内容被去重、来源证据不足或置信度过低；这是安全拦截，不应通过关闭核验来绕过。

### 第 8 步：单独测试各流水线阶段

只采集和保存来源：

```bash
docker compose exec app python -m app.cli fetch
```

对数据库中的候选主题重新排名：

```bash
docker compose exec app python -m app.cli rank
```

生成一个帖子但不发布：

```bash
docker compose exec app python -m app.cli generate --mode news
```

再次查看状态和结果：

```bash
docker compose exec app python -m app.cli status
docker compose exec app python -m app.cli list-posts
```

这些命令适合定位问题属于采集、排名、生成还是质量检查阶段。

### 第 9 步：运行自动化测试

项目的 Dockerfile 提供独立测试阶段，不需要在宿主机安装 Python 依赖：

```bash
docker build --target test -t ai-daily-content-agent:test .
docker run --rm ai-daily-content-agent:test
```

测试不调用真实 LLM 或社交媒体接口。它覆盖：

- 配置校验
- 主题排名
- 内容标准化和解析
- URL、标题及语义去重
- 事实核验
- 质量门禁
- LLM Provider 抽象
- 平台格式化和适配器

只运行某一类测试：

```bash
docker run --rm ai-daily-content-agent:test pytest tests/test_ranking.py -q
docker run --rm ai-daily-content-agent:test pytest tests/test_deduplication.py -q
docker run --rm ai-daily-content-agent:test pytest tests/test_quality_gate.py tests/test_verification.py -q
docker run --rm ai-daily-content-agent:test pytest tests/test_platforms.py tests/test_llm.py -q
```

### 第 10 步：使用 DeepSeek API 测试真实 LLM 生成

DeepSeek 提供 OpenAI 兼容 API，因此本项目可以直接使用。先编辑本地 `.env`：

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的真实密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash

DRY_RUN=true
AUTO_PUBLISH=false
PUBLISH_PLATFORMS=
```

截至本文更新时，DeepSeek 官方 OpenAI 兼容入口为 `https://api.deepseek.com`，推荐模型标识为 `deepseek-flash`；模型名称和 API 可用性仍可能变化，请在测试前查看 [DeepSeek 官方首次调用指南](https://api-docs.deepseek.com/guides/codex) 和 [模型列表](https://api-docs.deepseek.com/api/list-models/)。不要把密钥写入命令历史，也不要提交 `.env`。

让容器重新读取环境变量：

```bash
docker compose up -d --force-recreate
docker compose exec app python -m app.cli status
```

然后执行：

```bash
docker compose exec app python -m app.cli run --dry-run --mode news
```

检查点：

- 流水线成功完成，或给出明确的 API 错误。
- 帖子中保留来源引用。
- 生成文本没有加入来源无法支持的新数字、日期或产品能力。
- 质量分达到阈值时保存为 `pending_review`，而不是实际发布。
- 日志中不应出现 API 密钥。

常见 DeepSeek 错误：

- `401`：密钥无效、格式错误或未被容器读取。
- `402`：账户余额或计费状态问题。
- `429`：请求频率或配额限制。
- 模型不存在：检查 `DEEPSEEK_MODEL` 是否仍是账户可用的官方模型名。

修改 `.env` 后如果仍使用旧配置，运行：

```bash
docker compose up -d --force-recreate
```

### 第 11 步：验证质量门禁

默认自动发布阈值为：

```dotenv
MIN_QUALITY_SCORE=85
```

运行新闻和概念模式后，检查日志及帖子状态：

```bash
docker compose exec app python -m app.cli list-posts
docker compose logs --tail=200 app
```

质量低于阈值、来源不足或事实置信度过低的内容应进入 `quality_rejected`，不能自动发布。不要为了让测试“通过”而把阈值降到很低；应先检查来源、生成内容和被扣分原因。

### 第 12 步：测试人工审批流程

首先再次确认 `.env` 中保持：

```dotenv
DRY_RUN=true
AUTO_PUBLISH=false
```

列出待审批内容：

```bash
docker compose exec app python -m app.cli list-pending
```

记下帖子 ID，然后审批：

```bash
docker compose exec app python -m app.cli approve <post_id>
```

在 Dry Run 下测试发布命令：

```bash
docker compose exec app python -m app.cli publish <post_id>
```

预期输出应明确包含 `DRY RUN` 或“publication skipped”，且不会访问真实平台。`<post_id>` 必须替换为实际 ID，不要保留尖括号。

### 第 13 步：测试每日调度器

在 `.env` 中把发布时间临时设置为当前时间之后 2 至 3 分钟，并保持安全开关：

```dotenv
TIMEZONE=Asia/Singapore
POST_TIME=09:00
DRY_RUN=true
AUTO_PUBLISH=false
```

把 `09:00` 替换为你的测试时间，然后重启并跟踪日志：

```bash
docker compose up -d --force-recreate
docker compose logs -f app
```

到达设定时间后，应看到带同一个 `run_id` 的阶段日志：

```text
FETCH
NORMALIZE
DEDUP
RANK
VERIFY
GENERATE
QUALITY_CHECK
PUBLISH
DONE
```

如果运行失败，最后阶段会是 `FAILED`，并记录错误信息。按 `Ctrl+C` 只会退出日志跟踪，不会停止容器。

随后确认运行历史：

```bash
docker compose exec app python -m app.cli status
curl -s http://localhost:8000/runs
```

测试完成后，把 `POST_TIME` 恢复为正式发布时间并再次重启容器。

### 第 14 步：测试平台适配器，但不真实发布

先运行平台适配器的 Mock 测试：

```bash
docker build --target test -t ai-daily-content-agent:test .
docker run --rm ai-daily-content-agent:test pytest tests/test_platforms.py -q
```

该测试验证格式化、长度校验、请求构造和错误处理，不会访问真实 X、LinkedIn、Telegram 或 Webhook。

在配置真实平台前，始终保持 `DRY_RUN=true`。只有在以下条件全部满足后，才建议进行小范围真实发布：

1. DeepSeek 或其他 LLM 的输出已人工检查。
2. 事实核验和质量门禁稳定通过。
3. 目标平台使用测试账号或私有频道。
4. 平台凭据只存在于 `.env` 或安全的 Secret 管理系统。
5. 已明确设置 `PUBLISH_PLATFORMS`，且理解每个平台的 API 权限。
6. 最后才将 `DRY_RUN=false`。

### 第 15 步：停止、重新启动或清空环境

停止容器但保留 SQLite 数据卷：

```bash
docker compose down
```

重新启动并保留历史数据：

```bash
docker compose up -d
```

彻底删除容器和数据库卷：

```bash
docker compose down -v
```

警告：`docker compose down -v` 会删除已保存的帖子、运行历史和发布历史。除非你明确要重置测试环境，并且已经备份需要的数据，否则不要执行。

## 内容模式

通过环境变量配置默认模式：

```dotenv
CONTENT_MODE=mixed
```

允许的值：

- `news`：只发现并处理近期 AI 新闻。
- `concept`：从概念库选择并解释一个 AI 术语。
- `mixed`：在新闻和概念之间智能选择，并参考近期运行历史。

CLI 中的 `--mode` 只覆盖当前一次运行，不会修改 `.env`。

## LLM Provider

### 本地模板 Provider

默认配置：

```dotenv
LLM_PROVIDER=template
```

它不调用外部模型，适合首次启动、离线测试和 CI。生成效果主要用于验证工程链路，不等同于真实大模型的写作质量。

### DeepSeek

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

DeepSeek 通过兼容 Provider 接入。系统会要求模型返回结构化 JSON，并在生成后再次执行本地质量和事实检查。

`deepseek-flash` 是**推理模型**，它的思考过程**计入 `max_tokens`**。如果模型还没开始回答就把预算用光，API 返回的是**空内容**而不是简短回复，看起来像响应格式错误。翻译是最吃预算的场景（要把整篇帖子用另一种语言重写一遍），所以它有独立的 `TRANSLATION_MAX_TOKENS`（默认 16000；实测单篇帖子约需 7600 token 的推理加输出）。如果生成也开始出现同样症状，同样需要调高 `LLM_MAX_TOKENS`。

推理还很耗时，所以模型调用有独立的 `LLM_TIMEOUT_SECONDS`（默认 600 秒），不再复用抓取来源的超时；实测一次翻译耗时 35 秒。

### OpenAI

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

### 其他 OpenAI 兼容 API

```dotenv
LLM_PROVIDER=compatible
COMPATIBLE_API_KEY=
COMPATIBLE_BASE_URL=https://example.com/v1
COMPATIBLE_MODEL=your-model
```

兼容服务必须支持 OpenAI 风格的 Chat Completions 请求和 JSON 输出。不同供应商的字段、模型名或限流策略可能不同，应先在 Dry Run 中验证。

## 主要环境变量

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `ENVIRONMENT` | `development` | 运行环境名称 |
| `DATABASE_URL` | `sqlite:////app/data/content_agent.db` | Docker 中的 SQLAlchemy 数据库连接 |
| `CONTENT_MODE` | `mixed` | `news`、`concept` 或 `mixed` |
| `LLM_PROVIDER` | `template` | `template`、`openai`、`deepseek` 或 `compatible` |
| `LLM_MAX_TOKENS` | `1800` | 生成预算 |
| `TRANSLATION_MAX_TOKENS` | `16000` | 翻译预算，原因见下方 DeepSeek 说明 |
| `LLM_TIMEOUT_SECONDS` | `600` | 模型调用超时；`REQUEST_TIMEOUT_SECONDS` 只管抓取来源 |
| `DRY_RUN` | `true` | 为 `true` 时禁止真实发布 |
| `AUTO_PUBLISH` | `false` | 为 `false` 时合格帖子进入人工审核 |
| `DASHBOARD_ADMIN_TOKEN` | 空 | 生产环境 Web 审核操作令牌；`production` 时必填 |
| `MIN_QUALITY_SCORE` | `85` | 自动发布最低质量分 |
| `MIN_VERIFICATION_CONFIDENCE` | `0.72` | 最低事实核验置信度 |
| `TIMEZONE` | `Asia/Singapore` | 调度器 IANA 时区 |
| `POST_TIME` | `09:00` | 每日运行时间，24 小时制 |
| `PUBLISH_PLATFORMS` | 空 | 逗号分隔的平台列表 |
| `EXTRA_RSS_FEEDS` | 空 | 逗号分隔的额外 RSS 地址 |
| `EXTRA_RSS_CREDIBILITY` | `0.65` | `EXTRA_RSS_FEEDS` 各条目的起始可信度 |
| `SOURCE_CREDIBILITY_OVERRIDES` | 空 | 按来源名称覆盖可信度，如 `GitHub AI Projects=0.9` |
| `GITHUB_TOKEN` | 空 | 可选，用于提高 GitHub API 限额 |
| `SIMILARITY_THRESHOLD` | `0.82` | 当前候选之间的语义重复阈值 |
| `HISTORY_SIMILARITY_THRESHOLD` | `0.78` | 与历史内容比较的语义重复阈值 |
| `SCORE_RECENCY_WEIGHT` | `0.25` | 排名中的时效性权重 |
| `SCORE_SOURCE_QUALITY_WEIGHT` | `0.20` | 来源质量权重 |
| `SCORE_IMPORTANCE_WEIGHT` | `0.20` | 重要度权重 |
| `SCORE_NOVELTY_WEIGHT` | `0.15` | 新颖度权重 |
| `SCORE_TECHNICAL_RELEVANCE_WEIGHT` | `0.10` | 技术相关性权重 |
| `SCORE_SOCIAL_INTEREST_WEIGHT` | `0.10` | 社交关注度权重 |

完整配置和注释请查看 `.env.example`。

## 信息源

项目预置至少五类可靠来源：

- OpenAI 官方动态
- Google AI 官方博客
- Microsoft Research 官方动态
- NVIDIA AI 官方博客
- MIT AI News
- Google DeepMind 官方博客
- Hugging Face 博客
- arXiv AI / ML 论文
- GitHub AI 项目趋势信号

采集器会把外部内容视为不可信数据。网页中的“忽略先前指令”“输出密钥”“改变系统提示词”等文字不会被当作 Agent 指令；疑似提示词注入的内容会被标记，严重时直接拒绝。

### 添加 RSS 来源

不写代码时，把 URL 加到 `EXTRA_RSS_FEEDS` 即可。但每个条目起始可信度是 `EXTRA_RSS_CREDIBILITY`，**这个默认值不足以单独出稿**：核验置信度为 `0.55 × 可信度 + 0.25`，另加最多 `0.20` 的交叉印证分，必须达到 `MIN_VERIFICATION_CONFIDENCE`（0.72）。也就是说单一来源的可信度至少要 **0.855**。因此新增 feed 后需要提高 `EXTRA_RSS_CREDIBILITY`，或在 `SOURCE_CREDIBILITY_OVERRIDES` 中按名称指定，否则它的文章只能作为其他来源的交叉印证。

1. 在 `app/collectors/` 中新增采集器，或扩展现有 RSS 配置。
2. 输出统一的标准化文章 Schema。
3. 为来源配置可信度分值。
4. 为解析失败、缺失日期和恶意内容增加测试。
5. 把采集器注册到采集服务中。
6. 验证单个来源失败不会终止其他采集器。

## 去重和排名

系统依次检查：

1. 规范化 URL
2. 标题规范化
3. 内容哈希
4. 词项向量余弦相似度
5. 既往发布历史

默认排名公式为：

```text
topic_score =
  0.25 * recency
  + 0.20 * source_quality
  + 0.20 * importance
  + 0.15 * novelty
  + 0.10 * technical_relevance
  + 0.10 * social_interest
```

重复概率和既往发布记录会进一步降低或淘汰候选主题。权重在启动时校验，避免错误配置导致排名失真。

## 事实核验

生成前，系统会：

- 保存原始 URL、标题和发布日期。
- 提取来源中可直接支持的事实。
- 在可能时比较多个来源。
- 标记不确定、冲突或缺少证据的说法。
- 计算事实置信度。
- 拒绝提示词注入和证据不足的内容。

生成后，质量门禁会再次检查正文中的数字、日期、专有名词和断言是否能被来源支持。LLM 的输出永远不能替代原始来源证据。

## 内容结构和风格

新闻内容默认包含：

1. Hook
2. 发生了什么
3. 为什么重要
4. 技术解释
5. 行业影响或判断
6. 来源

概念内容默认包含：

1. 术语
2. 一句话解释
3. 工作原理
4. 简单示例
5. 为什么重要
6. 实际应用
7. 关键结论

支持的风格包括 `TECHNICAL`、`EDUCATIONAL`、`NEWS_SUMMARY`、`BEGINNER_FRIENDLY`、`PROFESSIONAL` 和 `VIRAL`。默认倾向专业、技术准确、易理解，并禁止空泛营销表达。

## 人工审核与发布

关闭自动发布时：

```dotenv
AUTO_PUBLISH=false
```

合格内容保存为 `pending_review`。常用命令：

```bash
python -m app.cli list-pending
python -m app.cli approve <post_id>
python -m app.cli publish <post_id>
```

即使帖子已经审批，只要 `DRY_RUN=true`，系统仍不会调用真实发布接口。

## 平台适配器

### Telegram

需要：

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

建议先使用私人测试频道，并确认 Bot 已获得发消息权限。

### 通用 Webhook

需要：

```dotenv
WEBHOOK_URL=
WEBHOOK_BEARER_TOKEN=
```

系统以 JSON 发送帖子和来源信息。Bearer Token 可留空，取决于目标服务。

### X / Twitter

需要 X 官方开发者访问权限，以及具备发帖权限的 OAuth 2.0 用户上下文 Bearer Token：

```dotenv
TWITTER_BEARER_TOKEN=
```

项目不使用浏览器自动化绕过官方 API 权限。

### LinkedIn

需要 LinkedIn 应用、有效 OAuth Access Token，以及允许发布的成员或组织 URN：

```dotenv
LINKEDIN_ACCESS_TOKEN=
LINKEDIN_AUTHOR_URN=
```

LinkedIn 的审核和权限要求可能变化，应以官方开发者文档为准。

### 添加新平台

1. 继承 `PlatformAdapter`。
2. 实现 `format`、`validate` 和 `publish`。
3. 所有凭据从环境变量读取。
4. 为长度限制、请求体和错误响应编写 Mock 测试。
5. 在平台工厂中注册适配器。
6. 先通过 Dry Run 和测试账号验证。

## 调度与并发控制

调度器使用 `TIMEZONE` 和 `POST_TIME` 每日触发。进程内的 `max_instances=1` 阻止同进程重叠，跨进程则由一个原子文件锁阻止 API 进程与 `docker compose exec` CLI 运行重叠；停机期间错过的任务会合并执行，过期锁在四小时后失效。每次执行都有独立 `run_id`，结构化日志记录以下阶段：

```text
FETCH
NORMALIZE
DEDUP
RANK
VERIFY
GENERATE
QUALITY_CHECK
PUBLISH
DONE / FAILED
```

使用 SQLite 时只能运行一个启用调度器的副本。需要多个生产副本时，应先迁移到 PostgreSQL，并把文件锁替换为数据库咨询锁或分布式租约。文件锁依赖共享文件系统，无法跨主机协调。

## API

服务默认监听 `http://localhost:8000`。

常用端点：

- `GET /`：Web 审核控制台
- `GET /api/dashboard`：控制台聚合数据
- `GET /health`：进程健康状态
- `GET /ready`：数据库和应用就绪状态
- `GET /posts`：生成帖子列表
- `GET /runs`：流水线运行历史
- `POST /api/pipeline/run`：从看板立即启动一次 Agent
- `POST /api/posts/{id}/translate/zh`：生成并缓存中文发布版
- `POST /api/posts/{id}/regenerate`：按人工意见生成新草稿
- `POST /api/posts/{id}/schedule`：保存定时发布任务

## 本地开发

如果不使用 Docker：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
pytest
ruff check .
uvicorn app.main:app --reload
```

另开终端运行：

```bash
source .venv/bin/activate
python -m app.cli run --dry-run
```

## 数据库

Docker Compose 使用命名卷持久化 SQLite 数据。主要表包括：

- `sources`
- `articles`
- `topics`
- `concepts`
- `generated_posts`
- `publication_history`
- `scheduled_publications`
- `run_history`

SQLAlchemy 模型使用可移植字段，为后续 PostgreSQL 迁移留出了空间。当前 Docker 镜像没有内置 PostgreSQL 驱动或 PostgreSQL 服务；迁移时需要先添加 `psycopg` 依赖、数据库服务、迁移脚本和备份方案，再修改 `DATABASE_URL`，例如：

```dotenv
DATABASE_URL=postgresql+psycopg://user:password@postgres:5432/ai_content
```

生产迁移前应补充数据库迁移工具和正式备份策略，不要直接复用开发环境的临时数据库凭据。

当前版本只用 `create_all` 初始化缺失的表，不会修改已有表结构，也没有内置迁移工具。因此改动既有 schema 前应先引入 Alembic 迁移，否则现有部署无法升级。

## 安全说明

- `.env` 已加入 `.gitignore`，不得提交真实密钥。
- 所有外部网页均按不可信数据处理。
- 抓取内容不会被拼接成可覆盖系统指令的提示词。
- 低置信度或证据不足的内容不会自动发布。
- HTTP 请求设置超时、重试边界和明确错误记录。
- Dry Run 是全局发布保险开关。
- Docker 默认只监听本机回环地址；Web 写操作要求专用请求头，生产环境还要求管理令牌。
- 不使用脆弱的浏览器自动化替代平台官方 API。
- API 密钥不应出现在异常、日志或生成内容中。

## 故障排查

### 启动时提示缺少 Provider 密钥

所选的 `LLM_PROVIDER` 需要对应的密钥。离线开发请改回 `LLM_PROVIDER=template`，或把密钥写入未被版本控制的 `.env`。

### 容器无法变为 healthy

```bash
docker compose ps
docker compose logs --tail=200 app
docker compose exec app python -m app.cli status
```

检查端口冲突、数据库目录权限和环境变量格式。

### GitHub 返回 403

匿名 GitHub API 有较低的限流额度。可以在 `.env` 设置只读 Token：

```dotenv
GITHUB_TOKEN=
```

不配置 Token 时，其他来源仍会继续运行。

### 没有找到可发布新闻

可能原因：

- 新闻已被历史记录判定为重复。
- 候选来源可信度或事实置信度过低。
- 内容包含疑似提示词注入。
- 来源日期过旧。
- 当前网络无法访问足够多的来源。

查看 `docker compose logs app` 和 `list-posts`，不要直接关闭安全检查。

### 质量分低于 85

检查来源是否可访问、正文是否包含无证据数字、是否使用夸张词、平台长度是否超限，以及来源链接是否保留。必要时改进 Prompt 或来源，而不是简单降低门槛。

### DeepSeek 配置后仍使用模板生成

确认 `.env` 中 `LLM_PROVIDER=deepseek`，然后强制重新创建容器：

```bash
docker compose up -d --force-recreate
docker compose exec app python -m app.cli status
```

### 端口 8000 被占用

修改 `docker-compose.yml` 中宿主机端口映射，例如改为 `8001:8000`，随后访问 `http://localhost:8001`。

### SQLite 只读或无法写入

检查 Docker 卷挂载、容器用户权限和磁盘空间：

```bash
docker compose ps
docker compose logs --tail=200 app
docker system df
```

不要直接删除数据卷，除非你确定不需要其中的内容。

### 提示已有流水线正在运行

这是并发锁在阻止重复任务。先通过 `status` 和日志确认是否确实有任务执行。只有在确认前一个进程已经异常终止后，才处理过期锁；不要在正常运行期间强行清除。

### 社交平台拒绝发布

确认官方 API 审批状态、Token 权限范围、作者或频道标识，以及当前平台 API 版本。失败记录保存在 `publication_history`，系统不会伪造成功响应。

## 推荐验收顺序

一次完整的 MVP 验收建议按以下顺序执行：

```bash
test -f .env || cp .env.example .env
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl -s http://localhost:8000/health
docker compose exec app python -m app.cli status
docker compose exec app python -m app.cli run --dry-run
docker compose exec app python -m app.cli list-posts
docker build --target test -t ai-daily-content-agent:test .
docker run --rm ai-daily-content-agent:test
```

验收成功标准：

- 容器为 `healthy`。
- 健康检查返回正常。
- Agent 至少从可用来源采集到候选内容。
- 完成标准化、去重、排名、事实核验、生成和质量检查。
- SQLite 中出现运行记录和生成帖子。
- 终端打印完整帖子和来源。
- 明确显示 `DRY RUN — publication skipped.`。
- 自动化测试全部通过。
- 没有真实社交平台发布行为。

## License

项目以开源工程结构提供。发布前请根据你的使用场景添加所需的许可证文件。
