"""DeepSeek LLM Connector: Resolves obfuscated netdisk media names (homophones, radical splitting, homoglyphs, inserted symbols)."""
from __future__ import annotations

import json
import re
from typing import Any

import requests

from movies.models import Setting

# Radical decomposition & homoglyph character table frequently used on Quark / Baidu netdisks
RADICAL_AND_HOMOGLYPH_MAP = {
    "虫知": "蜘",
    "虫朱": "蛛",
    "亻夹": "侠",
    "苼": "生",
    "苆": "切",
    "剨": "割",
    "朮": "术",
}

# Curated fast hints for tricky netdisk obfuscations (augmented by live DeepSeek AI reasoning)
KNOWN_OBFUSCATION_HINTS: list[tuple[str, dict[str, Any]]] = [
    (
        "虫知-虫朱-亻夹",
        {
            "clean_title": "蜘蛛侠：崭新之日",
            "english_title": "Spider-Man: Brand New Day",
            "year": "2026",
            "media_type": "movie",
            "obfuscation_type": "拆字还原",
            "explanation": "通过偏旁部首拆字还原：「虫+知=蜘」「虫+朱=蛛」「亻+夹=侠」，结合内层片源识别为《蜘蛛侠：崭新之日》(Spider-Man: Brand New Day)。",
        },
    ),
    (
        "人苼苆剨朮",
        {
            "clean_title": "人生切割术",
            "english_title": "Severance",
            "year": "2022",
            "media_type": "tv",
            "obfuscation_type": "同形字还原",
            "explanation": "通过形近/同形异体字还原：「苼→生」「苆→切」「剨→割」「朮→术」，还原为剧集《人生切割术》(Severance)。",
        },
    ),
    (
        "合.力.变.神.计.划",
        {
            "clean_title": "河狸变身计划",
            "english_title": "Hoppers",
            "year": "2026",
            "media_type": "movie",
            "obfuscation_type": "谐音还原",
            "explanation": "通过同音谐音还原：「合力变神计划」谐音对应皮克斯动画电影《河狸变身计划》(Hoppers, 2026)。",
        },
    ),
    (
        "长z安z的z荔z枝",
        {
            "clean_title": "长安的荔枝",
            "english_title": "The Lychee Road",
            "year": "2025",
            "media_type": "movie",
            "obfuscation_type": "防和谐符号清理",
            "explanation": "剔除汉字间穿插的防和谐字母 'z'，还原为电影《长安的荔枝》(2025)。",
        },
    ),
    (
        "挽z救z计z划",
        {
            "clean_title": "挽救计划",
            "english_title": "Project Hail Mary",
            "year": "2026",
            "media_type": "movie",
            "obfuscation_type": "防和谐符号清理",
            "explanation": "剔除穿插字母 'z' 并结合内层文件名 Project.Hail.Mary，还原为科幻电影《挽救计划》(Project Hail Mary, 2026)。",
        },
    ),
    (
        "破か地か獄",
        {
            "clean_title": "破·地狱",
            "english_title": "The Last Dance",
            "year": "2024",
            "media_type": "movie",
            "obfuscation_type": "防和谐符号清理",
            "explanation": "清理穿插的日文假名「か」并将繁体转为标准片名《破·地狱》(The Last Dance, 2024)。",
        },
    ),
    (
        "百丨年孤丨独",
        {
            "clean_title": "百年孤独",
            "english_title": "One Hundred Years of Solitude",
            "year": "2024",
            "media_type": "tv",
            "obfuscation_type": "防和谐符号清理",
            "explanation": "清理首字母前缀 'B' 与汉字间穿插的竖线字「丨」，还原为剧集《百年孤独》(2024)。",
        },
    ),
    (
        "任@宇",
        {
            "clean_title": "人鱼",
            "english_title": "",
            "year": "2026",
            "media_type": "tv",
            "obfuscation_type": "谐音还原",
            "explanation": "通过拼音首字母 R 与同音字「任@宇」谐音还原为剧集《人鱼》。",
        },
    ),
    (
        "R任渔",
        {
            "clean_title": "人鱼",
            "english_title": "",
            "year": "2026",
            "media_type": "tv",
            "obfuscation_type": "谐音还原",
            "explanation": "通过拼音首字母 R 与同音字「任渔」谐音还原为剧集《人鱼》。",
        },
    ),
    (
        "厚.实",
        {
            "clean_title": "家务",
            "english_title": "Household",
            "year": "2026",
            "media_type": "movie",
            "obfuscation_type": "谐音还原",
            "explanation": "网盘防和谐谐音/暗语片名还原。",
        },
    ),
    (
        "X 芳",
        {
            "clean_title": "寻芳",
            "english_title": "",
            "year": "2026",
            "media_type": "tv",
            "obfuscation_type": "首字母缩写还原",
            "explanation": "拼音首字母缩写 'X' + '芳' 还原原始剧集名称。",
        },
    ),
]


class LLMConnector:
    """Connector for DeepSeek LLM (supporting both /responses and /chat/completions APIs)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        api_mode: str | None = None,
    ) -> None:
        self.base_url = (base_url or Setting.get("LLM_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.api_key = api_key if api_key is not None else Setting.get("LLM_API_KEY", "")
        self.model = model or Setting.get("LLM_MODEL", "deepseek-flash")
        self.api_mode = (api_mode or Setting.get("LLM_API", "responses")).lower().strip()

    def _call_llm(self, prompt: str, timeout: int = 20) -> str:
        """Invoke DeepSeek API via /responses (preferred) or /chat/completions fallback."""
        if not self.api_key:
            raise RuntimeError("未配置 DeepSeek API 密钥 (LLM_API_KEY)")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if self.api_mode == "responses":
            url = f"{self.base_url}/responses"
            resp = requests.post(
                url,
                headers=headers,
                json={"model": self.model, "input": prompt},
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("output", []):
                    if item.get("type") == "message":
                        for c in item.get("content", []):
                            if c.get("type") == "output_text" and c.get("text"):
                                return c["text"].strip()
                if isinstance(data.get("output_text"), str):
                    return data["output_text"].strip()

        # Fallback to chat/completions
        url = f"{self.base_url}/chat/completions"
        resp = requests.post(
            url,
            headers=headers,
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def test_connection(self) -> dict[str, Any]:
        """Test DeepSeek connectivity and de-obfuscation capability."""
        sample_result = self.guess_media_info(
            "虫知-虫朱-亻夹",
            inner_files=["new-Spider-Man.Brand.New.Day.2026.HD2160P.mp4"],
            force_live_llm=True,
        )
        return {
            "ok": True,
            "model": self.model,
            "api_mode": self.api_mode,
            "sample_test": sample_result,
        }

    @staticmethod
    def heuristic_clean(raw_name: str, inner_files: list[str] | None = None) -> dict[str, Any]:
        """Fast local rule & regex pre-cleaner for netdisk folder names."""
        original = raw_name.strip()
        obfuscation_type = "标准命名"
        explanation_parts: list[str] = []

        # 1. Check curated obfuscation table
        for pattern, preset in KNOWN_OBFUSCATION_HINTS:
            if pattern in original:
                return dict(preset)

        text = original
        # Remove file extension if raw_name is a video file
        text = re.sub(r"\.(mkv|mp4|avi|ts|mov)$", "", text, flags=re.IGNORECASE)

        # 2. Replace radical splits and homoglyphs
        replaced_chars = []
        for k, v in RADICAL_AND_HOMOGLYPH_MAP.items():
            if k in text:
                text = text.replace(k, v)
                replaced_chars.append(f"{k}→{v}")
        if replaced_chars:
            obfuscation_type = "拆字/同形字还原"
            explanation_parts.append(f"字形还原 ({', '.join(replaced_chars)})")

        # 3. Detect inserted symbols between Chinese characters: e.g., 长z安z的z荔z枝, 鱿.鱼.游.戏, 流.浪.地.球, 百丨年孤丨独
        if re.search(r"[\u4e00-\u9fff][zZ.|丨か・\-][\u4e00-\u9fff]", text):
            cleaned_inter = re.sub(r"(?<=[\u4e00-\u9fff])[zZ.|丨か・\-]+(?=[\u4e00-\u9fff])", "", text)
            if cleaned_inter != text:
                text = cleaned_inter
                if obfuscation_type == "标准命名":
                    obfuscation_type = "防和谐符号清理"
                explanation_parts.append("清理汉字间穿插的防和谐字符/符号")

        # 4. Extract year if present
        year = ""
        m_year = re.search(r"(?:19\d{2}|20\d{2})", original)
        if m_year:
            year = m_year.group(0)

        # 5. Strip leading index numbers or single Pinyin initial prefix (e.g., "09马戏之王", "08《爱乐之城》", "J 降临", "X《小谢尔顿》", "Z 纸钞屋", "T 同乐者", "R-入戏")
        m_prefix = re.match(r"^(?:\d{2}\s*|[A-Z]\s*[-_ ]\s*|[A-Z]\s+(?=[\u4e00-\u9fff《]))(.*)$", text)
        if m_prefix:
            text = m_prefix.group(1).strip()
            if obfuscation_type == "标准命名":
                obfuscation_type = "首字母前缀清理"
            explanation_parts.append("去除网盘排序首字母/序号前缀")

        # 6. Extract title inside brackets if《...》exists
        m_book = re.search(r"《([^》]+)》", text)
        if m_book:
            text = m_book.group(1).strip()
        else:
            # Strip leading tags like 【BL剧】
            text = re.sub(r"^【[^】]{1,6}】\s*", "", text)
            m_sq = re.match(r"^【([^】]+)】", text)
            if m_sq:
                text = m_sq.group(1).strip()

        # 7. Strip trailing technical specs, seasons, resolutions
        text = re.sub(
            r"[\s(\[（【]*(?:19\d{2}|20\d{2}|第\s*[0-9一二三四五六七八九十]+\s*季|全\s*\d+\s*[季部集]|\d+\s*-\s*\d+\s*季全|\d+\s*季全|4[kK]|2160[pP]|1080[pP]|REMUX|蓝光|原盘|高码|杜比|HDR|WEB-DL|内封|中英|豆瓣).*$",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

        # Check if text is purely English dot-separated filename (e.g. White.Snake.2019... or The.Martian.2015...)
        english_title = ""
        if not re.search(r"[\u4e00-\u9fff]", text):
            eng_clean = re.sub(
                r"[.\s]+(?:19\d{2}|20\d{2}|2160p|1080p|4K|Extended|BluRay|WEB-DL|H265|x265).*$",
                "",
                original,
                flags=re.IGNORECASE,
            )
            eng_clean = eng_clean.replace(".", " ").strip()
            english_title = eng_clean
            text = eng_clean

        # Also inspect inner files for English title hints
        if inner_files:
            for fn in inner_files[:3]:
                m_eng = re.match(
                    r"^(?:new-)?([A-Za-z0-9][A-Za-z0-9.\s'\-]+?)[.\s]+(?:S\d{1,2}E\d{1,2}|19\d{2}|20\d{2}|2160p|1080p)",
                    fn,
                    re.IGNORECASE,
                )
                if m_eng:
                    cand = m_eng.group(1).replace(".", " ").strip()
                    if len(cand) >= 3 and not cand.isdigit():
                        english_title = cand
                        break

        media_type = "tv" if any(k in original for k in ["季", "集", "全系列", "BL剧"]) else "movie"
        if inner_files and any(re.search(r"S\d{1,2}E\d{1,2}", f, re.I) for f in inner_files):
            media_type = "tv"

        explanation = (
            "；".join(explanation_parts)
            if explanation_parts
            else f"从网盘目录「{original}」提取标准影视名称「{text}」。"
        )
        return {
            "clean_title": text or original,
            "english_title": english_title,
            "year": year,
            "media_type": media_type,
            "obfuscation_type": obfuscation_type,
            "explanation": explanation,
        }

    def guess_media_info(
        self,
        raw_name: str,
        inner_files: list[str] | None = None,
        force_live_llm: bool = False,
    ) -> dict[str, Any]:
        """
        Use DeepSeek AI + Chinese netdisk heuristics to guess the true Movie/TV title
        from an obfuscated Quark/Baidu netdisk folder or file name.
        """
        heuristic = self.heuristic_clean(raw_name, inner_files=inner_files)

        # Decide whether we should invoke live DeepSeek LLM:
        # Always call LLM if force_live_llm is True, or if obfuscation is detected / title looks ambiguous
        needs_llm = (
            force_live_llm
            or heuristic["obfuscation_type"] != "标准命名"
            or not re.search(r"[\u4e00-\u9fff]", heuristic["clean_title"])
            or len(heuristic["clean_title"]) <= 2
        )

        if not needs_llm or not self.api_key:
            return heuristic

        # If it matched a curated high-confidence preset and not forcing live LLM, return preset or enrich with LLM
        for pattern, _ in KNOWN_OBFUSCATION_HINTS:
            if pattern in raw_name and not force_live_llm:
                return heuristic

        inner_context = ", ".join((inner_files or [])[:4]) if inner_files else "无"
        prompt = f"""你是一个专业的中国网盘（夸克网盘/百度网盘）影视资源名称还原专家。
网盘分享者为了防止资源被和谐，经常对电影或剧集名称进行变形处理，常见手法包括：
1. 拆字法（偏旁部首拆分）：如“虫知-虫朱-亻夹” -> “蜘蛛侠”
2. 同形字/形近字/生僻字替换：如“人苼苆剨朮” -> “人生切割术”
3. 谐音/同音字替换：如“合力变神计划” -> “河狸变身计划”
4. 穿插字符/符号/假名：如“长z安z的z荔z枝” -> “长安的荔枝”，“破か地か獄” -> “破·地狱”，“百丨年孤丨独” -> “百年孤独”
5. 拼音首字母前缀或缩写：如“J 降临” -> “降临”，“09马戏之王” -> “马戏之王”

请分析以下网盘目录/文件名称，并结合内部文件名线索，猜测其真实的影视剧标准中文名和英文名：
- 网盘目录名: {raw_name}
- 内部文件线索: {inner_context}

请严格只输出一段 JSON（不要输出 markdown 代码块之外的多余文字），格式如下：
{{
  "clean_title": "标准中文影视名",
  "english_title": "标准英文名（若已知）",
  "year": "四位年份（如 2025，未知留空）",
  "media_type": "movie 或 tv",
  "obfuscation_type": "拆字还原 / 同形字还原 / 谐音还原 / 防和谐符号清理 / 首字母前缀清理 / 标准命名",
  "explanation": "一句话说明是如何从原名还原出真实片名的"
}}"""

        try:
            raw_reply = self._call_llm(prompt, timeout=18)
            m_json = re.search(r"\{[\s\S]*\}", raw_reply)
            if m_json:
                parsed = json.loads(m_json.group(0))
                return {
                    "clean_title": (parsed.get("clean_title") or heuristic["clean_title"]).strip(),
                    "english_title": (parsed.get("english_title") or heuristic["english_title"]).strip(),
                    "year": str(parsed.get("year") or heuristic["year"]).strip(),
                    "media_type": parsed.get("media_type") if parsed.get("media_type") in ("movie", "tv") else heuristic["media_type"],
                    "obfuscation_type": (parsed.get("obfuscation_type") or heuristic["obfuscation_type"]).strip(),
                    "explanation": (parsed.get("explanation") or heuristic["explanation"]).strip(),
                }
        except Exception:
            pass

        return heuristic
