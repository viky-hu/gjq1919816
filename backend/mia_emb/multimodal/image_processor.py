# -*- coding: utf-8 -*-
"""
Image Processor — 把图片转成可入库的文字描述。

处理顺序（前面成功就用前面的，逐级降级）
----------------------------------------
1. **VLM 描述**（首选）：调 `VisionDescriber`（Qwen-VL），一次调用同时拿到
   图中文字、表格结构、图表含义、场景描述。中文准确率远高于 OCR。
2. **OCR 兜底**：VLM 不可用时（没配 key / 关闭 / 调用失败）退回 pytesseract。
3. **元信息兜底**：两者都不可用时，只产出文件名 + 分辨率 + 格式，
   并在描述里**明确标注**"未能提取文字"，不再静默假装成功。

为什么修了 OCR 探测
-------------------
原实现只检查 `import pytesseract` 是否成功就认定 OCR 可用。但 `pytesseract`
只是 Python 包装，真正干活的是系统里的 **tesseract 可执行文件**。二进制缺失时
`_ocr_available` 被误判为 True，调用时抛 `TesseractNotFoundError`、被 except 吞掉，
最终产出「（未检测到文本内容）」——**图里的文字全部丢失，且完全静默**。
现在改为真正探测二进制版本，并顺带检查中文语言包 `chi_sim`。

不改动 `ImageProcessResult` 的既有字段，只新增字段，保证调用方兼容。
"""

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("multimodal.image")

try:  # 包内正常导入
    from .vision_describer import VisionDescriber
except ImportError:  # 允许脚本方式单独复用
    from vision_describer import VisionDescriber  # type: ignore


@dataclass
class ImageProcessResult:
    """Result of image processing."""
    source_path: str
    description: str
    ocr_text: str
    width: int
    height: int
    format: str
    # ── 以下为新增字段（向后兼容）──
    vision_text: str = ""          # VLM 给出的描述
    method: str = "metadata"       # vision | ocr | metadata
    has_content: bool = False      # 是否真的提取到了可用内容


class ImageProcessor:
    """Process images into text descriptions for KG insertion."""

    def __init__(
        self,
        ocr_enabled: bool = True,
        max_size: int = 1024,
        vision: Optional[VisionDescriber] = None,
        vision_enabled: bool = True,
    ):
        self.ocr_enabled = ocr_enabled
        self.max_size = max_size
        self._ocr_available = False
        self._ocr_langs: list[str] = []

        # 真正探测 OCR 能力：二进制是否存在 + 有没有中文包
        if ocr_enabled:
            self._probe_ocr()

        # VLM：优先使用
        self.vision = vision if vision is not None else VisionDescriber()
        if not vision_enabled:
            self.vision.enabled = False

    # ── 能力探测 ────────────────────────────────────────────────

    def _probe_ocr(self) -> None:
        """真正探测 tesseract 可执行文件与语言包，而不是只看能否 import。"""
        try:
            import pytesseract
        except ImportError:
            logger.warning("pytesseract 未安装，OCR 不可用。安装：pip install pytesseract")
            return
        try:
            version = pytesseract.get_tesseract_version()
        except Exception as e:
            logger.warning(
                "检测到 pytesseract，但 tesseract 可执行文件不可用（%s）。OCR 已禁用；"
                "如需要 OCR 请安装 tesseract 本体，或依赖 VLM 通道。",
                type(e).__name__)
            return
        self._ocr_available = True
        try:
            langs = list(pytesseract.get_languages(config=""))
            self._ocr_langs = langs
            if "chi_sim" not in langs:
                logger.warning(
                    "tesseract 可用（%s），但缺少中文语言包 chi_sim，中文识别效果会很差。",
                    version)
            else:
                logger.info("OCR 可用：tesseract %s，含 chi_sim 中文包", version)
        except Exception:
            logger.info("OCR 可用：tesseract %s", version)

    @property
    def ocr_available(self) -> bool:
        return self._ocr_available

    # ── 对外接口 ────────────────────────────────────────────────

    def process_file(self, image_path: str) -> ImageProcessResult:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        data = path.read_bytes()
        return self._process_bytes(data, str(path))

    def process_bytes(self, image_bytes: bytes, filename: str = "image") -> ImageProcessResult:
        return self._process_bytes(image_bytes, filename)

    # ── 内部实现 ────────────────────────────────────────────────

    def _process_bytes(self, image_bytes: bytes, source: str) -> ImageProcessResult:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        orig_w, orig_h = img.size
        orig_format = img.format or "unknown"

        prepared = self._preprocess(img)
        w, h = prepared.size

        # 第一步：VLM（首选）
        vision_text = ""
        if self.vision.available:
            vision_text = self.vision.describe_bytes(image_bytes, Path(source).name)

        # 第二步：OCR（VLM 没拿到东西时才做，省时间）
        ocr_text = ""
        if not vision_text and self._ocr_available:
            ocr_text = self._extract_ocr(prepared)

        # 第三步：组装描述
        name = Path(source).name
        if vision_text:
            method = "vision"
            description = "图像文件：{0}\n分辨率：{1}x{2}，格式：{3}\n图像内容：\n{4}".format(
                name, orig_w, orig_h, orig_format, vision_text)
        elif ocr_text:
            method = "ocr"
            if len(ocr_text) > 1500:
                ocr_text = ocr_text[:1500] + "..."
            description = "图像文件：{0}\n分辨率：{1}x{2}，格式：{3}\n图像文本内容：\n{4}".format(
                name, orig_w, orig_h, orig_format, ocr_text)
        else:
            method = "metadata"
            description = (
                "图像文件：{0}\n分辨率：{1}x{2}，格式：{3}\n"
                "（未能提取文字内容：VLM 不可用且 OCR 不可用或未识别到文字。"
                "此条目仅含元信息，检索价值有限。）"
            ).format(name, orig_w, orig_h, orig_format)

        if method == "metadata":
            logger.warning("图片 %s 只提取到元信息（无正文内容）", name)

        return ImageProcessResult(
            source_path=source,
            description=description,
            ocr_text=ocr_text,
            width=w,
            height=h,
            format=orig_format,
            vision_text=vision_text,
            method=method,
            has_content=bool(vision_text or ocr_text),
        )

    def _preprocess(self, img):
        from PIL import Image, ImageOps

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        w, h = img.size
        if max(w, h) > self.max_size:
            ratio = self.max_size / max(w, h)
            img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))),
                             Image.LANCZOS)

        img = ImageOps.exif_transpose(img) or img
        return img

    def _extract_ocr(self, img) -> str:
        """Extract text from image via pytesseract."""
        try:
            import pytesseract
            # 有中文包就用中英混排，否则退回英文，避免因缺包直接报错
            lang = "chi_sim+eng" if "chi_sim" in self._ocr_langs else "eng"
            text = pytesseract.image_to_string(img, lang=lang)
            text = text.strip()
            if len(text) > 10:
                logger.info("OCR 提取 %d 字符（lang=%s）", len(text), lang)
            return text
        except Exception as e:
            logger.warning("OCR 失败：%s", e)
            return ""
