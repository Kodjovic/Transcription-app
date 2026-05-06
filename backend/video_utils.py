import os
import uuid
import subprocess

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}


class VideoProcessor:

    @staticmethod
    def is_ffmpeg_available() -> bool:
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def extract_audio(self, video_path: str, output_dir: str = None) -> str:
        if not self.is_ffmpeg_available():
            raise RuntimeError("FFmpeg is not installed or not found on PATH")

        if output_dir is None:
            output_dir = os.path.dirname(video_path)

        output_path = os.path.join(output_dir, f"{uuid.uuid4()}_audio.wav")

        try:
            import ffmpeg
            (
                ffmpeg
                .input(video_path)
                .output(
                    output_path,
                    acodec="pcm_s16le",
                    ac=1,
                    ar=16000,
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        except Exception as e:
            stderr = getattr(e, "stderr", b"")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Audio extraction failed: {stderr or str(e)}")

        return output_path

    def get_video_metadata(self, video_path: str) -> dict:
        try:
            import ffmpeg
            probe = ffmpeg.probe(video_path)
            video_streams = [s for s in probe["streams"] if s.get("codec_type") == "video"]
            audio_streams = [s for s in probe["streams"] if s.get("codec_type") == "audio"]

            duration = float(probe.get("format", {}).get("duration", 0))
            result = {"duration": duration, "video_streams": [], "audio_streams": []}

            for vs in video_streams:
                result["video_streams"].append({
                    "codec": vs.get("codec_name"),
                    "width": vs.get("width"),
                    "height": vs.get("height"),
                })
            for a in audio_streams:
                result["audio_streams"].append({
                    "codec": a.get("codec_name"),
                    "sample_rate": a.get("sample_rate"),
                    "channels": a.get("channels"),
                })
            return result
        except Exception as e:
            return {"error": str(e)}
