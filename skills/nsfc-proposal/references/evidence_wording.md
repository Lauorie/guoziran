# 证据与措辞强度

## 怎样判断一条证据

- 只读完整摘要或全文。只有摘要片段（以「…」开头或结尾）的论文，不能作为支持证据。
- 每条证据写明 `role`：支持（supporting）还是反驳（counter）。找到反驳证据时照实记录，不要删掉。
- `basis` 写判断依据：`fulltext`（全文）或 `full_abstract`（完整摘要）。
- `ref` 写 bibkey；只有线索、没有进入 `.bib` 的，写 `lead:L<编号>`，它不计入已核实证据。

## 支持程度与正文写法

| support | 条件 | 正文写法 |
|---|---|---|
| `multi_verified` | 至少 2 条支持证据，`ref` 为 bibkey，`basis` 为全文或完整摘要 | 可写「多项研究表明」 |
| `single_verified` | 恰好 1 条这样的证据 | 只写「有研究报道」，不写成共识 |
| `unsupported` | 没有已核实证据 | 不写成事实；改为推测（「可能」「尚不清楚」），或删去 |
| `applicant_material` | 申请人提供的材料（只用于 `applicant_result` 类论断） | 按材料原样写，不夸大 |

`case.py validate` 会检查 `support` 是否超出证据实际能支撑的程度。

## 例句

- multi_verified：多项研究表明，瘤周区域特征可提供瘤内特征之外的信息\cite{a,b}。
- single_verified：有研究报道，重建核改变后部分纹理特征的重复性下降\cite{c}。
- unsupported：这一对应关系在不同扫描参数下是否稳定，目前尚不清楚。
- 缺材料：本课题组已完成预实验【待补充：预实验的样本量与主要结果】。

## 论断条目的写法

`evidence_map.yaml` 的 `claims` 列表中，一条论断这样写：

```yaml
claims:
  - id: C1
    text: "……"
    sections: ["立项依据"]
    type: gap                    # background | gap | mechanism | applicant_result
    support: multi_verified      # multi_verified | single_verified | unsupported | applicant_material
    evidence:
      - ref: smith2020example    # .bib 中的 bibkey，或 lead:L<编号>
        role: supporting         # supporting | counter
        basis: full_abstract     # fulltext | full_abstract
      - ref: "lead:L3"
        role: counter
        basis: full_abstract
```

流程第 2 步（科学论证）新增论断时一律写 `support: unsupported`、`evidence: []`；第 3 步读完摘要后再改。`applicant_material` 只用于 `type: applicant_result`。
