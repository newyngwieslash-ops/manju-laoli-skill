# 离线管线契约加固与迁移

基线：`e95a437db944f58813198fff9cb1973c36e01ef8`。
代码候选：`2bb618b874a6339491cacecdd34aff8581d95053`（后续说明提交不改变此验证快照）。

## 已实现

| 范围 | 行为变化 | 验证 |
|---|---|---|
| 导演审计 | 从同一 loader/参数库解析 ID 与名称，9/10 与选择器一致，28→68；缺失、未知、不完整卡报错；检查完整成品块和真实数值区间，生成 `--select` 指令 | 旧卡/别名、未知 ID、关键词伪装、非法区间负例 |
| 编译 | 必填锁与明确确认、画幅路由、小数秒保真、逐段 cast/props、char_states 生效范围、真实文件读取指纹、编译前后对账；H3 错路由拒绝 | 双人竖屏文戏、道具动作、多人跨段三类固定合成样例及真实 CLI |
| 台词 | 使用 segment-map 相同 dialogue_id/speaker_id/voice_id/exact_text；逐阶段核对文本、说话人、声线、顺序、次数；逐镜与跨镜检查 | 源剧本→分镜→投喂 JSON，并解析实际编译文本对比源台词；漏词、换人、重复、改序、错误拆句负例 |
| 契约 | 结构关键词不代表交付；逐阶段 typed artifact、实体覆盖、引用文件及 hash；P4 对比当前台账的真实编译结果；C31 在 JSON 模式同样执行 | 同一 README hash 冒充所有阶段失败；有效结构记录通过、篡改文件失败 |
| 规则 | 原稿台词默认全保留；精简另列候选，明确批准后才改；继承导演切镜策略；经验配额与平台限制分层 | 修改冲突模板与技能调用；保留确认门禁 |
| 模型 | 单一 JSON 配置生成 SKILL/model-adapters 表；sd_core、validator、gate、segment-map 共用 | 配置/生成表一致性及两模型真实字符预算调用 |
| 素材/连续性 | 复用 project_state 的出入快照，记录换手/状态变化原因及镜头或相邻段引用；生成/访问/目检/批准分开 | 未知实体、空状态、错误交接、无效变更和虚假目检记录拒绝；M1 不回传仍合法 |
| 可移植性 | 测试临时路径由 tempfile 提供，UTF-8 明确，symlink 不支持时报告跳过；13 目录复制/发现 smoke；统一测试入口；Windows/Linux CI | 当前 Linux/Python 3.12 全程通过；Windows 结果以远端 CI 为准 |

本轮不改变 16 张核心卡、74 个目录编号、55 个注册编号，旧卡参数与推荐顺序不变；诺兰 P01 可选，IMAX 四事实仍待审。

## 输入迁移（不自动确认或修改项目）

原 `--state project_state.json [--out feed.md]` CLI 保留。旧输入若缺明确锁、实体作用域或台词结构，现在返回错误，而非猜值。可参考 `short-drama-director/tests/fixtures/offline/*-state.json` 的固定合成样例；其中确认与批准字段仅为测试，不可当用户项目授权。

1. `locks` 必须显式提供 `track/source/model/aspect/delivery/seam/style_card/asset_mode`，`confirmed=true` 只在项目已确认后填写。`sd_core --init-state` 生成的模板始终 `confirmed=false`。
2. 每段列出 `cast`、`props`（可为空），仅引用主档中的名称；每个主档有全局唯一 `id`。场景须存在。`entry_state/exit_state` 覆盖本段全部且仅有实体，属性为非空文本。角色台词还须匹配主档 `voice_id`。
3. `state_changes` 记录 `entity/phase/before/after/reason`。`within` 引用本段 `shot_no`；`boundary` 的 `handoff_ref` 为 `前段ID→本段ID`。新增/离场、道具换手、状态变化均需明确原因，不自动造账。
4. `char_states` 每项必须有 `segments` 生效段 ID 列表。每镜 `start/end` 为有限非负数，连续且递增；保留小数，不截断。
5. 每镜显式 `dialogue_slices`，无对白为 `[]` 且 `dialogue="无"`；有对白使用已有 `dialogue_id/speaker_id/voice_id/exact_text/integrity` 字段，与镜行台词逐字对应。当前编译器支持每镜一条完整台词；单镜多条/跨段拆句走已有 segment-map 或人工适配，不得擅自切镜。独立守恒检查支持合法 HEAD/MIDDLE/TAIL 串接。
6. `receipt.read_refs` 只接受仓库内可解析文件，脚本实际读取后输出 SHA256。无记录明确标未提供。该行为不证明 AI 语义阅读、外挂执行、人工批准或视频效果。
7. `asset_status.generated/accessible/inspected/approved` 为独立布尔字段；目检需可访问且有 `inspection_ref`，批准需目检且有 `approval_ref`。这些引用仍须人工核对真实性。M1 无回传不需要升为 M2；M2 引用图需要明确记录。

### 阶段交付记录

`audit_contract.py <稿.md> --director 68 --state project_state.json` 读取既有项目台账内 `stage_records`，不新建运行账本。每阶段是列表，每条包含 `entity_id/artifact_ref/sha256/summary`，引用相对仓库根目录的真实文件。跨阶段不能仅引用相同 README：

- P0：覆盖 `PROJECT`；JSON 为 `stage_id/entity_id/payload`，`payload.locks` 与台账一致。
- P1：覆盖全部资产 ID；`payload.asset` 与资产主档一致。
- P2：覆盖全部资产 ID；`payload.asset_id` 对齐，`views/appearance/negative_prompt` 为非空文本列表。详细模板质量仍须人工语义评审。
- P3：覆盖全部段 ID；`payload.segment` 与分镜段一致。
- P4：覆盖 `PROJECT`；引用实际编译文本，内容须与当前台账编译结果一致。
- P5：覆盖全部段 ID；`payload.entry_state/exit_state/state_changes` 与台账一致，`unresolved_conflicts=[]`。

通过表示结构/逻辑一致，不证明素材内容正确、声明的批准真实或画面连续。报告固定区分人工语义与实际生成验收；关键词合成样本不再获“全项交付通过”。

### 台词双阶段检查

```bash
python sd-feed-engine/scripts/script_feed_diff.py --script script.json --storyboard storyboard.json --feed feed-dialogues.json
```

JSON 可采用 `dialogues` 列表或既有 `payload.segments[].dialogue_slices`。零台词须明确 `dialogue_free=true`，零解析不得假通过。Markdown 兼容模式必须传完整 `--names`；疑似未知说话人直接失败。JSON 是正式可追溯路线。

批准删改用 `--approvals edits.json`，每项包含 `phase`（script-to-storyboard / storyboard-to-feed）、`dialogue_id/speaker_id/before/after/status/reason/approval_ref`；`status=approved`，明确删除用 `after=null`。无引用、原文不符、重复或阶段未参与均失败。脚本只核对记录，不授予批准。

## 模型证据边界

`short-drama-director/references/model-capabilities.json` 记录 provider、model、task_mode、source、checked_at、evidence_status。当前来源是固定仓库基线，保留原时长与字符策略，**official_limits=null**；checked_at 是项目配置核对日期，绝非官方资料核验完成日期。未核实的 API/参考素材/时长能力不能当官方事实。不得据配置替用户选择模型。

```bash
python short-drama-director/scripts/model_contract.py --write
python short-drama-director/scripts/model_contract.py
```

第一条仅更新生成表，第二条检查漂移。原检查器依赖字面硬编码的断言已改为检查单源引用、原策略数值、生成表一致性，并用实际 gate 调用验证不同模型预算；没有删除门禁或忽略失败。

## 验证结果与剩余范围

基线：39 项测试、包级检查通过。最终：**59 项测试、包级检查、validate_prompt/sd_core/compile_feed/audit_contract 自测、模型文档一致性、diff 格式检查通过**。

```bash
python -X utf8 short-drama-director/scripts/run_checks.py
```

包括原注册删除/改名/新增/重复变异、旧卡与推荐冻结输出，以及新增编译、台词、引用、状态和格式负例。独立只读评审发现的假通过已复现并修复，后续独立复验全部原负例及最后跨镜重复 ID 回归通过，无剩余阻塞发现。

CI 定义：`.github/workflows/offline-contracts.yml`，Ubuntu/Windows、Python 3.12、只读 contents 权限，无密钥、无付费调用；未完成的远端运行不能称通过。本地仅实际执行 Linux/Python；复制安装 smoke 不等于各 Agent 宿主安装认证。

尚未运行：模型生成、视频/图像视觉验收、完整宿主交互。H3 自动编译及单镜多条对白暂不支持，明确拒绝并交给既有适配流程。官方模型能力仍待核，人工语义与实际生成验收不能由本次文本机检替代。
