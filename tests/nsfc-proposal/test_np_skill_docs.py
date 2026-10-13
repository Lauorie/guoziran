# tests/nsfc-proposal/test_np_skill_docs.py
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "nsfc-proposal"
SKILLS = ROOT / "skills"
TEXT = (SKILL / "SKILL.md").read_text(encoding="utf-8") if (SKILL / "SKILL.md").exists() else ""
ORDER = ["## 目标", "## 流程", "### 输入", "### 执行步骤", "### 输出", "### 输出管理", "### 校验", "### 失败与恢复", "## 约束"]


def frontmatter() -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", TEXT, re.S)
    return yaml.safe_load(match.group(1)) if match else {}


class SkillDocTest(unittest.TestCase):
    def test_frontmatter(self) -> None:
        meta = frontmatter()
        self.assertEqual(meta.get("name"), "nsfc-proposal")
        self.assertEqual((meta.get("metadata") or {}).get("author"), "Lauorie")
        description = meta.get("description") or ""
        self.assertTrue(description)
        for leak in ("proposal/", ".yaml", "case.py", "--"):
            self.assertNotIn(leak, description)

    def test_section_order_and_no_control_section(self) -> None:
        headings = [line for line in TEXT.splitlines() if line.startswith(("## ", "### "))]
        positions = [headings.index(h) for h in ORDER]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("## 控制", TEXT)

    def test_common_constraints_block_is_verbatim(self) -> None:
        template = (ROOT / "docs/templates/skill-common-constraints.md").read_text(encoding="utf-8").splitlines()
        block = "\n".join(template[1:]).strip()
        self.assertIn(block, TEXT)

    def test_referenced_files_exist(self) -> None:
        self.assertNotIn("SK/", TEXT)
        local = set(re.findall(r"(?<![A-Za-z])S/((?:scripts|references|assets)/[\w.\-]+)", TEXT))
        local |= set(re.findall(r"`(references/[\w.\-]+\.md)`", TEXT))
        self.assertTrue(local)
        for rel in sorted(local):
            self.assertTrue((SKILL / rel).is_file(), rel)

    def test_config_guides_exist(self) -> None:
        config = yaml.safe_load((SKILL / "config.yaml").read_text(encoding="utf-8"))
        guides = {s["guide"] for s in config["sections"] if s.get("guide")}
        self.assertEqual(len(guides), 4)
        for rel in sorted(guides):
            self.assertTrue((SKILL / rel).is_file(), rel)
            self.assertIn(f"`{rel}`", TEXT, rel)

    def test_version_only_in_config(self) -> None:
        config = yaml.safe_load((SKILL / "config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(config["skill_info"]["version"], "0.5.1")
        self.assertNotIn("0.5.1", TEXT)
        self.assertNotIn("0.5.1", (SKILL / "README.md").read_text(encoding="utf-8"))

    def test_changelog(self) -> None:
        changelog = (SKILL / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [0.5.1] - 2026-10-13", changelog)
        self.assertLess(changelog.index("## [0.5.1]"), changelog.index("## [0.5.0]"))
        self.assertIn("## [0.5.0] - 2026-10-13", changelog)
        self.assertLess(changelog.index("## [0.5.0]"), changelog.index("## [0.4.0]"))
        self.assertIn("## [0.4.0] - 2026-10-13", changelog)
        self.assertLess(changelog.index("## [0.4.0]"), changelog.index("## [0.3.0]"))
        self.assertIn("## [0.3.0] - 2026-10-12", changelog)
        self.assertLess(changelog.index("## [0.3.0]"), changelog.index("## [0.2.0]"))
        self.assertIn("## [0.2.0] - 2026-10-12", changelog)
        self.assertIn("## [0.1.0] - 2026-10-09", changelog)
        self.assertLess(changelog.index("## [0.2.0]"), changelog.index("## [0.1.0]"))
        self.assertIn("初始化技能，实现核心功能", changelog)
        self.assertIn("本分支未写 BAC 记录，经负责人同意。", changelog)


class RoundThreeDocsTest(unittest.TestCase):
    def test_figure_labels_carry_no_brackets(self) -> None:
        guide = (SKILL / "references" / "figure_guide.md").read_text(encoding="utf-8")
        self.assertIn("不加括号、引号或书名号", guide)
        self.assertIn("连同〈〉一起换掉", guide)
        self.assertIn("没有清单以外的符号", guide)
        self.assertIn("英文、拼音、汉字或符号", guide)
        rule = [ln for ln in guide.splitlines() if ln.startswith("图中所有可见文字只能使用以下内容")]
        self.assertEqual(len(rule), 1)
        self.assertNotIn("〈", rule[0])
        self.assertNotIn("〉", rule[0])

    def test_wispaper_step_states_foreground_timeout_and_rerun(self) -> None:
        blocks = [b for b in re.split(r"\n(?=\d+\. )", TEXT) if "wispaper_search.py run" in b and b.lstrip().startswith("4. ")]
        self.assertEqual(len(blocks), 1)
        self.assertIn("600000", blocks[0])
        self.assertIn("原样重跑", blocks[0])

    def test_motor_matched_control_rule(self) -> None:
        bounds = (SKILL / "references" / "research_content.md").read_text(encoding="utf-8")
        self.assertIn("动作匹配的对照", bounds)
        self.assertIn("出声朗读", bounds)
        self.assertIn("前三条", bounds)

    def test_build_command_has_no_relative_project_dir(self) -> None:
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`python3 P/scripts/nsfc_build.py`", skill)
        self.assertNotIn("nsfc_build.py build --project-dir P", skill)


class RoundFiveRetrievalDocsTest(unittest.TestCase):
    def test_flow_never_mentions_other_search_services(self) -> None:
        for rel in ("SKILL.md", "README.md", "scripts/bib_resolve.py", "scripts/bib_refresh.py"):
            text = (SKILL / rel).read_text(encoding="utf-8").lower()
            for name in ("openalex", "semantic scholar", "semantic_scholar"):
                self.assertNotIn(name, text, f"{rel}: {name}")

    def test_pools_are_wispaper_only(self) -> None:
        self.assertIn("literature.py pool", TEXT)
        self.assertNotIn("--provider-order", TEXT)
        self.assertNotIn("search_runner.py", TEXT)
        self.assertNotIn("--no-fallback", TEXT)
        self.assertNotIn("其他检索源", TEXT.replace("不改用其他检索源", ""))

    def test_abstracts_come_from_wispaper_offline(self) -> None:
        self.assertIn("literature.py abstract-queries", TEXT)
        self.assertIn("--name abstracts_1 --tool quick_search", TEXT)
        self.assertIn("literature.py enrich-abstracts", TEXT)
        self.assertNotIn("--offline", TEXT)
        self.assertNotIn("exhausted_providers", TEXT)

    def test_wispaper_unavailable_stops(self) -> None:
        row = [ln for ln in TEXT.splitlines() if ln.startswith("| wispaper 不可用")]
        self.assertEqual(len(row), 1)
        self.assertIn("停在第 3 步", row[0])
        self.assertIn("不改用其他检索源", row[0])


class RoundFiveWritingDocsTest(unittest.TestCase):
    def test_subheadings_follow_each_study_type(self) -> None:
        bounds = (SKILL / "references" / "research_content.md").read_text(encoding="utf-8")
        self.assertIn("小标题按每项研究的类型选", bounds)
        self.assertIn("各用各的一组", bounds)
        self.assertNotIn("全章一致", bounds)
        self.assertNotIn("每项用同一组小标题", bounds)
        self.assertIn("不为统一改用另一组", TEXT)
        self.assertNotIn("要求每项研究内容用同一组，全章一致", TEXT)

    def test_figures_draw_stimuli_as_icons_and_reject_photos(self) -> None:
        guide = (SKILL / "references" / "figure_guide.md").read_text(encoding="utf-8")
        self.assertEqual(guide.count("无照片、无写实渲染"), 2)
        self.assertIn("画成线描图标", guide)
        self.assertIn("没有照片或写实渲染的图像", guide)


class RoundSixFigureDocsTest(unittest.TestCase):
    def test_figure_guide_checks_icon_counts(self) -> None:
        guide = (SKILL / "references" / "figure_guide.md").read_text(encoding="utf-8")
        self.assertIn("数量：", guide)
        self.assertIn("在提示词中写明个数", guide)
        self.assertIn("重复图标的个数与 Brief 一致", guide)


class FusionDocsTest(unittest.TestCase):
    SIBLINGS = ("nsfc-justification-writer", "nsfc-research-content-writer", "nsfc-research-foundation-writer",
                "nsfc-abstract", "nsfc-length-aligner", "research-literature-search")

    def test_no_sibling_skill_names(self) -> None:
        suffixes = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".tex", ".sh"}
        hits = [f"{p.relative_to(SKILL)}: {name}" for p in sorted(SKILL.rglob("*"))
                if p.is_file() and p.suffix in suffixes and p.name != "CHANGELOG.md" and "__pycache__" not in p.parts
                for name in self.SIBLINGS if name in p.read_text(encoding="utf-8", errors="ignore")]
        self.assertEqual(hits, [])

    def test_description_covers_single_tasks(self) -> None:
        description = frontmatter().get("description") or ""
        for word in ("摘要", "篇幅", "润色", "立项依据", "研究基础"):
            self.assertIn(word, description)

    def test_task_types_and_chapter_loop(self) -> None:
        for heading in ("### 任务类型", "**只改一章**", "**只写摘要**", "**篇幅对齐**"):
            self.assertIn(heading, TEXT)
        for command in ("case.py brief", "chapter_check.py", "length_check.py", "output/before/"):
            self.assertIn(command, TEXT)
        self.assertNotIn("to-info-form", TEXT)
        self.assertNotIn("check_project_outputs.py", TEXT)


class AskUserDocsTest(unittest.TestCase):
    def test_skill_asks_instead_of_deciding(self) -> None:
        self.assertIn("### 提问", TEXT)
        self.assertIn("AskUserQuestion", TEXT)
        self.assertIn("（未能提问）", TEXT)
        self.assertIn("第 1、2 类问题照样问", TEXT)
        self.assertNotIn("全流程只有一个确认点", TEXT)
        self.assertNotIn("整个流程只有第 5 步向用户提问", TEXT)

    def test_guides_no_longer_forbid_questions(self) -> None:
        for rel in ("references/abstract.md", "references/confirm_prompt.md"):
            text = (SKILL / rel).read_text(encoding="utf-8")
            self.assertNotIn("不向申请人提问", text, rel)
            self.assertNotIn("全流程只在这里停一次", text, rel)

    def test_stage_log_uses_real_time(self) -> None:
        self.assertIn("date '+%F %H:%M'", TEXT)


class RoundSevenDocsTest(unittest.TestCase):
    def test_length_keeps_page_cap_first(self) -> None:
        guide = (SKILL / "references" / "length.md").read_text(encoding="utf-8")
        self.assertIn("页数优先于字数下限", guide)
        self.assertIn("页数优先于字数下限", TEXT)
        self.assertIn("pages.hard_max", TEXT)

    def test_unasked_questions_have_a_home_without_case(self) -> None:
        self.assertIn("T/nsfc-proposal/output/assumptions.md", TEXT)

    def test_literature_helpers_replace_hand_written_code(self) -> None:
        for command in ("literature.py digest", "literature.py select", "literature.py evidence"):
            self.assertIn(command, TEXT)
        self.assertIn("evidence_by_claim.md", TEXT)
        guide = (SKILL / "references" / "scientific_case_guide.md").read_text(encoding="utf-8")
        self.assertIn("power.py", guide)

    def test_detail_moved_out_of_skill(self) -> None:
        for rel in ("references/literature.md", "references/consistency_fixes.md"):
            self.assertIn(f"`{rel}`", TEXT)
        self.assertNotIn("`no_citation_ledger`（没有引用台账）", TEXT)
        self.assertLess(len(TEXT), 30000)


class RoundSevenFixDocsTest(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (SKILL / rel).read_text(encoding="utf-8")

    def test_three_asking_situations(self) -> None:
        for phrase in ("情形一，有 AskUserQuestion 工具", "情形二，没有 AskUserQuestion，但对话中有人",
                       "不确定有没有人回答时，按情形二", "情形三，没有人会回答", "下文「不能提问」都指情形三"):
            self.assertIn(phrase, TEXT)
        self.assertNotIn("「全自动」「无人值守」时，确认点不停", TEXT)
        self.assertIn("或属于「提问」情形三时，确认点不停", TEXT)
        confirm = self.read("references/confirm_prompt.md")
        self.assertIn("情形三", confirm)
        self.assertIn("第 2 条问", confirm)
        self.assertNotIn("- 无人值守（", confirm)
        readme = self.read("README.md")
        self.assertNotIn("全程不被打断", readme)
        self.assertIn("会改变内容的决定仍会问你", readme)
        self.assertIn("「无人值守」", readme)

    def test_batches_and_mechanical_fixes(self) -> None:
        self.assertIn("一次只问一个问题", TEXT)  # 0.5.1 起取代「每次最多 4 个」
        self.assertIn("按检查脚本结果做的机械修改", TEXT)
        self.assertIn("要在内容之间取舍的修改", TEXT)

    def test_single_chapter_reads_moved_rules(self) -> None:
        for heading in ("**只改一章**", "**篇幅对齐**"):
            block = TEXT.split(heading, 1)[1].split("\n**", 1)[0]
            self.assertIn("需要新文献时另读 `references/literature.md`", block, heading)
            self.assertIn("报出问题时另读 `references/consistency_fixes.md`", block, heading)
            self.assertIn("`references/evidence_wording.md`", block, heading)

    def test_page_cap_without_compiling(self) -> None:
        self.assertEqual(TEXT.count("`length_standard.overall.max` 字"), 2)
        self.assertGreaterEqual(TEXT.count("「页数未核」"), 4)
        guide = self.read("references/length.md")
        self.assertIn("`python3 P/scripts/nsfc_build.py`", guide)
        self.assertNotIn("nsfc_build.py build --project-dir", guide)
        self.assertIn("`length_standard.overall.max`", guide)
        self.assertIn("页数未核", guide)
        self.assertIn("扩写后再编译一次", guide)

    def test_literature_pointers_and_reselect(self) -> None:
        self.assertNotIn("按第 3 步第 6 项处理", TEXT)
        self.assertIn("`references/literature.md` 的「补摘要」", TEXT)
        guide = self.read("references/literature.md")
        self.assertIn("按 SKILL.md 第 3 步第 4、5 项检索并建池", guide)
        self.assertIn("要列出全部论断", guide)

    def test_abstract_overlimit_recorded_and_type_corrected(self) -> None:
        abstract = self.read("references/abstract.md")
        line = [ln for ln in abstract.splitlines() if ln.startswith("3 轮后仍超限")][0]
        self.assertIn("（未能提问）", line)
        self.assertIn("`project.type`", TEXT)

    def test_power_designs_listed(self) -> None:
        guide = self.read("references/scientific_case_guide.md")
        for text in ("`props-mde --n N`", "`--lower`", "`means-mde --n1 N1 --n2 N2 --cluster-size M --icc ICC`",
                     "层级回归的 f² 检验力 `power.py` 不算"):
            self.assertIn(text, guide)


class NsfcSkillsHaveNoOpenAlexTest(unittest.TestCase):
    def test_no_nsfc_skill_mentions_openalex(self) -> None:
        suffixes = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".tex", ".sh"}
        hits = [str(p.relative_to(ROOT)) for d in sorted(SKILLS.glob("nsfc-*")) for p in d.rglob("*")
                if p.is_file() and p.suffix in suffixes and p.name != "CHANGELOG.md" and "__pycache__" not in p.parts
                and "openalex" in p.read_text(encoding="utf-8", errors="ignore").lower()]
        self.assertEqual(hits, [])



class FreshFourDocsTest(unittest.TestCase):
    def test_no_compression_before_foundation_is_written(self) -> None:
        self.assertNotIn("或先压缩已写的章节", TEXT)
        self.assertIn("这时不压缩已写的章节", TEXT)
        self.assertIn("到第 8 步第 3 项再定", TEXT)
        step8 = TEXT.split("**8. 收尾**", 1)[1].split("\n**", 1)[0]
        item3 = step8.split("\n3. ", 1)[1].split("\n4. ", 1)[0]
        self.assertIn("检查篇幅", item3)
        self.assertIn("超过 `length_standard.pages.hard_max` 页时", item3)
        self.assertIn("「偏长时压缩」", item3)
        self.assertIn("删去的段落、论断与引用记入 `assumptions.md` 的「## AI 拟定项」", item3)

    def test_must_include_values_are_spelled_out(self) -> None:
        step4 = TEXT.split("**4. 章节分配**", 1)[1].split("\n**", 1)[0]
        self.assertIn("`must_include` 只填两类", step4)
        for field in ("hypothesis", "entry_point", "feasibility", "risks"):
            self.assertIn(f"`{field}`", step4)
        self.assertIn("不填论断编号 `C<n>`", step4)



class ChineseFallbackDocsTest(unittest.TestCase):
    def test_chinese_queries_and_publisher_page_rule(self) -> None:
        self.assertIn("另写几条中文检索式", TEXT)
        self.assertIn("来源记为 `publisher_page`", TEXT)
        self.assertIn("CrossRef 没有记录的中文文献，取自出版方文章页的引文标签", TEXT)
        guide = (SKILL / "references" / "literature.md").read_text(encoding="utf-8")
        for phrase in ("`citation_*` 引文标签", "期刊名必须有", "doi.org 确认已注册", "`bib_refresh` 不刷新这类条目"):
            self.assertIn(phrase, guide)
        config = yaml.safe_load((SKILL / "config.yaml").read_text(encoding="utf-8"))
        self.assertIs(config["literature"]["cn_publisher_fallback"], True)



class RoundEightDocsTest(unittest.TestCase):
    """2026-10-13 平台日志带来的通用改动：开场模板、提问放最后、篇幅不凑字、导出 Word。"""

    def test_opening_and_stop_rules(self) -> None:
        opening = TEXT.split("### 开场：一次问一件事", 1)[1].split("\n### ", 1)[0]
        for phrase in ("每次只问一个问题", "「这次申请哪一类项目？（影响正文提纲与研究期限）」", "研究方向用文字问，不用选项卡",
                       "「方向已明确」", "例：", "不问协作方式", "拟 2–3 个聚焦方向"):
            self.assertIn(phrase, opening)
        stop = TEXT.split("### 停下等回答", 1)[1].split("\n### ", 1)[0]
        for phrase in ("pending", "不留 in_progress", "提问是本轮最后一段文字", "不再调用工具"):
            self.assertIn(phrase, stop)
        self.assertIn("选项卡只用于在几个已知的做法之间选", TEXT)

    def test_questions_are_asked_one_per_turn(self) -> None:
        block = TEXT.split("### 提问", 1)[1].split("\n### ", 1)[0]
        for phrase in ("一次只问一个问题", "只问会卡住下一步、或会改变正文内容的事", "题干末尾用括号说明这个答案影响什么",
                       "不标「（推荐）」", "一次一个"):
            self.assertIn(phrase, block)
        self.assertIn("设计参数只在清单里列出，不逐个提问", TEXT)
        self.assertIn("可以随时给我文件路径」，不作为提问", TEXT)
        abstract = (SKILL / "references" / "abstract.md").read_text(encoding="utf-8")
        readme = (SKILL / "README.md").read_text(encoding="utf-8")
        self.assertIn("一次只问一个问题", readme)
        for text in (TEXT, abstract, readme):
            for old in ("集中问", "只写第 1 条也行", "填写模板", "每次最多 4 个", "合并成一次", "一并问"):
                self.assertNotIn(old, text)

    def test_word_export_and_length(self) -> None:
        for phrase in ("export_docx.py --project-root P", "P/申请书正文.docx", "pip install --user python-docx",
                       "下限只作参考，不是必须写满的目标", "看到字数偏少也不要为此补句子"):
            self.assertIn(phrase, TEXT)
        self.assertEqual(TEXT.count("重新导出 Word（第 8 步第 4 项）"), 3)
        config = yaml.safe_load((SKILL / "config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(config["export"]["docx_name"], "申请书正文.docx")
        for name in ("export_docx.py", "docx_writer.py", "docx_latex.py", "docx_blocks.py", "docx_bib.py"):
            self.assertTrue((SKILL / "scripts" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
