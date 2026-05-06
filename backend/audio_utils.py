import os
import uuid
from typing import List

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}


class AudioProcessor:

    def get_file_size_mb(self, path: str) -> float:
        return os.path.getsize(path) / (1024 * 1024)

    def get_audio_duration(self, path: str) -> float:
        import librosa
        return librosa.get_duration(path=path)

    def convert_to_wav(self, input_path: str, output_path: str) -> str:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(output_path, format="wav")
        return output_path

    def normalize_audio(self, audio_path: str, output_path: str) -> str:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_path)
        normalized = audio.normalize()
        normalized.export(output_path, format="wav")
        return output_path

    def split_audio(
        self,
        audio_path: str,
        max_chunk_mb: float = 24.0,
        output_dir: str = None,
    ) -> List[str]:
        from pydub import AudioSegment
        from pydub.silence import detect_silence

        if output_dir is None:
            output_dir = os.path.dirname(audio_path)

        file_size_mb = self.get_file_size_mb(audio_path)
        if file_size_mb <= max_chunk_mb * 1.02:
            return [audio_path]

        # Convert to WAV first for reliable splitting
        ext = os.path.splitext(audio_path)[1].lower()
        if ext != ".wav":
            wav_path = os.path.join(output_dir, f"{uuid.uuid4()}_converted.wav")
            audio_path = self.convert_to_wav(audio_path, wav_path)

        audio = AudioSegment.from_wav(audio_path)
        audio = audio.set_frame_rate(16000).set_channels(1)

        total_ms = len(audio)
        file_size_bytes = os.path.getsize(audio_path)

        # Calculate safe chunk duration
        bytes_per_ms = file_size_bytes / total_ms if total_ms > 0 else 1
        max_chunk_bytes = max_chunk_mb * 1024 * 1024
        chunk_duration_ms = int((max_chunk_bytes / bytes_per_ms) * 0.95)
        chunk_duration_ms = max(chunk_duration_ms, 10_000)  # minimum 10s per chunk

        # Detect silences for smart split points
        try:
            silences = detect_silence(audio, min_silence_len=500, silence_thresh=-40)
        except Exception:
            silences = []

        def find_nearest_silence(target_ms: int, tolerance_ms: int = 10_000) -> int:
            candidates = [s for s in silences if abs(s[0] - target_ms) < tolerance_ms]
            if candidates:
                return min(candidates, key=lambda s: abs(s[0] - target_ms))[0]
            return target_ms

        chunk_paths = []
        start_ms = 0
        chunk_index = 0

        while start_ms < total_ms:
            ideal_end = start_ms + chunk_duration_ms
            if ideal_end >= total_ms:
                end_ms = total_ms
            else:
                end_ms = find_nearest_silence(ideal_end)
                if end_ms <= start_ms:
                    end_ms = ideal_end

            chunk = audio[start_ms:end_ms]
            chunk_path = os.path.join(output_dir, f"{uuid.uuid4()}_chunk_{chunk_index}.wav")
            chunk.export(chunk_path, format="wav")
            chunk_paths.append(chunk_path)

            start_ms = end_ms
            chunk_index += 1

        return chunk_paths
