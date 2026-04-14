#!/usr/bin/env python3
"""
Video & Media Production Tool Module

Free content creation pipeline tools using ONLY:
- ffmpeg (already required by the project for TTS)
- PIL/Pillow (standard image library)
- No external API keys needed

Tools provided:
- video_assemble: images + audio -> video with optional subtitles
- srt_generate: text segments -> SRT subtitle file with auto-timing
- cover_generate: text + style -> cover/thumbnail image (PIL, no API)
- video_trim: cut/trim video segments
- video_merge: concatenate multiple videos
- audio_mix: mix/overlay audio tracks
- content_pipeline: end-to-end script->video orchestrator

All output goes to ~/.kunming/cache/media/ by default.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from tools.registry import registry


def _get_output_dir() -> str:
    try:
        from kunming_constants import get_kunming_dir
        return str(get_kunming_dir("cache/media", "media_cache"))
    except ImportError:
        return str(Path(tempfile.gettempdir()) / "kunming_media")


OUTPUT_DIR = _get_output_dir()


def _ensure_dir(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _has_pil() -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
        return True
    except ImportError:
        return False


def _get_audio_duration(audio_path: str) -> float:
    if not _has_ffmpeg():
        return 0.0
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, timeout=30,
        )
        return float(result.stdout.strip().decode() or "0")
    except Exception:
        return 0.0


def _run_ffmpeg(args: List[str], timeout: int = 120) -> Tuple[bool, str]:
    cmd = ["ffmpeg", "-y"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        success = result.returncode == 0
        stderr = result.stderr.decode("utf-8", errors="ignore")[-500:] if result.stderr else ""
        return success, stderr
    except subprocess.TimeoutExpired:
        return False, f"ffmpeg timed out after {timeout}s"
    except FileNotFoundError:
        return False, "ffmpeg not found in PATH"


# ===========================================================================
# Tool 1: video_assemble - Create video from images + audio
# ===========================================================================

def _video_assemble_handler(args: Dict[str, Any], **kwargs) -> str:
    images = args.get("images", [])
    if isinstance(images, str):
        images = [s.strip() for s in images.split(",") if s.strip()]
    audio = args.get("audio", "")
    output_path = args.get("output_path", "")
    subtitles = args.get("subtitles", "")
    duration_per_image = args.get("duration_per_image", 3)
    fps = args.get("fps", 24)
    resolution = args.get("resolution", "1080x1920")
    transition = args.get("transition", "none")

    if not images or not audio:
        return json.dumps({"success": False, "error": "images and audio are required"})

    if not _has_ffmpeg():
        return json.dumps({"success": False, "error": "ffmpeg is required but not installed"})

    for img in images:
        if not os.path.isfile(img):
            return json.dumps({"success": False, "error": f"image file not found: {img}"})
    if not os.path.isfile(audio):
        return json.dumps({"success": False, "error": f"audio file not found: {audio}"})

    _ensure_dir(OUTPUT_DIR)
    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, f"video_{uuid.uuid4().hex[:8]}.mp4")

    audio_dur = _get_audio_duration(audio)
    total_images = len(images)
    if audio_dur > 0 and total_images > 0:
        duration_per_image = max(0.5, audio_dur / total_images)

    concat_list_path = os.path.join(OUTPUT_DIR, f"concat_{uuid.uuid4().hex[:8]}.txt")
    try:
        tmp_dir = tempfile.mkdtemp(prefix="km_vid_", dir=OUTPUT_DIR)
        scaled_paths = []
        for i, img in enumerate(images):
            out = os.path.join(tmp_dir, f"frame_{i:04d}.png")
            scale_args = ["-loop", "1", "-i", img,
                          "-vf", f"scale={resolution}:force_original_aspect_ratio=decrease,"
                                  f"pad={resolution}:(ow-iw)/2:(oh-ih)/2:black",
                          "-t", str(duration_per_image),
                          "-pix_fmt", "yuv420p", out]
            ok, err = _run_ffmpeg(scale_args)
            if not ok:
                return json.dumps({"success": False, "error": f"Failed to scale image {i}: {err}"})
            scaled_paths.append(out)

        with open(concat_list_path, "w") as f:
            for p in scaled_paths:
                safe_p = p.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe_p}'\n")

        vid_args = ["-f", "concat", "-safe", "0", "-i", concat_list_path,
                    "-i", audio, "-c:v", "libx264", "-preset", "fast",
                    "-crf", "18", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart", output_path]

        if subtitles and os.path.isfile(subtitles):
            vid_args.insert(-2, "-vf")
            vid_args.insert(-2, f"subtitles='{subtitles.replace('\\', '/').replace(':', '\\:')}'")

        ok, err = _run_ffmpeg(vid_args, timeout=300)

        if ok and os.path.isfile(output_path):
            size_mb = round(os.path.getsize(output_path) / (1024 * 1024), 2)
            return json.dumps({
                "success": True,
                "output_path": output_path,
                "duration_sec": round(duration_per_image * total_images, 1),
                "total_images": total_images,
                "resolution": resolution,
                "size_mb": size_mb,
                "has_subtitles": bool(subtitles and os.path.isfile(subtitles)),
            })
        else:
            return json.dumps({"success": False, "error": f"Video assembly failed: {err}"})
    finally:
        for d in [tmp_dir]:
            if os.path.isdir(d):
                import shutil as _sh
                _sh.rmtree(d, ignore_errors=True)
        if os.path.isfile(concat_list_path):
            os.unlink(concat_list_path)


# ===========================================================================
# Tool 2: srt_generate - Generate SRT subtitle file from text
# ===========================================================================

def _srt_generate_handler(args: Dict[str, Any], **kwargs) -> str:
    segments = args.get("segments", [])
    if isinstance(segments, str):
        try:
            segments = json.loads(segments)
        except json.JSONDecodeError:
            segments = [{"text": s.strip()} for s in segments.split("\n") if s.strip()]

    output_path = args.get("output_path", "")
    audio_path = args.get("audio_path", "")
    words_per_second = args.get("words_per_second", 3.5)
    min_duration = args.get("min_duration", 1.5)
    max_duration = args.get("max_duration", 7.0)
    encoding = args.get("encoding", "utf-8")

    if not segments:
        return json.dumps({"success": False, "error": "segments are required"})

    _ensure_dir(OUTPUT_DIR)
    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, f"subs_{uuid.uuid4().hex[:8]}.srt")

    total_audio_dur = _get_audio_duration(audio_path) if audio_path else 0

    def _fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    current_time = 0.0
    for idx, seg in enumerate(segments):
        text = seg.get("text", "") if isinstance(seg, dict) else str(seg)
        if not text.strip():
            continue

        word_count = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text)) + \
                     len(re.findall(r'[a-zA-Z]+', text))
        cn_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
        en_words = len(re.findall(r'[a-zA-Z]+', text))

        estimated_dur = (cn_chars * 0.6 + en_words * 0.25) / words_per_second
        estimated_dur = max(min_duration, min(max_duration, estimated_dur))

        if total_audio_dur > 0:
            remaining = total_audio_dur - current_time
            avg_remaining = remaining / max(1, len([s for s in segments[idx:]
                                                      if (s.get("text","") if isinstance(s, dict) else s).strip()]))
            estimated_dur = min(estimated_dur, remaining, avg_remaining * 2)

        start_t = current_time
        end_t = start_t + estimated_dur
        current_time = end_t

        lines.append(f"{idx + 1}")
        lines.append(f"{_fmt_time(start_t)} --> {_fmt_time(end_t)}")
        lines.append(text.strip())
        lines.append("")

    try:
        with open(output_path, "w", encoding=encoding) as f:
            f.write("\n".join(lines))

        return json.dumps({
            "success": True,
            "output_path": output_path,
            "subtitle_count": len([l for l in lines if l.endswith(",000 -->")] or [0]),
            "total_duration_sec": round(current_time, 1),
            "audio_matched": bool(total_audio_dur > 0),
        })
    except Exception as e:
        return json.dumps({"success": False, "error": f"Failed to write SRT file: {e}"})


# ===========================================================================
# Tool 3: cover_generate - Generate cover/thumbnail image (PIL only, no API)
# ===========================================================================

def _cover_generate_handler(args: Dict[str, Any], **kwargs) -> str:
    title = args.get("title", "")
    subtitle = args.get("subtitle", "")
    output_path = args.get("output_path", "")
    width = args.get("width", 1080)
    height = args.get("height", 1920)
    bg_color = args.get("bg_color", "#1a1a2e")
    title_color = args.get("title_color", "#FFFFFF")
    subtitle_color = args.get("subtitle_color", "#CCCCCC")
    accent_color = args.get("accent_color", "#e94560")
    font_size_title = args.get("font_size_title", 72)
    font_size_subtitle = args.get("font_size_subtitle", 36)
    style = args.get("style", "modern")

    if not title:
        return json.dumps({"success": False, "error": "title is required"})

    if not _has_pil():
        return json.dumps({"success": False, "error": "PIL/Pillow is required: pip install Pillow"})

    from PIL import Image, ImageDraw, ImageFont

    _ensure_dir(OUTPUT_DIR)
    if not output_path:
        ext = ".png"
        output_path = os.path.join(OUTPUT_DIR, f"cover_{uuid.uuid4().hex[:8]}{ext}")

    try:
        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        font_title = _load_font(font_size_title)
        font_sub = _load_font(font_size_subtitle)
        font_accent = _load_font(int(font_size_title * 0.6))

        cx = width // 2

        if style == "modern":
            bar_y = height // 3
            draw.rectangle([(60, bar_y), (width - 60, bar_y + 8)], fill=accent_color)

            bbox_title = draw.textbbox((0, 0), title, font=font_title)
            tw = bbox_title[2] - bbox_title[0]
            draw.text(((width - tw) // 2, bar_y + 40), title, fill=title_color, font=font_title)

            if subtitle:
                bbox_sub = draw.textbbox((0, 0), subtitle, font=font_sub)
                sw = bbox_sub[2] - bbox_sub[0]
                draw.text(((width - sw) // 2, bar_y + 130), subtitle, fill=subtitle_color, font=font_sub)

        elif style == "gradient":
            for y in range(height):
                ratio = y / height
                r = int(int(bg_color.lstrip("#")[0:2], 16) * (1 - ratio) + int(accent_color.lstrip("#")[0:2], 16) * ratio * 0.3)
                g = int(int(bg_color.lstrip("#")[2:4], 16) * (1 - ratio) + int(accent_color.lstrip("#")[2:4], 16) * ratio * 0.3)
                b = int(int(bg_color.lstrip("#")[4:6], 16) * (1 - ratio) + int(accent_color.lstrip("#")[4:6], 16) * ratio * 0.3)
                draw.line([(0, y), (width, y)], fill=(r, g, b))

            bbox_title = draw.textbbox((0, 0), title, font=font_title)
            tw = bbox_title[2] - bbox_title[0]
            draw.text(((width - tw) // 2, height // 2 - 50), title, fill=title_color, font=font_title)
            if subtitle:
                bbox_sub = draw.textbbox((0, 0), subtitle, font=font_sub)
                sw = bbox_sub[2] - bbox_sub[0]
                draw.text(((width - sw) // 2, height // 2 + 50), subtitle, fill=subtitle_color, font=font_sub)

        elif style == "bold":
            draw.rectangle([(40, 40), (width - 40, height - 40)], outline=accent_color, width=4)
            padding = 80
            wrapped = _wrap_text(draw, title, font_title, width - padding * 2)
            y_offset = height // 2 - (len(wrapped) * (font_size_title + 10)) // 2
            for line in wrapped:
                bbox_lt = draw.textbbox((0, 0), line, font=font_title)
                lw = bbox_lt[2] - bbox_lt[0]
                draw.text(((width - lw) // 2, y_offset), line, fill=title_color, font=font_title)
                y_offset += font_size_title + 10
            if subtitle:
                bbox_sub = draw.textbbox((0, 0), subtitle, font=font_sub)
                sw = bbox_sub[2] - bbox_sub[0]
                draw.text(((width - sw) // 2, y_offset + 20), subtitle, fill=accent_color, font=font_sub)

        else:
            bbox_title = draw.textbbox((0, 0), title, font=font_title)
            tw = bbox_title[2] - bbox_title[0]
            draw.text(((width - tw) // 2, height // 2), title, fill=title_color, font=font_title)
            if subtitle:
                bbox_sub = draw.textbbox((0, 0), subtitle, font=font_sub)
                sw = bbox_sub[2] - bbox_sub[0]
                draw.text(((width - sw) // 2, height // 2 + font_size_title + 20), subtitle, fill=subtitle_color, font=font_sub)

        img.save(output_path, quality=95)
        size_kb = round(os.path.getsize(output_path) / 1024, 1)

        return json.dumps({
            "success": True,
            "output_path": output_path,
            "width": width,
            "height": height,
            "style": style,
            "size_kb": size_kb,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": f"Cover generation failed: {e}"})


def _load_font(size: int):
    from PIL import ImageFont
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyhbd.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        None,
    ]
    for fp in font_paths:
        if fp and os.path.isfile(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            test = current + char
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
    return lines


# ===========================================================================
# Tool 4: video_trim - Cut/trim video segments
# ===========================================================================

def _video_trim_handler(args: Dict[str, Any], **kwargs) -> str:
    input_path = args.get("input_path", "")
    output_path = args.get("output_path", "")
    start_time = args.get("start_time", "00:00:00")
    end_time = args.get("end_time", "")
    duration = args.get("duration", "")

    if not input_path or not os.path.isfile(input_path):
        return json.dumps({"success": False, "error": f"input video not found: {input_path}"})

    if not _has_ffmpeg():
        return json.dumps({"success": False, "error": "ffmpeg is required but not installed"})

    _ensure_dir(OUTPUT_DIR)
    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = os.path.join(OUTPUT_DIR, f"trimmed_{uuid.uuid4().hex[:8]}{ext}")

    trim_args = ["-ss", start_time, "-i", input_path, "-c:v", "libx264", "-c:a", "aac"]
    if end_time:
        trim_args.extend(["-to", end_time])
    elif duration:
        trim_args.extend(["-t", duration])
    trim_args.extend(["-avoid_negative_ts", "1", "-movflags", "+faststart", output_path])

    ok, err = _run_ffmpeg(trim_args, timeout=300)
    if ok and os.path.isfile(output_path):
        size_mb = round(os.path.getsize(output_path) / (1024 * 1024), 2)
        out_dur = _get_audio_duration(output_path)
        return json.dumps({
            "success": True,
            "output_path": output_path,
            "start_time": start_time,
            "end_time": end_time or duration,
            "duration_sec": round(out_dur, 1),
            "size_mb": size_mb,
        })
    return json.dumps({"success": False, "error": f"Trim failed: {err}"})


# ===========================================================================
# Tool 5: video_merge - Concatenate multiple videos
# ===========================================================================

def _video_merge_handler(args: Dict[str, Any], **kwargs) -> str:
    videos = args.get("videos", [])
    if isinstance(videos, str):
        videos = [v.strip() for v in videos.split(",") if v.strip()]
    output_path = args.get("output_path", "")

    if not videos:
        return json.dumps({"success": False, "error": "videos list is required"})

    for v in videos:
        if not os.path.isfile(v):
            return json.dumps({"success": False, "error": f"video not found: {v}"})

    if not _has_ffmpeg():
        return json.dumps({"success": False, "error": "ffmpeg is required but not installed"})

    _ensure_dir(OUTPUT_DIR)
    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, f"merged_{uuid.uuid4().hex[:8]}.mp4")

    concat_list = os.path.join(OUTPUT_DIR, f"concat_m_{uuid.uuid4().hex[:8]}.txt")
    try:
        with open(concat_list, "w", encoding="utf-8") as f:
            for v in videos:
                sv = v.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{sv}'\n")

        merge_args = ["-f", "concat", "-safe", "0", "-i", concat_list,
                      "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                      "-c:a", "aac", "-b:a", "192k",
                      "-movflags", "+faststart", output_path]

        ok, err = _run_ffmpeg(merge_args, timeout=600)
        if ok and os.path.isfile(output_path):
            size_mb = round(os.path.getsize(output_path) / (1024 * 1024), 2)
            dur = _get_audio_duration(output_path)
            return json.dumps({
                "success": True,
                "output_path": output_path,
                "source_count": len(videos),
                "duration_sec": round(dur, 1),
                "size_mb": size_mb,
            })
        return json.dumps({"success": False, "error": f"Merge failed: {err}"})
    finally:
        if os.path.isfile(concat_list):
            os.unlink(concat_list)


# ===========================================================================
# Tool 6: audio_mix - Mix/overlay audio tracks
# ===========================================================================

def _audio_mix_handler(args: Dict[str, Any], **kwargs) -> str:
    primary = args.get("primary_audio", "")
    background = args.get("background_audio", "")
    output_path = args.get("output_path", "")
    bg_volume = args.get("background_volume", 0.15)
    fade_in = args.get("fade_in", 0)
    fade_out = args.get("fade_out", 0)

    if not primary or not os.path.isfile(primary):
        return json.dumps({"success": False, "error": f"primary_audio not found: {primary}"})

    if not _has_ffmpeg():
        return json.dumps({"success": False, "error": "ffmpeg is required but not installed"})

    _ensure_dir(OUTPUT_DIR)
    if not output_path:
        base, ext = os.path.splitext(primary)
        output_path = os.path.join(OUTPUT_DIR, f"mixed_{uuid.uuid4().hex[:8]}{ext or '.mp3'}")

    filter_parts = [f"[1:a]volume={bg_volume}[bg]"]
    if fade_in > 0:
        filter_parts[0] = f"[1:a]volume={bg_volume},afade=t=in:d={fade_in}[bg]"
    if fade_out > 0:
        pri_dur = _get_audio_duration(primary)
        filter_parts.append(f"[0:a]afade=t=out:d={fade_out}:st={pri_dur - fade_out if pri_dur > fade_out else 0}[vo]")
        filter_parts.append(f"[bg]afade=t=out:d={fade_out}:st={pri_dur - fade_out if pri_dur > fade_out else 0}[bo]")
        complex_filter = ";".join(filter_parts) + f";[vo][bo]amix=inputs=2:duration=first[out]"
    else:
        complex_filter = filter_parts[0] + f";[0:a][bg]amix=inputs=2:duration=first[out]"

    mix_args = ["-i", primary]
    if background and os.path.isfile(background):
        mix_args.extend(["-i", background])
    else:
        mix_args.extend(["-i", primary])
        complex_filter = "anullsrc"

    if background and os.path.isfile(background):
        mix_args.extend(["-filter_complex", complex_filter, "-map", "[out]", output_path])
    else:
        mix_args.extend(["-c:a", "libmp3lame", "-q:a", "2", output_path])

    ok, err = _run_ffmpeg(mix_args, timeout=120)
    if ok and os.path.isfile(output_path):
        size_kb = round(os.path.getsize(output_path) / 1024, 1)
        return json.dumps({
            "success": True,
            "output_path": output_path,
            "has_background": bool(background and os.path.isfile(background)),
            "bg_volume": bg_volume,
            "size_kb": size_kb,
        })
    return json.dumps({"success": False, "error": f"Audio mix failed: {err}"})


# ===========================================================================
# Tool 7: content_pipeline - End-to-end orchestrator metadata
# (The actual orchestration is done by the LLM calling the above tools in sequence)
# This tool provides structured templates and best-practice guidance
# ===========================================================================

def _content_pipeline_handler(args: Dict[str, Any], **kwargs) -> str:
    action = args.get("action", "list_templates")
    topic = args.get("topic", "")
    style = args.get("style", "engaging")
    platform = args.get("platform", "douyin")
    duration_target = args.get("duration_target", 60)

    templates = {
        "storytelling": {
            "name": "故事叙述型",
            "structure": ["钩子(0-3秒)", "冲突引入(3-10秒)", "情节展开(10-40秒)", "高潮反转(40-55秒)", "金句收尾(55-60秒)"],
            "tips": "开头必须制造悬念或冲突，中间用具体案例，结尾留思考空间",
            "best_for": ["历史解说", "人物传记", "案件分析"],
        },
        "listicle": {
            "name": "清单盘点型",
            "structure": ["数字标题钩子", "第N个要点(每个15-20秒)", "递进式节奏", "总结+CTA"],
            "tips": "用'你绝对想不到的第3个'这类话术，每条要有信息增量",
            "best_for": ["知识科普", "产品推荐", "技巧合集"],
        },
        "reaction": {
            "name": "热点评论型",
            "structure": ["热点事件描述(5秒)", "个人观点抛出(10秒)", "多角度分析(30秒)", "预测/呼吁(15秒)"],
            "tips": "观点要鲜明有态度，避免和稀泥，可以适度争议",
            "best_for": ["新闻点评", "社会现象", "娱乐八卦"],
        },
        "tutorial": {
            "name": "干货教程型",
            "structure": ["痛点共鸣(5秒)", "效果预展示(5秒)", "步骤拆解(40秒)", "避坑提醒(5秒)", "总结回顾(5秒)"],
            "tips": "每步要可视化结果，语速适中偏快，关键操作要强调",
            "best_for": ["技能教学", "软件教程", "生活妙招"],
        },
        "emotional": {
            "name": "情感共鸣型",
            "structure": ["场景代入(10秒)", "情感递进(30秒)", "共情爆发点(15秒)", "温暖收尾(5秒)"],
            "tips": "用第二人称'你'拉近距离，细节描写要具体可感",
            "best_for": ["情感故事", "人生感悟", "正能量"],
        },
    }

    platform_specs = {
        "douyin": {"aspect": "9:16", "resolution": "1080x1920", "optimal_duration": "30-60s", "max_duration": "10min", "caption_style": "短句+emoji"},
        "xiaohongshu": {"aspect": "9:16", "resolution": "1080x1920", "optimal_duration": "3-5min", "max_duration": "15min", "caption_style": "详细笔记体"},
        "bilibili": {"aspect": "16:9", "resolution": "1920x1080", "optimal_duration": "3-8min", "max_duration": "unlimited", "caption_style": "分P讲解"},
        "kuaishou": {"aspect": "9:16", "resolution": "1080x1920", "optimal_duration": "30-60s", "max_duration": "10min", "caption_style": "接地气口语"},
        "wechat_video": {"aspect": "16:9", "resolution": "1920x1080", "optimal_duration": "1-3min", "max_duration": "unlimited", "caption_style": "专业叙事"},
        "youtube_shorts": {"aspect": "9:16", "resolution": "1080x1920", "optimal_duration": "≤60s", "max_duration": "60s", "caption_style": "hook-driven"},
    }

    if action == "list_templates":
        return json.dumps({"success": True, "action": "templates", "templates": templates})
    elif action == "platform_specs":
        return json.dumps({"success": True, "action": "specs", "platforms": platform_specs})
    elif action == "generate_plan":
        if not topic:
            return json.dumps({"success": False, "error": "topic is required for generate_plan"})
        tpl = templates.get(style, templates["storytelling"])
        spec = platform_specs.get(platform, platform_specs["douyin"])
        plan = {
            "topic": topic,
            "template": tpl["name"],
            "structure": tpl["structure"],
            "platform": platform,
            "spec": spec,
            "estimated_segments": len(tpl["structure"]),
            "workflow": [
                {"step": 1, "action": "generate_script", "tool": "LLM (built-in)",
                 "detail": f"根据{tpl['name']}模板生成{spec['optimal_duration']}的文案"},
                {"step": 2, "action": "generate_voiceover", "tool": "text_to_speech",
                 "detail": "使用Edge TTS将文案转为语音（免费）"},
                {"step": 3, "action": "generate_covers", "tool": "cover_generate",
                 "detail": f"为每个段落生成{spec['aspect']}配图（PIL免费生成）"},
                {"step": 4, "action": "generate_subtitles", "tool": "srt_generate",
                 "detail": "根据文案和音频时长自动生成SRT字幕"},
                {"step": 5, "action": "assemble_video", "tool": "video_assemble",
                 "detail": "将图片+音频+字幕合成最终视频"},
                {"step": 6, "action": "mix_bgm", "tool": "audio_mix",
                 "detail": "（可选）添加背景音乐"},
            ],
        }
        return json.dumps({"success": True, "action": "plan", "plan": plan})
    else:
        return json.dumps({"success": False, "error": f"Unknown action: {action}. Use: list_templates, platform_specs, generate_plan"})


# ===========================================================================
# Registration
# ===========================================================================

def _check_ffmpeg() -> bool:
    return _has_ffmpeg()


def _check_pil() -> bool:
    return _has_pil()

registry.register(
    name="video_assemble",
    toolset="media",
    schema={
        "name": "video_assemble",
        "description": "Create a video from images + audio track using ffmpeg. Supports subtitles overlay. Free, no API keys needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "images": {"type": "array", "items": {"type": "string"},
                           "description": "List of image file paths (will be displayed sequentially)"},
                "audio": {"type": "string", "description": "Audio file path (mp3/wav/ogg) for voiceover/BGM"},
                "output_path": {"type": "string", "description": "Output MP4 path (optional, auto-generated if omitted)"},
                "subtitles": {"type": "string", "description": "SRT file path to burn into video (optional)"},
                "duration_per_image": {"type": "number", "description": "Seconds to show each image (default: 3, auto-calculated from audio if possible)"},
                "fps": {"type": "number", "description": "Frames per second (default: 24)"},
                "resolution": {"type": "string", "description": "Output resolution e.g. '1080x1920' for vertical video (default: 1080x1920)"},
                "transition": {"type": "string", "enum": ["none", "fade", "crossfade"],
                              "description": "Transition between frames (default: none)"},
            },
            "required": ["images", "audio"],
        },
    },
    handler=_video_assemble_handler,
    check_fn=_check_ffmpeg,
)

registry.register(
    name="srt_generate",
    toolset="media",
    schema={
        "name": "srt_generate",
        "description": "Generate SRT subtitle file from text segments. Auto-calculates timing based on word count and optional audio duration.",
        "parameters": {
            "type": "object",
            "properties": {
                "segments": {"type": "array",
                            "items": {"type": "object",
                                     "properties": {"text": {"type": "string"}},
                                     "required": ["text"]},
                            "description": "Text segments (each becomes one subtitle entry). Also accepts newline-separated string."},
                "output_path": {"type": "string", "description": "Output .srt file path (optional)"},
                "audio_path": {"type": "string", "description": "Optional: audio file to auto-calculate timing from its duration"},
                "words_per_second": {"type": "number",
                                      "description": "Reading speed for timing calculation (default: 3.5, lower=longer display)"},
                "min_duration": {"type": "number", "description": "Minimum seconds per subtitle entry (default: 1.5)"},
                "max_duration": {"type": "number", "description": "Maximum seconds per subtitle entry (default: 7.0)"},
            },
            "required": ["segments"],
        },
    },
    handler=_srt_generate_handler,
)

registry.register(
    name="cover_generate",
    toolset="media",
    schema={
        "name": "cover_generate",
        "description": "Generate cover/thumbnail images using PIL (free, no API). Creates styled text-on-background images perfect for social media covers.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Main title text for the cover"},
                "subtitle": {"type": "string", "description": "Secondary/subtitle text (optional)"},
                "output_path": {"type": "string", "description": "Output image path (optional)"},
                "width": {"type": "number", "description": "Image width in pixels (default: 1080)"},
                "height": {"type": "number", "description": "Image height in pixels (default: 1920 for vertical)"},
                "bg_color": {"type": "string", "description": "Background color hex (default: '#1a1a2e' dark blue)"},
                "title_color": {"type": "string", "description": "Title text color hex (default: '#FFFFFF')"},
                "subtitle_color": {"type": "string", "description": "Subtitle text color hex (default: '#CCCCCC')"},
                "accent_color": {"type": "string", "description": "Accent/decoration color hex (default: '#e94560' red)"},
                "style": {"type": "string", "enum": ["modern", "gradient", "bold", "simple"],
                         "description": "Cover design style (default: 'modern' with accent bar)"},
            },
            "required": ["title"],
        },
    },
    handler=_cover_generate_handler,
    check_fn=_check_pil,
)

registry.register(
    name="video_trim",
    toolset="media",
    schema={
        "name": "video_trim",
        "description": "Trim/cut a video segment by start time and optional end time or duration. Uses ffmpeg.",
        "parameters": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string", "description": "Source video file path"},
                "output_path": {"type": "string", "description": "Output trimmed video path (optional)"},
                "start_time": {"type": "string", "description": "Start time in HH:MM:SS or seconds format (default: 00:00:00)"},
                "end_time": {"type": "string", "description": "End time in HH:MM:SS format (optional)"},
                "duration": {"type": "string", "description": "Duration to keep (alternative to end_time)"},
            },
            "required": ["input_path"],
        },
    },
    handler=_video_trim_handler,
    check_fn=_check_ffmpeg,
)

registry.register(
    name="video_merge",
    toolset="media",
    schema={
        "name": "video_merge",
        "description": "Concatenate multiple videos into one. Uses ffmpeg demuxer for lossless joining when codecs match.",
        "parameters": {
            "type": "object",
            "properties": {
                "videos": {"type": "array", "items": {"type": "string"},
                           "description": "List of video file paths to merge in order"},
                "output_path": {"type": "string", "description": "Output merged video path (optional)"},
            },
            "required": ["videos"],
        },
    },
    handler=_video_merge_handler,
    check_fn=_check_ffmpeg,
)

registry.register(
    name="audio_mix",
    toolset="media",
    schema={
        "name": "audio_mix",
        "description": "Mix/overlay a background music track under voiceover audio. Uses ffmpeg audio filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "primary_audio": {"type": "string", "description": "Primary audio (voiceover) file path"},
                "background_audio": {"type": "string", "description": "Background music file path (optional, returns clean copy if omitted)"},
                "output_path": {"type": "string", "description": "Output mixed audio path (optional)"},
                "background_volume": {"type": "number", "description": "Background volume 0.0-1.0 (default: 0.15, doesn't drown voiceover)"},
                "fade_in": {"type": "number", "description": "Fade-in duration in seconds (default: 0, no fade)"},
                "fade_out": {"type": "number", "description": "Fade-out duration in seconds (default: 0, no fade)"},
            },
            "required": ["primary_audio"],
        },
    },
    handler=_audio_mix_handler,
    check_fn=_check_ffmpeg,
)

registry.register(
    name="content_pipeline",
    toolset="media",
    schema={
        "name": "content_pipeline",
        "description": "Content creation pipeline helper: lists proven templates, platform specs, and generates production plans for short-form video content. No external APIs needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                          "enum": ["list_templates", "platform_specs", "generate_plan"],
                          "description": "Action: list available templates, get platform specs, or generate a full production plan"},
                "topic": {"type": "string", "description": "Content topic (required for generate_plan)"},
                "style": {"type": "string",
                         "enum": ["storytelling", "listicle", "reaction", "tutorial", "emotional"],
                         "description": "Content template/style (default: engaging)"},
                "platform": {"type": "string",
                            "enum": ["douyin", "xiaohongshu", "bilibili", "kuaishou", "wechat_video", "youtube_shorts"],
                            "description": "Target platform (default: douyin)"},
                "duration_target": {"type": "number", "description": "Target video length in seconds (default: 60)"},
            },
            "required": ["action"],
        },
    },
    handler=_content_pipeline_handler,
)
