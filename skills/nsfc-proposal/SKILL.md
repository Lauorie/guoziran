---
name: nsfc-proposal
description: 当用户要写、重写或续写国家自然科学基金申请书正文的多个章节（立项依据、研究内容、研究基础等），或要求各章围绕同一套科学问题与假设、引用可核验时使用。先与申请人确定科学论证，再调用 nsfc-* 写作 skill 分章成稿并做跨章检查。⚠️ 不适用：只改某一章的措辞（用对应的 nsfc-*-writer）、只做评审或质检（用 nsfc-reviewers 或 nsfc-qc）、只写预算或选申请代码（用 nsfc-budget 或 nsfc-code）、尚未确定研究方向而要系统探索选题（先用 research-idea）。
metadata:
  author: Lauorie
---

# 国自然申请书正文总控

## 目标

把申请人的研究想法写成一份各章口径一致的国自然申请书正文。先建立一份科学论证，立项依据、研究内容、研究基础和摘要都从它出发；文献经检索并核对元数据后才能引用。

本 skill 负责：

- 建立并维护 `{project_root}/proposal/` 下的科学论证、证据图谱和章节分工；
- 检索文献，核对元数据后写入 `.bib`；
- 设一个确认点，请申请人确认科学问题与假设；
- 按固定顺序调用写作 skill，并做跨章一致性检查；
- 起草生成式人工智能使用说明。

本 skill 不负责：预算（nsfc-budget）、申请代码（nsfc-code）、模拟评审（nsfc-reviewers）、质检（nsfc-qc）、篇幅压缩（nsfc-length-aligner）、去 AI 腔（nsfc-humanization）、选题探索（research-idea）、PDF 排版。

## 流程

### 输入

- 必需：
  - `project_root`：含 `main.tex` 和 `extraTex/` 的 NSFC 正文项目，例如 `projects/NSFC_Young` 的副本。
  - 申请人的研究信息：题目或方向、研究对象、痛点、科学问题与假设的初步想法、已有材料。
- 可选：项目类型；要写的章节（默认全部）；协作方式；论文、数据、预实验结果；参考文献。
- 缺 `project_root` 时停下，请用户指定；无人值守时报错退出。
- 申请人没提供的信息不追问（确认点除外），按保守假设处理，并记入 `assumptions.md`。

### 执行步骤

下文 `S` 指本 skill 目录，`SK` 指 skills 根目录（本 skill 的上一级），`P` 指 project_root，`T` 指本任务目录。

**0. 说明与建目录**

1. 向用户逐项说明将调用的 skill 及其工作，按调用顺序：research-literature-search（检索文献）→ nsfc-justification-writer（立项依据）→ nsfc-research-content-writer（研究内容、特色与创新、年度研究计划）→ nsfc-research-foundation-writer（研究基础、工作条件）→ nsfc-abstract（摘要）。用户只要部分章节时，只列相关的 skill。
2. 宣布唯一任务目录 `T = ./.bensz-api/task-{yyyymmdd-hhmm}-{简短描述}/`，之后不更换。建立 `T/README.md`、`T/shared/` 和 `T/nsfc-proposal/{input,output,log}/`。
3. 此后每完成一步，在 `T/nsfc-proposal/log/stages.md` 追加一行：时间、步骤、AI 做了什么、产出文件、申请人是否确认。第 8 步据此起草 AI 使用说明。

**1. 材料与项目画像**

```bash
python3 S/scripts/case.py init --project-root P --title "<题目>" --type "<项目类型>" [--sections 立项依据,研究内容]
```

把命令输出中的 ⚠️ 提示转告用户，例如模板没有引用 AI 使用说明文件。

**2. 科学论证**

按 `references/scientific_case_guide.md` 填写 `P/proposal/scientific_case.yaml`。论证用到的每条论断同时写入 `P/proposal/evidence_map.yaml`，`support` 记为 `unsupported`，`evidence` 留空。然后运行：

```bash
python3 S/scripts/case.py validate --project-root P
```

第 2、3 步只要求 `[scientific_case]` 和 `[evidence_map]` 前缀的问题清零。`[section_plan]` 前缀的问题（如研究基础的占位尚未登记）留到第 4 步解决；进入第 5 步前全部清零。

各列表条目和论断条目的字段写法见 `references/scientific_case_guide.md` 的「列表条目的写法」和 `references/evidence_wording.md` 的「论断条目的写法」。

**3. 文献与证据**

1. 生成 5–25 条英文关键词检索式，写入 `T/nsfc-proposal/input/keyword_queries.json`（格式 `{"queries": [...]}`），并抄入 `P/proposal/literature_leads.md` 的「## 检索式」。
2. 对每条 `gap`、`mechanism` 类论断写一个英文问句，写入 `T/nsfc-proposal/input/claim_queries_1.json`；超过 25 条时拆成 `claim_queries_2.json` 等。
3. `config.yaml` 中 `literature.use_wispaper` 为 true，且宿主有 `mcp__wis-scholar-search__quick_search` 工具时：
   - 每条关键词检索式调用 `quick_search`，`top_n` 取 `literature.quick_search_top_n`；
   - 每个论断问句调用 `deep_search`，`top_n` 取 `literature.deep_search_top_n`；
   - 把原始返回逐字存成 `rls.host_results.v1` 文件：`T/nsfc-proposal/output/wispaper/keyword_host.json`、`claims_host_1.json` 等。格式见 `SK/research-literature-search/SKILL.md`。不得改写论文字段。
4. 建检索 bundle 并校验：

```bash
python3 SK/research-literature-search/scripts/search_runner.py run --topic "<题目>" \
  --query-file T/nsfc-proposal/input/keyword_queries.json \
  --output-dir T/research-literature-search/output/keyword-bundle \
  --max-results-per-query 20 --host-results T/nsfc-proposal/output/wispaper/keyword_host.json
python3 SK/research-literature-search/scripts/search_runner.py run --topic "<题目>" \
  --query-file T/nsfc-proposal/input/claim_queries_1.json --min-queries 1 \
  --output-dir T/research-literature-search/output/claims-bundle-1 \
  --max-results-per-query 10 --no-fallback --host-results T/nsfc-proposal/output/wispaper/claims_host_1.json
python3 SK/research-literature-search/scripts/search_runner.py validate --bundle <每个 bundle 目录>
```

   没有 wispaper 时去掉 `--host-results`；论断 bundle 同时去掉 `--no-fallback`。
5. 逐条论断从各 bundle 的 `candidates_deduped.jsonl` 中挑候选证据，原样写入 `T/nsfc-proposal/output/selected.jsonl`，再补全摘要：

```bash
python3 SK/research-literature-search/scripts/search_runner.py enrich-abstracts \
  --input T/nsfc-proposal/output/selected.jsonl --output T/nsfc-proposal/output/selected_enriched.jsonl
```

6. 核对元数据并写入 `.bib`：

```bash
python3 S/scripts/bib_resolve.py --project-root P --records T/nsfc-proposal/output/selected_enriched.jsonl --task-root T
```

   输出中 `added` 或 `exists` 条目的 bibkey 是候选引用键；`unresolved` 条目已写入线索清单，正文不得引用。能否在正文引用，取决于规则 5 的三个条件。
7. 阅读完整摘要，按 `references/evidence_wording.md` 填写每条论断的 `evidence` 与 `support`，再运行 `case.py validate`，直到 `[scientific_case]` 和 `[evidence_map]` 前缀的问题清零。

完全离线时跳过 3–6：文献类论断保持 `unsupported`，并在 `assumptions.md` 的「## 待核实项」写明「本次未检索文献」。证据不足时，`section_plan.yaml` 的篇幅是上限，不是必须写满的目标；不用推测或泛泛的背景凑字数。

**4. 章节分配**

按 `references/section_boundaries.md` 填写 `P/proposal/section_plan.yaml` 各文件的 `must_include`、`must_exclude` 和 `placeholders`。`scientific_case.yaml` 中 `source: missing` 的可行性条目，逐条写进研究基础的 `placeholders`。然后运行下面两条；此时 `[section_plan]` 前缀的问题也要清零。

```bash
python3 S/scripts/case.py validate --project-root P
python3 S/scripts/case.py render --project-root P
```

**5. 确认点**

按 `references/confirm_prompt.md` 展示 `P/proposal/scientific_case.md` 的要点，然后停下，等申请人回答：

| 回答 | 动作 |
|---|---|
| 同意 | `python3 S/scripts/case.py status --project-root P --set confirmed` |
| 同意并改其中几条（如「同意，第 2 条改成……」） | 按「修改」处理：修改 YAML → `case.py bump` → `case.py validate`。改动涉及科学问题、假设或术语时重新展示；否则 validate 通过后执行 `--set confirmed`。不在 `bump` 之前设 confirmed，`bump` 会把状态重置为 draft |
| 修改：…… | 修改 YAML → `case.py bump` → `case.py validate` → 重新展示 |
| 先继续 | `python3 S/scripts/case.py status --project-root P --set bypassed` |

`confirm.mode` 为 `auto`，或用户要求「全自动」「无人值守」时，不停下，直接执行 `--set bypassed`。

**6. 分章写作**（顺序固定）

每一章都遵守七条规则：

- 规则 1：措辞不超过 `evidence_map.yaml` 中对应论断的 `support`。
- 规则 2：不写 `must_exclude` 中的内容。
- 规则 3：缺失的信息写成可见占位 `【待补充：……】`，并逐条列入 `assumptions.md` 的「## 占位清单」（格式：`- 文件：【待补充：……】`）。
- 规则 4：正文不出现内部编号。
- 规则 5：凡是叙述研究现状、他人方法或结论、流行病学数据的句子，必须 `\cite`，且只能引用同时满足三条的 bibkey：(a) 经 `bib_resolve.py` 进入 `.bib`（`added` 或 `exists`）；(b) 列在这句话所表达的那条论断的 `evidence` 中，`role` 为 supporting；(c) 措辞不超过该论断的 `support`。内容没有对应论断时，先按第 3 步把论断补进 `evidence_map.yaml`，或改写为推测（「可能」「尚不清楚」）、删去。不把某项具体研究的结果改写成「可能」来回避引用：转述某项研究发现了什么的句子，必须引用该研究。一个段落讲几项研究，就逐项引用，不在段末堆一个引用。申请人自己的结果按申请人材料写或写占位，不需 `\cite`（材料本身是已入 `.bib` 的已发表论文时才引用）；本项目自己的设计、目标和假设不是现状，不需引用；教科书级定义不需引用，除非引用具体标准或指南（此时引用或写明名称）。示例见 `references/evidence_wording.md` 的「哪些句子必须引用」。
- 规则 6：证据不足时，`section_plan.yaml` 的篇幅是上限，不是必须写满的目标。不用推测或泛泛的背景凑字数；字数不足的原因写进收尾报告。
- 规则 7：被调用的写作 skill 若在自己的说明里要向用户提问（确认 project_root 或 output_mode、确认后创建 `extraTex`、nsfc-abstract 多次超长裁剪后让用户选方案等），一律不问，取保守默认（保留已有文件、按配置先预览再应用、停止裁剪并保留当前版本），把决定记入 `T/nsfc-proposal/log/stages.md`，并列入最终报告。整个流程只有第 5 步向用户提问。

6.1 立项依据：

   ```bash
   python3 S/scripts/case.py to-info-form --project-root P --writer nsfc-justification-writer --out T/nsfc-proposal/output/info_form_justification.md
   ```

   按 `SK/nsfc-justification-writer/SKILL.md` 执行。`--task-root T` 是顶层选项，放在子命令之前，例如 `python3 SK/nsfc-justification-writer/scripts/run.py --task-root T coach --project-root P --info-form T/nsfc-proposal/output/info_form_justification.md`；每条 CLI 命令都这样加。`coach` 加 `--info-form T/nsfc-proposal/output/info_form_justification.md`。写入后运行 `python3 S/scripts/case.py mark-written --project-root P --file extraTex/1.1.立项依据.tex`。
6.2 研究内容、特色与创新、年度研究计划：用 `--writer nsfc-research-content-writer` 生成信息表，按 `SK/nsfc-research-content-writer/SKILL.md` 执行。写完直接运行 `python3 SK/nsfc-research-content-writer/scripts/check_project_outputs.py --project-root P`，三个文件逐一 `mark-written`。不用 `run_checks.py`：它先跑 `validate_skill.py`，后者在当前版本中会因打包问题提前退出，检查没有执行。
6.3 研究基础、工作条件：用 `--writer nsfc-research-foundation-writer` 生成信息表，按 `SK/nsfc-research-foundation-writer/SKILL.md` 执行。写完同样直接运行 `python3 SK/nsfc-research-foundation-writer/scripts/check_project_outputs.py --project-root P`，两个文件逐一 `mark-written`。
6.4 摘要：按 `SK/nsfc-abstract/SKILL.md` 在 `P` 下写 `NSFC-ABSTRACTS.md`，科学问题与术语以科学论证为准，然后 `mark-written --file NSFC-ABSTRACTS.md`。

**7. 跨章一致性检查**

```bash
python3 S/scripts/consistency_check.py --project-root P
```

- 「必须修正」：回到对应的写作 skill 修改，再查；最多 `consistency.max_fix_rounds` 轮。仍不通过的写进收尾报告。
- 「需要复核」：逐条判断。确属内部编号的改成自然语言；属于误报的（如「T1 加权」）在 `T/nsfc-proposal/log/stages.md` 记下理由。
- 数值对照：运行 `python3 S/scripts/consistency_check.py --project-root P --numbers`，按单位对照数值清单。同一参数（环带宽度、阈值、例数、年限、任务数等）在各章取值必须一致；确有不同时，在正文中写明原因（例如一处是文献报道值，一处是本项目设定值，并写清来源）。处理结果记入 `stages.md`。
- 语义检查由 AI 完成：各章的科学问题与假设表述一致；研究内容的任务与科学问题一一对应；研究基础覆盖每个任务的可行性。
- 现状句检查：通读立项依据、研究内容、特色与创新、研究基础和摘要中凡叙述研究现状或他人结论的部分，逐句找出叙述研究现状、他人方法或结论、流行病学数据却没有 `\cite` 的句子，按规则 5 补引用或改写为推测，也检查有引用的句子是否满足 (b)(c)。处理结果记入 `stages.md`。
- 同步改动：科学论证中的术语、分组名称、研究任务数改过后，用 `grep` 在全部正文和 `assumptions.md` 中查旧说法，逐处改成新说法。

**8. 收尾**

1. 起草 AI 使用说明，写入 `section_plan.yaml` 中 writer 为 `nsfc-proposal` 的文件（`extraTex/4.5.生成式人工智能.tex` 或 `proposal/ai_declaration.md`）。只写 `stages.md` 里记录过的使用。第一行写 `【待补充：申请人核对本声明后删除此行】`，并列入占位清单。
2. 再运行一次 `consistency_check.py`。
3. 项目有编译脚本且本机字体齐全时编译，用 `pdfinfo` 记页数。超过 28 页时在报告中写明页数，并建议用 nsfc-length-aligner 压缩。字体缺失导致编译报错时，写「页数未核」。各章篇幅取自 nsfc-length-aligner 的下限时，加上参考文献，正文仍可能超过 30 页。
4. 按「输出」一节的格式向用户报告。申请人在确认点只答「同意」时，把 AI 拟定项在报告中再列一次，标「申请人未逐条回应」。
5. 用户要求时，调用 nsfc-reviewers 或 nsfc-qc。

### 输出

- `P/proposal/`：`scientific_case.yaml`、`scientific_case.md`、`evidence_map.yaml`、`section_plan.yaml`、`assumptions.md`、`literature_leads.md`；模板没有引用 AI 使用说明文件时，还有 `ai_declaration.md`。
- `P/extraTex/` 下的各章正文，以及 `P/NSFC-ABSTRACTS.md`。
- `main.tex` 指向的 `.bib` 中新增的已核实条目。

每轮回复用这个格式：

```text
当前进度：……
我刚完成：……
下一步：……
需要你确认：……（没有就写「无」）
```

最终报告还要列出：写入的文件、占位清单、待核实项、未解决的一致性问题、建议的下一步（编译、nsfc-length-aligner、nsfc-reviewers、nsfc-qc）。

### 输出管理

- 正式交付物写在 `P` 中。过程文件只写在 `T` 中：wispaper 原始返回、检索 bundle、信息表、`.bib` 备份、`bib_resolve.json`、运行日志。
- `T` 中不保存密钥、令牌和个人身份信息；HTTP 请求不附带个人邮箱。
- 不修改 `main.tex`、`extraTex/@config.tex` 和任何 `.cls`、`.sty`；`.bib` 只追加。

### 校验

- 第 2、3 步：`case.py validate` 中 `[scientific_case]` 和 `[evidence_map]` 前缀的问题清零。进入第 5 步前：全部问题清零。
- 写作期间：各写作 skill 自带的检查通过（立项依据的 Tier2、研究内容和研究基础的 `check_project_outputs.py`、摘要的 `validate_abstract.py`）。
- 收尾前：`consistency_check.py` 的「必须修正」为 0，或剩余问题已写入报告。
- 篇幅：`python3 SK/nsfc-length-aligner/scripts/check_length.py --input P`。
- 项目有编译脚本且本机字体齐全时运行它（如 `python3 P/scripts/nsfc_build.py build --project-dir P`），确认 PDF 生成，并用 `pdfinfo` 记页数；超过 28 页，报告写明页数并建议用 nsfc-length-aligner 压缩。字体缺失导致报错时，写「页数未核」。

### 失败与恢复

| 情况 | 处理 |
|---|---|
| `case.py validate` 在第 4 步后仍有问题 | 不进入写作；按提示修改后重试 |
| wispaper 不可用 | 不传 `--host-results`，改用 research-literature-search 的现有检索源 |
| CrossRef 与 OpenAlex 都不可达 | 不新增 `.bib` 条目；相关论断记为 `unsupported` |
| 某个写作 skill 失败 | 保留已写章节；从 `section_plan.yaml` 中 `written_with_case_version` 为空或低于当前版本的章节继续 |
| 写完后科学论证又被修改 | `case.py bump` 后，一致性检查会列出依据旧版的章节，逐章重写 |
| 一致性检查 2 轮后仍不通过 | 停止重试，问题列入报告 |
| 编译失败 | 报告错误位置；不改动结构命令 |
| `.bib` 写入出错 | 用 `T/nsfc-proposal/output/bib_backup/` 中的备份恢复 |

## 约束

### 公共硬约束

- 任务需要落盘时，使用唯一的 `./.bensz-api/task-{yyyymmdd-hhmm}-{简短描述}/` 根目录；共享材料放入 `shared/`，Skill 专属材料放入该 Skill 的 `input/`、`output/`、`log/`。
- 正式交付物、源代码和正式计划按项目约定保存，不写入任务工作区；未经授权不覆盖、删除、迁移或远程写入。
- 项目维护变更检查 BAC 可用性并记录需求、AI 产出、工具结果、文件改动和验证摘要；BAC 只做过程审计，不替代署名、责任或合规判断。
- 不记录 API Key、访问令牌、密码、Cookie、环境/凭据文件、私有 Prompt、身份信息、本地用户名、主机名或不必要的大体积原始数据。
- 文件路径必须规范化并限制在授权项目范围内；外部 URL、子进程和网络访问遵循最小权限，防止路径遍历、SSRF 和命令注入。
- Skill 版本唯一记录在自身 `config.yaml:skill_info.version`；公开 API、协议、目录或配置变更同步文档与 `CHANGELOG.md`。
- 仅将 Skill 或 Bensz 基础设施本身的设计缺陷交给 `bensz-collect-bugs`；先脱敏写入 `~/.bensz-skills/bugs/`，当前任务不中断，只有用户明确要求才公开上报，禁止直接修改用户已安装的 Skill 源码。
<!-- End of canonical common constraints. -->

### Skill 专属约束

- 不编造文献、数据、病例数、前期成果和合作单位；申请人没提供的内容只写占位。
- 文献的作者、期刊、年份、卷期页码只取自 CrossRef 或 OpenAlex 的返回，不凭记忆填写。
- 全流程只有一个确认点；其余步骤不打断用户。
- 不调用 research-idea。需要系统探索选题时，建议用户先运行它，再把结论写进 `scientific_case.yaml`。
