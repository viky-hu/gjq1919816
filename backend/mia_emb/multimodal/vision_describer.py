# -*- coding: utf-8 -*-
"""Vision Describer — 用云端视觉语言模型（VLM）把图片转成可入库的文字描述。

为什么不用 OCR
--------------
原先图片走 pytesseract。问题有三：

1. **tesseract 二进制常常没装**。`pytesseract` 只是 Python 包装，真正干活的是
   系统里的 tesseract 可执行文件。原实现只检查 `import pytesseract` 是否成功，
   二进制缺失时会误判为"OCR 可用"，然后在调用时抛异常、被 except 吞掉，
   最终产出「（未检测到文本内容）」——**图里的文字全部丢失，且完全静默**。
2. **中文识别质量差**。无中文语言包（`chi_sim`）时中文基本识别不出来。
3. **只能出文字**。表格、流程图、示意图、照片场景全都读不懂。

改用 VLM 后，一次调用就能同时给出：图中文字、图表含义、版面结构、场景描述，
比 OCR 更适合"把图片变成能检索的知识"。

配置（环境变量）
----------------
    DASHSCOPE_API_KEY / EMBEDDING_API_KEY   必填，DashScope（阿里云百炼）key
    VL_MODEL        默认 qwen-vl-max        视觉模型名
    VL_BASE_URL     默认 DashScope 兼容端点
    VL_ENABLED      设为 "0"/"false" 可整体关闭，退回纯 OCR

失败行为：任何异常都返回空字符串，由调用方降级处理，**不抛出**。
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("multimodal.vision")

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# 实测（本项目 key）：qwen3-vl-plus 可用；qwen-vl-max / qwen-vl-plus 返回 404 Model not exist，
# qwen-vl-max-latest / qwen2.5-vl-72b-instruct 返回 403 Access denied。
# 因此默认用 qwen3-vl-plus，并在 model_not_found 时按下面顺序自动降级重试。
DEFAULT_MODEL = "qwen3-vl-plus"
FALLBACK_MODELS = (
    "qwen3-vl-plus",
    "qwen-vl-max-latest",
    "qwen2.5-vl-72b-instruct",
    "qwen-vl-plus",
)
# 连续失败达到该次数后，本篇文档剩余图片不再调用 VLM（避免几十次 404 拖垮整次上传）
MAX_CONSECUTIVE_FAILURES = 3

# 送给 VLM 前先把图缩到长边不超过该值，控制 base64 体积与费用
MAX_UPLOAD_SIDE = 1280

DEFAULT_PROMPT = (
    "请把这张图片转换成便于检索的完整文字描述，用于构建法律领域知识库。要求：\n"
    "1. 逐字转录图中**所有可见文字**，保持原有条文编号与层次（如「第一千零四十二条」）；\n"
    "2. 若含有表格，用 Markdown 表格还原；\n"
    "3. 若含有流程图/结构图，说明各元素的层级与指向关系；\n"
    "4. 若是照片或场景图，客观描述主体、场景与可辨识的关键信息；\n"
    "5. 只输出描述本身，不要加「这张图片展示了」之类的开场白，不要臆造图中没有的内容。"
)


def _next_model(current: str) -> str | None:
    """在候选模型列表里取下一个可用候选（用于 model_not_found 时自动降级）。"""
    try:
        idx = FALLBACK_MODELS.index(current)
    except ValueError:
        idx = -1
    for cand in FALLBACK_MODELS[idx + 1:]:
        if cand != current:
            return cand
    return None


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


class VisionDescriber:
    """把图片（或视频关键帧）转成文字描述。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 90,
        max_side: int = MAX_UPLOAD_SIDE,
        enabled: bool | None = None,
    ):
        self.api_key = (
            api_key
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("EMBEDDING_API_KEY")
            or os.getenv("VL_API_KEY")
            or ""
        ).strip()
        self.base_url = (base_url or os.getenv("VL_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.getenv("VL_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        self.max_side = max_side
        self.enabled = _env_flag("VL_ENABLED", True) if enabled is None else enabled

        # 统计，便于日志里看清实际调用量（视频会逐帧调用，费用敏感）
        self.call_count = 0
        self.fail_count = 0

    # ── 可用性 ──────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return bool(self.enabled and self.api_key)

    def describe_bytes(
        self,
        image_bytes: bytes,
        source_name: str = "image",
        prompt: str | None = None,
    ) -> str:
        """描述一张图片。失败返回空字符串。"""
        if not self.available:
            return ""
        prepared = self._prepare(image_bytes)
        if prepared is None:
            return ""
        payload_b64 = base64.b64encode(prepared).decode("ascii")
        return self._call(payload_b64, prompt or DEFAULT_PROMPT, source_name)

    # ── 内部实现 ────────────────────────────────────────────────

    def _prepare(self, image_bytes: bytes) -> bytes | None:
        """统一转成 PNG 并限制长边，控制请求体积。"""
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            img.load()
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > self.max_side:
                ratio = self.max_side / max(w, h)
                img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))),
                                 Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
        except Exception as e:
            logger.warning("VLM 图片预处理失败：%s: %s", type(e).__name__, e)
            return None

    def _call(self, payload_b64: str, prompt: str, source_name: str) -> str:
        if not self.enabled:
            return ""
        url = self.base_url + "/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": "data:image/png;base64," + payload_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
            "max_tokens": 1500,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
        })

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            text = (data.get("choices", [{}])[0]
                        .get("message", {}).get("content", "") or "").strip()
            self.call_count += 1
            self._consecutive_failures = 0
            if text:
                logger.info("VLM 描述成功：%s（%d 字）", source_name, len(text))
            else:
                logger.warning("VLM 返回空描述：%s", source_name)
            return text
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            self.fail_count += 1
            self._consecutive_failures = getattr(self, "_consecutive_failures", 0) + 1
            # 模型不存在/无权限：自动换下一个候选模型再试一次
            if e.code in (403, 404) and "Model not exist" in detail or e.code == 403:
                nxt = _next_model(self.model)
                if nxt:
                    logger.warning("VLM 模型 %s 不可用（HTTP %s），改用 %s 重试", self.model, e.code, nxt)
                    self.model = nxt
                    return self._call(payload_b64, prompt, source_name)
            # 连续失败过多：本篇文档剩余图片直接跳过 VLM，交给 OCR/元信息降级
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                self.enabled = False
                logger.warning(
                    "VLM 连续失败 %d 次，本次文档剩余图片不再调用视觉模型（降级为 OCR/元信息）",
                    self._consecutive_failures)
            logger.warning("VLM 调用失败（HTTP %s）：%s -> %s", e.code, source_name, detail)
            return ""
        except Exception as e:
            self.fail_count += 1
            logger.warning("VLM 调用异常：%s -> %s: %s", source_name, type(e).__name__, e)
            return ""
