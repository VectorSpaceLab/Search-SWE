# Faiss 属性过滤 ANN 检索后端

作者：bingyu。投稿编号：`task-1-x-1`。Implementation / CPU，版本 0.8.1。
本任务从既有任务迁移；v0.8.0 将公开和隐藏 query 分别扩为 10 条，逐条计分后取平均。

Agent 从空的 `/app` 开始，实现数据读取、Faiss ANN 索引、tag 过滤、持久化与
逐条 JSON 查询服务，通过 `build.sh`、`run.sh` 接入独立验证器。

## 任务约定

- 1,000 万个 192 维 uint8 向量，200,386 个 tag，距离为原始 squared L2。
- tag 条件按 AND 组合；每条评分查询返回精确 Top-10，边界等距邻居可互换。
- 10 条公开验证查询、10 条隐藏评测查询；每组四条单 tag、四条双 tag、两条三 tag。
- 资源分配见 `task.toml`：8 CPU、16 GiB RAM、64 GiB 存储、无 GPU；建库 600 秒。
- 服务启动后等待 `ready`，加载阶段不设独立时限，由整个检索评测的 3900 秒总超时兜底。
- `ready` 后每条查询从发送请求到响应解码最多 15 ms，包含第一条查询；启动耗时不计入查询耗时。
- 同一组 10 条隐藏查询在索引搬迁重载后再执行一次，共 20 次调用，按 10 条计分。
- 每条 query 两轮均正确、均在 15 ms 内且答案一致得 1，否则得 0；最终 reward 为十条分数的平均值。
- 单条错误或超时只扣该条分数，后续继续。通过 7 条即 0.7（70 分）；公开 query 不计分。
- 建库、索引、加载及独立轨迹审查仍是整体门槛，未通过则最终得分为 0。

完整接口和执行时限见 [instruction.md](instruction.md)。查询数量与执行时限直接写在
评分器中；CPU、内存、存储配置统一保留在 `task.toml`。v0.8.1 将建库时限改为
600 秒，移除独立的限制配置文件、进程 RSS 门槛和 12 GiB 索引大小门槛。

v0.8.1 移除独立限制配置后的全量隐藏集复验：建库 120.74 秒（新时限 600 秒），
10 条查询及重载后的 20 次请求全部通过，最慢 5.67 ms。11 项评分回归及真实
子进程异常/隔离检查通过，三条失败时仍正确得到 0.7 的检索分。模型轨迹审查未运行；
该离线运行检索分为 1，最终综合 reward 为 0。记录位于
`jobs/task-submissions/bingyu/1-x-1/simplify-limits/`（fork 仓库内的本地忽略目录）。

## 数据与隔离

本地运行数据在 `data/`；`assets.json` 记录全部 9 个输入文件的大小、SHA-256、
HF 来源和固定版本。数据共 2,865,730,488 字节，不提交到 Git。
来源、衍生方式和逐类许可见 [SOURCES.md](SOURCES.md)。

公开开发数据已发布到
[Cooki-e/search-swe-development](https://huggingface.co/datasets/Cooki-e/search-swe-development)。
`assets.json` 已固定实际 HF 提交版本，并记录逐文件大小和 SHA-256。
从仓库根目录恢复并核验：

```bash
python scripts/download_assets.py --task-path task-submissions/bingyu/1-x-1
python scripts/download_assets.py --task-path task-submissions/bingyu/1-x-1 --verify-only
```

Agent 只读挂载公开 corpus、validation、example 与环境说明。Verifier 只挂载 corpus
和环境说明，评测查询与标签放在其镜像的 `tests/data/`。参考实现保留在作者的本地
验证副本中，不属于这个投稿包，也不进入 Agent 镜像或数据集。

只有 `/app` 和真实记录的 `/logs/agent/trajectory.json` 传递给 verifier。
提交代码以无特权用户运行，不能创建 Internet socket，不获得任何模型凭据；
轨迹审查在提交进程停止后单独运行。

## 检查与运行

Python 3.12+，仓库宿主依赖和 Docker/Compose 的安装要求见
[贡献指南](../../../docs/contributing.md)。从仓库根目录执行：

```bash
python scripts/check_submission.py task-submissions/bingyu/1-x-1
python scripts/check_release.py
git diff --check
```

评分器回归测试在 verifier 镜像中运行，其中已包含 Faiss、NumPy 和 SciPy：

```bash
docker build -t search-swe-local:bingyu-1-x-1-verifier task-submissions/bingyu/1-x-1/tests
docker run --rm --network none --cpus 2 --memory 2g \
  search-swe-local:bingyu-1-x-1-verifier \
  /opt/conda/bin/python -B -m unittest discover -s /tests -p test_contract.py -v
```

真实 Agent 运行使用仓库启动器。模型 ID 按实际账号替换；先查看 dry-run：

```bash
python scripts/run_task.py --task-path task-submissions/bingyu/1-x-1 \
  --agent codex --model MODEL_ID --dry-run
```

Agent 使用 `AGENT_OPENAI_BASE_URL` / `AGENT_OPENAI_API_KEY`；轨迹审查使用独立的
`VERIFIER_OPENAI_BASE_URL` / `VERIFIER_OPENAI_API_KEY`，对应源任务已有的
`gpt-5.6-sol` Codex 审查模型及兼容 Responses 的服务端点。填写变量后，真实运行
需去掉 `--dry-run` 并指定新的 `--output jobs/...`。不要提交本机 `.env`。

Verifier 镜像在构建时安装固定版本 `harbor-rewardkit==0.1.7`，评测期间不安装依赖。
缺少凭据、真实轨迹或审查失败时，最终得分为零。离线检索通过不等于含轨迹审查的
最终评测通过。迁移的设计、执行记录和未运行检查保存在本地忽略目录
`jobs/task-submissions/bingyu/1-x-1/migration/`。

旧版 v0.7.1 的本地迁移验证中，两套镜像构建、9 项评分器回归测试和实际提交进程
隔离/异常检查通过。作者参考解在完整 1,000 万向量上通过 5 条评测查询及重载后的
10 次请求，最慢 5.58 ms，建库 136.36 秒。该离线运行没有真实 Agent 轨迹和模型
审查凭据，因此检索部分得分 1、最终综合得分 0；真实 Agent 和轨迹审查仍待验证。

v0.8.0 已在完整 1,000 万向量、8 CPU / 16 GiB 的容器中独立复验公开与隐藏两组：
每组 10 条 query、两轮共 20 次请求全部通过。公开最慢 6.02 ms，
隐藏最慢 7.15 ms；两组检索分均为 1。10 项评分回归测试通过，
真实子进程的超时、坏 JSON 和异常退出注入得到预期的 7/10 = 0.7。
本轮未调用模型审查 API，没有生成真实 Agent 轨迹；因此离线最终综合 reward 为 0，
不代表已完成含轨迹审查的端到端评测。

新版十条查询的构造与评分验证记录在本地忽略目录
`jobs/task-submissions/bingyu/1-x-1/ten-query-scoring/`。

## 审核后发布

保持当前临时编号，正式编号由维护者分配。官方数据迁移、正式编号替换和最终
GitHub 合并按同一个 PR 的流程完成；个人开发数据在官方固定版本可下载之前保留。
