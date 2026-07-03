"""ffmpeg/export helpers, moved from app.py (Phase 3 refactor, no behavior change).

- ExportError: raised when the ffmpeg export pipeline fails.
- run_export_pipeline: probe the input video, mix the voiceover into the CTA
  end card, re-encode (or stream-copy) the input to match, and concat the two
  into the final output video.
- _run_cmd: run an ffmpeg/ffprobe command, logging output, raising ExportError
  on non-zero exit.
- _run_cmd_timed: like _run_cmd but with a watchdog timeout and a background
  stderr-draining thread, used for the long-running encode/concat steps.
"""
import json
import shutil
import subprocess
import threading
from pathlib import Path

ROOT_DIR       = Path(__file__).resolve().parent.parent
ASSETS_DIR     = ROOT_DIR / "assets"
OUTPUT_DIR     = ROOT_DIR / "finished-reels"
CTA_PATH       = ASSETS_DIR / "cta-endcard.mp4"
VOICEOVER_PATH = ASSETS_DIR / "voiceover.mp3"
TEMP_CTA       = ROOT_DIR / "cta-with-voice.mp4"

FFMPEG  = shutil.which("ffmpeg")  or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"


class ExportError(Exception):
    pass


def run_export_pipeline(input_path: Path, title: str, log_lines: list,
                        status_cb=None, ffmpeg_timeout_s: int = 300) -> Path:
    if not CTA_PATH.exists():
        raise ExportError("Missing end card video. Export from Canva as cta-endcard.mp4 → assets/")
    if not VOICEOVER_PATH.exists():
        raise ExportError("Missing voiceover. Place voiceover.mp3 in assets/")

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / f"{title}.mp4"

    # Probe input: width, height, fps, codec, bitrate — use JSON so field order is irrelevant
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,codec_name,bit_rate",
         "-of", "json", str(input_path)],
        capture_output=True, text=True
    )
    log_lines.append(f"=== ffprobe input ===\n{result.stdout}\n{result.stderr}")
    if result.returncode != 0:
        raise ExportError(f"Export failed. ffmpeg error code: {result.returncode}")

    try:
        probe = json.loads(result.stdout)
        st = probe["streams"][0]
        width      = int(st["width"])
        height     = int(st["height"])
        fps        = st["r_frame_rate"]
        codec_name = st.get("codec_name", "")
        bit_rate   = st.get("bit_rate", "0")
        bitrate_bps = int(bit_rate) if (bit_rate and str(bit_rate).strip().isdigit()) else 0
    except Exception as e:
        raise ExportError(f"Export failed: could not parse ffprobe output — {e}")

    # Smart copy: skip re-encoding if input is already H.264 1080×1920 under 15 Mb/s
    can_copy_video = (
        codec_name == "h264"
        and width == 1080 and height == 1920
        and bitrate_bps < 15_000_000
    )
    log_lines.append(
        f"Input: {width}x{height} {codec_name} {bitrate_bps // 1000}kbps  "
        f"→ {'COPY (no re-encode)' if can_copy_video else 're-encode'}"
    )

    ra = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(CTA_PATH)],
        capture_output=True, text=True
    )
    cta_has_audio = bool(ra.stdout.strip())

    if cta_has_audio:
        mix_cmd = [
            FFMPEG, "-y", "-i", str(CTA_PATH), "-i", str(VOICEOVER_PATH),
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest",
            "-c:v", "copy", str(TEMP_CTA)
        ]
    else:
        mix_cmd = [
            FFMPEG, "-y", "-i", str(CTA_PATH), "-i", str(VOICEOVER_PATH),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(TEMP_CTA)
        ]
    _run_cmd(mix_cmd, log_lines)

    scaled_cta      = ROOT_DIR / "_scaled_cta.mp4"
    reencoded_input = ROOT_DIR / "_input_enc.mp4"

    try:
        _run_cmd([
            FFMPEG, "-y", "-threads", "0", "-i", str(TEMP_CTA),
            "-vf", (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}"),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", str(scaled_cta)
        ], log_lines)

        ria = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(input_path)],
            capture_output=True, text=True
        )
        input_has_audio = bool(ria.stdout.strip())

        if can_copy_video:
            # Stream-copy the video, just transcode audio if needed
            if input_has_audio:
                enc_cmd = [
                    FFMPEG, "-y", "-i", str(input_path),
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", str(reencoded_input)
                ]
            else:
                enc_cmd = [
                    FFMPEG, "-y", "-i", str(input_path),
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=44100",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(reencoded_input)
                ]
            _run_cmd(enc_cmd, log_lines)
        else:
            if input_has_audio:
                enc_cmd = [
                    FFMPEG, "-y", "-threads", "0", "-i", str(input_path),
                    "-vf", f"fps={fps}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", str(reencoded_input)
                ]
            else:
                enc_cmd = [
                    FFMPEG, "-y", "-threads", "0", "-i", str(input_path),
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=44100",
                    "-vf", f"fps={fps}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(reencoded_input)
                ]
            _run_cmd_timed(enc_cmd, log_lines, timeout_s=ffmpeg_timeout_s, status_cb=status_cb)

        _run_cmd_timed([
            FFMPEG, "-y", "-threads", "0",
            "-i", str(reencoded_input), "-i", str(scaled_cta),
            "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[outv][outa]",
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            str(output_path)
        ], log_lines, timeout_s=ffmpeg_timeout_s, status_cb=status_cb)

    finally:
        for tmp in [TEMP_CTA, scaled_cta, reencoded_input]:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception as e:
                log_lines.append(f"[cleanup warning] could not delete {tmp.name}: {e}")

    return output_path


def _run_cmd(cmd, log_lines):
    result = subprocess.run(cmd, capture_output=True, text=True)
    log_lines.append(
        f"=== {Path(cmd[0]).name} ===\n"
        f"CMD: {' '.join(str(c) for c in cmd)}\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\nEXIT: {result.returncode}\n"
    )
    if result.returncode != 0:
        raise ExportError(f"Export failed. ffmpeg error code: {result.returncode}")


def _run_cmd_timed(cmd, log_lines, timeout_s=300, status_cb=None):
    """Run a command with a hard timeout and stderr capture.

    Runs ffmpeg via Popen; a reader thread drains stderr to prevent the 64 KB
    pipe buffer filling and stalling ffmpeg. A watchdog thread kills the process
    if it exceeds timeout_s. No elapsed-timer display — reliability over UI sugar.
    """
    if status_cb:
        status_cb("⏳  Processing video...")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    print(f"[FFMPEG] PID {proc.pid} started: {Path(cmd[0]).name} {' '.join(str(c) for c in cmd[1:4])}")

    # Drain stderr in a thread so ffmpeg is never blocked on pipe writes
    stderr_chunks: list = []
    def _read_stderr():
        for chunk in iter(lambda: proc.stderr.read(4096), b""):
            stderr_chunks.append(chunk)
    reader = threading.Thread(target=_read_stderr, daemon=True)
    reader.start()

    # Watchdog: kill process if it runs too long
    timed_out = threading.Event()
    def _watchdog():
        if not timed_out.wait(timeout_s):
            return  # process finished before timeout
        proc.kill()
    watchdog = threading.Thread(target=_watchdog, daemon=True)
    watchdog.start()

    proc.wait()
    print(f"[FFMPEG] PID {proc.pid} finished with returncode {proc.returncode}")
    timed_out.set()       # signal watchdog to exit cleanly
    reader.join(timeout=5)
    watchdog.join(timeout=2)

    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
    log_lines.append(
        f"=== {Path(cmd[0]).name} ===\n"
        f"CMD: {' '.join(str(c) for c in cmd)}\n"
        f"STDERR:\n{stderr}\nEXIT: {proc.returncode}\n"
    )
    if proc.returncode == -9 or proc.returncode == 1 and not stderr.strip():
        raise ExportError(
            "Export failed: video processing took too long. "
            "Try a smaller or already-compressed video file."
        )
    if proc.returncode != 0:
        raise ExportError(f"Export failed. ffmpeg error code: {proc.returncode}")
