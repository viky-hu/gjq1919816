# -*- coding: utf-8 -*-
"""Video Processor — 用关键帧 + VLM 把视频转成可入库的文字描述。

为什么这么做
------------
后端原先**完全不支持视频**（`ALLOWED_EXTENSIONS` 里没有任何视频扩展名）。
本模块用 OpenCV 抽关键帧，逐帧交给 `VisionDescriber`（Qwen-VL）描述，
再把各帧描述按时间顺序拼成一段文本，交给既有的文本入库管线。

因此**不需要 ffmpeg**：OpenCV 自带解码器，`cv2.VideoCapture` 即可读帧。

帧数上限很重要
--------------
视频是逐帧调用 VLM 的，**按次计费**。默认策略：

    * 每秒抽 `fps_sample` 帧（默认 1 帧/秒）
    * 总帧数不超过 `max_frames`（默认 30 帧）

即一个 10 分钟的视频最多也只花 30 次调用。超出时**自动降采样**
（拉大抽帧间隔），而不是截断后面的内容——保证整段时间轴都有覆盖。

失败行为：任何异常都返回带说明的结果，由调用方决定是否入库，不抛出。
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

try:  # 包内正常导入
    from .vision_describer import VisionDescriber
except ImportError:  # 允许脚本方式单独测试/复用
    from vision_describer import VisionDescriber  # type: ignore

logger = logging.getLogger("multimodal.video")

VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".flv", ".wmv"}


@dataclass
class VideoFrameNote:
    """单帧的描述结果。"""
    index: int
    timestamp_sec: float
    description: str


@dataclass
class VideoProcessResult:
    source_path: str
    duration_sec: float = 0.0
    fps: float = 0.0
    total_frames: int = 0
    sampled_frames: int = 0
    frames: list[VideoFrameNote] = field(default_factory=list)
    description: str = ""
    error: str = ""


def _format_timestamp(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h:
        return "{0:d}:{1:02d}:{2:02d}".format(h, m, s)
    return "{0:02d}:{1:02d}".format(m, s)


class VideoProcessor:
    """把视频转成文字描述（抽帧 + VLM）。"""

    def __init__(
        self,
        vision: VisionDescriber | None = None,
        fps_sample: float = 1.0,
        max_frames: int = 30,
        frame_max_side: int = 1280,
    ):
        self.vision = vision or VisionDescriber()
        self.fps_sample = max(0.01, fps_sample)
        self.max_frames = max(1, max_frames)
        self.frame_max_side = frame_max_side

    # ── 主入口 ──────────────────────────────────────────────────

    def process_file(self, video_path: str) -> VideoProcessResult:
        path = Path(video_path)
        result = VideoProcessResult(source_path=str(path))

        if not path.exists():
            result.error = "文件不存在"
            return result

        try:
            import cv2
        except ImportError as e:
            result.error = "缺少 opencv-python（cv2）：{0}".format(e)
            logger.error(result.error)
            return result

        cap = None
        try:
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                result.error = ("无法解码该视频（编码格式可能不被 OpenCV 支持，"
                                "建议转成 H.264 MP4）")
                logger.warning("%s：%s", path.name, result.error)
                return result

            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if fps <= 0 or total <= 0:
                result.error = "读不到有效的帧率/帧数"
                return result

            duration = total / fps
            result.fps = fps
            result.total_frames = total
            result.duration_sec = duration

            timestamps = self._plan_timestamps(duration, fps, total)
            logger.info("视频 %s：%.1fs / %d 帧 / %.1ffps，计划抽 %d 帧",
                        path.name, duration, total, fps, len(timestamps))

            notes: list[VideoFrameNote] = []
            for idx, ts in enumerate(timestamps):
                frame_bytes = self._read_frame_bytes(cap, ts, fps)
                if frame_bytes is None:
                    continue
                desc = self.vision.describe_bytes(
                    frame_bytes,
                    source_name="{0}@{1}".format(path.name, _format_timestamp(ts)),
                )
                if desc:
                    notes.append(VideoFrameNote(index=idx, timestamp_sec=ts,
                                                description=desc))

            result.frames = notes
            result.sampled_frames = len(notes)

            if not notes:
                result.error = ("所有抽帧都没有得到描述（可能是 VLM 不可用或额度不足）。"
                                "请检查 DASHSCOPE_API_KEY 与 VL_ENABLED。")
                return result

            result.description = self._compose(path.name, duration, fps,
                                               len(notes), notes)
            return result

        except Exception as e:
            result.error = "{0}: {1}".format(type(e).__name__, e)
            logger.exception("视频处理异常：%s", path.name)
            return result
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    # ── 抽帧计划 ────────────────────────────────────────────────

    def _plan_timestamps(self, duration: float, fps: float,
                         total_frames: int) -> list[float]:
        """决定抽哪些时间点。

        优先按 fps_sample 抽；若总帧数超过 max_frames，则**整体拉大间隔**
        （而不是只取前 max_frames 帧），保证时间轴两端都有覆盖。
        """
        if duration <= 0:
            return []
        wanted = max(1, int(duration * self.fps_sample) + 1)
        if wanted <= self.max_frames:
            step = 1.0 / self.fps_sample
        else:
            step = duration / self.max_frames
        stamps, t = [], 0.0
        while t < duration and len(stamps) < self.max_frames:
            stamps.append(t)
            t += step
        return stamps

    def _read_frame_bytes(self, cap, ts: float, fps: float) -> bytes | None:
        """按时间点定位并编码单帧为 PNG 字节。"""
        try:
            import cv2
            frame_no = int(ts * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ok, frame = cap.read()
            if not ok or frame is None:
                return None
            h, w = frame.shape[:2]
            if max(w, h) > self.frame_max_side:
                ratio = self.frame_max_side / max(w, h)
                frame = cv2.resize(frame, (max(1, int(w * ratio)),
                                           max(1, int(h * ratio))),
                                   interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".png", frame)
            if not ok:
                return None
            return buf.tobytes()
        except Exception as e:
            logger.warning("读帧失败 @%.1fs：%s", ts, e)
            return None

    # ── 组装描述文本 ────────────────────────────────────────────

    @staticmethod
    def _compose(name: str, duration: float, fps: float,
                 sampled: int, notes: list[VideoFrameNote]) -> str:
        head = (
            "视频文件：{0}\n"
            "时长：{1}（{2:.1f} 秒），帧率：{3:.2f} fps，"
            "已按时间顺序抽取 {4} 个关键帧并逐帧描述。"
        ).format(name, _format_timestamp(duration), duration, fps, sampled)
        body = [
            "[{0}] {1}".format(_format_timestamp(n.timestamp_sec), n.description)
            for n in notes
        ]
        return head + "\n\n" + "\n\n".join(body)
