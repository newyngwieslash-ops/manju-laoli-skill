# 导演风格系统：20 轮工程验收

本批 R01–R20 独立计数。完成 20 轮：4 轮保留缺陷修复、16 轮审计无需代码修改、0 轮回滚。测试覆盖改善与验收报告随最终交付保存，不另计迭代轮数。

范围仅为现有加载器、选择入口和兼容性。完整卡 15、目录 74、注册并集 55 均不变。P01 仍可选、四条 IMAX 事实仍待审；无模型/视频实测。

## 固定提交与方法

测试在 R01 变更前冻结，此后未改；源码 SHA256：`f3c992d80981fdb72558fc7486dae5c2c885a2ec356a3f4ee0def44ca53ff259`。最终保存为 `short-drama-director/tests/test_style_audit_20.py`。每轮在修改前读取实际提交 SHA，修改后提交并再次测试；无改动轮 before/candidate 相同，不把提交后的 HEAD 充作改前版本。

- B0: `810d40ff98a8ed5f191f3a3925a6d7094d1dd9eb`
- B1: `46020f60556d5e18de95ced4e8500c32d059c806`
- B2: `f493bd293ee8e5fbd3a1203e847dcfee0ea771c9`
- B3: `c2ed9ae7ca5159685fd1c630512865909f7010e7`
- B4: `28318a67183b3b931652414c24c4da7ac3caf0cd`

每轮命令均从仓库根执行：

```bash
python3 short-drama-director/tests/test_style_audit_20.py StyleAudit20.<下表测试方法> -v
```

复现旧提交时，用临时归档提供源代码，并设置 `STYLE_AUDIT_ROOT=<归档>/short-drama-director`；运行同一份冻结测试。所有文件损坏/路径实验仅在临时副本执行。

## 逐轮记录

| 轮次 | 假设或风险 | before → candidate | 测试方法 | 真实结果与结论 |
| --- | --- | --- | --- | --- |
| R01 | 空源文档应返回可处理错误 | B0 → B1 | `test_R01_empty_documents` | 空文件触发 IndexError；修复空段过滤，改后 ValueError。 保留修复（改前测试退出 1，候选退出 0） |
| R02 | API 编号类型不可绕过诺兰填参 | B1 → B2 | `test_R02_api_style_id_types` | 字符串编号可输出未替换占位符；限制为正整数且拒绝布尔值。 保留修复（改前测试退出 1，候选退出 0） |
| R03 | 区间容器不得把文本当成两个数字 | B2 → B3 | `test_R03_api_range_container_types` | 标量/迭代器触发 TypeError，字符串及 bytes 被误接收；明确仅接受二元素 list/tuple。 保留修复（改前测试退出 1，候选退出 0） |
| R04 | 项目占位符不能被静态值或错槽替代 | B3 → B4 | `test_R04_template_placeholder_integrity` | 临时模板改成固定值仍可输出；增加唯一性与槽位位置检查。 保留修复（改前测试退出 1，候选退出 0） |
| R05 | 重复章节不能静默选第一项 | B4 → B4 | `test_R05_duplicate_sections` | 两个源文件分别复制编号 36 章节，均被拒绝。 无需代码修改（实验退出 0） |
| R06 | 11 槽位删除或重复不能通过 | B4 → B4 | `test_R06_slot_deletion_and_duplication` | 分别删除、重复第 5 行，均被拒绝。 无需代码修改（实验退出 0） |
| R07 | 成品块额外代码段或次序错乱不能通过 | B4 → B4 | `test_R07_fenced_block_count_and_order` | 增加第三个围栏块、调换两段次序均被拒绝。 无需代码修改（实验退出 0） |
| R08 | 源文件缺失应是 CLI 错误而非崩溃 | B4 → B4 | `test_R08_missing_source_cli` | 两个入口均返回 2，stdout 为空、stderr 无 traceback。 无需代码修改（实验退出 0） |
| R09 | 非法 UTF-8 应是 CLI 错误而非崩溃 | B4 → B4 | `test_R09_invalid_utf8_cli` | 写入非法字节后，两个入口均返回 2 且无部分输出。 无需代码修改（实验退出 0） |
| R10 | BOM/CRLF 不应改变投喂文本 | B4 → B4 | `test_R10_bom_crlf_compatibility` | 两个源文件转换为 UTF-8 BOM/CRLF，输出逐字一致。 无需代码修改（实验退出 0） |
| R11 | 中文与空格路径不应改变旧卡输出 | B4 → B4 | `test_R11_unicode_space_paths` | 复制到中文及空格目录，从其他 cwd 调用两入口，输出与原路径一致。 无需代码修改（实验退出 0） |
| R12 | 符号链接入口应能定位真实资源 | B4 → B4 | `test_R12_symlink_entrypoints` | 两个脚本的临时符号链接均能输出完整卡。 无需代码修改（实验退出 0） |
| R13 | 互斥或错误 CLI 参数必须拒绝 | B4 → B4 | `test_R13_argument_conflicts` | 每入口 5 组参数冲突/缺失均返回 2，help 正常。 无需代码修改（实验退出 0） |
| R14 | 等值十进制写法应得到同一输出 | B4 → B4 | `test_R14_equivalent_numeric_spellings` | 指数、前导零、正号及尾随零均标准化为相同项目数值。 无需代码修改（实验退出 0） |
| R15 | 外部 Decimal 精度上下文不得改参数 | B4 → B4 | `test_R15_decimal_context_independence` | 精度设为 1 并启用 Inexact/Rounded 陷阱，输出仍逐字一致。 无需代码修改（实验退出 0） |
| R16 | 行宽边界不能舍入或截断数值 | B4 → B4 | `test_R16_output_width_boundary` | 扫描 1–18 位焦距值：可输出值原样保留，超限明确拒绝，所有成功行不超过 42 字。 无需代码修改（实验退出 0） |
| R17 | 选卡与错误请求不写源或项目 | B4 → B4 | `test_R17_cli_read_only` | 禁写 pycache 的临时副本中，成功/错误 CLI 前后文件集合与内容哈希一致。 无需代码修改（实验退出 0） |
| R18 | 所有已注册编号要么有完整卡要么明确缺失 | B4 → B4 | `test_R18_every_registered_style_loadability` | 遍历两表共 92 条记录；完整卡可加载，非完整卡明确 ValueError。 无需代码修改（实验退出 0） |
| R19 | 研究元数据不得自动成为投喂内容 | B4 → B4 | `test_R19_research_is_not_prompt_input` | 在临时源追加可选/待审元数据，输出不变且无 P01/IMAX/导演名。 无需代码修改（实验退出 0） |
| R20 | C23 必须保留边界值并拦截越界 | B4 → B4 | `test_R20_c23_boundaries` | 3 组焦距区间的上下端点通过，焦距及光比双越界均产生 C23b。 无需代码修改（实验退出 0） |

## 总体验收

- 新增 20 个不同审计方法，加既有 13 项，共 33 项回归；旧 14 卡输出与 12 个推荐场景指纹保持冻结基准。
- 两个入口的删除、改名、新增编号、重复编号共 8 个注册变异继续被拒绝。
- 全部 33 项测试、完整包检查、校验器自测及差异格式检查通过。冻结测试回放总基线 B0 时，缺陷集中在 R01–R04（4 个失败断言、3 个错误）；候选全部通过。
- 独立只读复核从各轮固定 before 提取源码复现 R01–R04，确认 20 轮日志、提交与结论一致；独立运行 33 项测试、包检查和差异格式检查通过，无阻塞发现。
- 研究说明、公开来源、参数卡、注册表和默认 A 未修改。未自动合并、部署或创建调度。

可复跑命令：

```bash
python3 -m unittest discover -s short-drama-director/tests -v
python3 short-drama-director/scripts/check_package.py
python3 short-drama-director/scripts/validate_prompt.py --self-test
python3 short-drama-director/scripts/style-lock-ladder.py --select 36
python3 short-drama-director/scripts/style-lock-recommend.py --select 36 --format prompt --light-range 2.5 6.25 --lens-range 35 50
```

最后一条数值仅为测试输入，不是创作默认值。路径与符号链接验证覆盖当前 Linux/Python 环境，不代表所有操作系统均已实测；只读实验显式关闭 Python 字节码缓存。远端 CI 仅以 GitHub 实际记录为准。
