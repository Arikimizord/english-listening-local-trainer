"""Offline single-stage CUDA worker. Invoked by the workstation job manager.

Exit 0 means the atomic stage result exists; it never means owner approval.
No GUI, downloads, global configuration, or CPU fallback.
"""
from __future__ import annotations
import argparse, contextlib, hashlib, importlib.util, json, math, os, pathlib
import socket, subprocess, sys, tempfile, traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
DLL_HANDLES_MODULE = None
sys.path.insert(0, str(ROOT / 'scripts'))


def local_file(raw: str, label: str) -> pathlib.Path:
    if '://' in raw or raw.startswith(('\\\\', '//')):
        raise ValueError(label + ' must be a local drive path, not a URL or UNC path')
    p = pathlib.Path(raw)
    if not p.is_absolute():
        raise ValueError(label + ' must be absolute')
    p = p.resolve(strict=True)
    if not p.is_file():
        raise ValueError(label + ' must be a regular file')
    return p


def no_network(*args, **kwargs):
    raise RuntimeError('Offline worker: network/download attempt rejected')


def configure_private_runtime():
    global DLL_HANDLES_MODULE
    for name in ['HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY']:
        os.environ[name] = '1'
    os.environ['HF_HOME'] = str(ROOT / 'cache/huggingface')
    os.environ['HF_HUB_CACHE'] = str(ROOT / 'cache/huggingface/hub')
    os.environ['HUGGINGFACE_HUB_CACHE'] = os.environ['HF_HUB_CACHE']
    os.environ['HF_XET_CACHE'] = str(ROOT / 'cache/huggingface/xet')
    os.environ['TORCH_HOME'] = str(ROOT / 'cache/torch')
    os.environ['NLTK_DATA'] = str(ROOT / 'cache/nltk')
    os.environ['XDG_CACHE_HOME'] = str(ROOT / 'cache/xdg')
    os.environ['MPLCONFIGDIR'] = str(ROOT / 'cache/matplotlib')
    os.environ['NUMBA_CACHE_DIR'] = str(ROOT / 'cache/numba')
    os.environ['TEMP'] = os.environ['TMP'] = str(ROOT / 'temp')
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
    os.environ['OMP_NUM_THREADS'] = os.environ['MKL_NUM_THREADS'] = '4'
    socket.create_connection = no_network
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    import urllib.request
    urllib.request.urlopen = no_network
    import requests
    requests.sessions.Session.request = no_network
    spec = importlib.util.spec_from_file_location('subtitle_private_runtime', ROOT / 'scripts/private-runtime.py')
    DLL_HANDLES_MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(DLL_HANDLES_MODULE)
    return DLL_HANDLES_MODULE.configure(ROOT)


def verify_model(kind: str):
    lock = json.loads((ROOT / 'config/models-stage3.lock.json').read_text(encoding='utf-8-sig'))
    model = next(m for m in lock['models'] if m['kind'] == kind)
    folder = (ROOT / model['directory']).resolve(strict=True)
    if not folder.is_relative_to((ROOT / 'models').resolve()):
        raise ValueError('Model path escaped private models directory')
    for entry in model['files']:
        p = (folder / entry['name']).resolve(strict=True)
        if not p.is_relative_to(folder) or not p.is_file() or p.stat().st_size != entry['size']:
            raise ValueError('Model file path/size mismatch: ' + entry['name'])
        if entry.get('sha256'):
            with p.open('rb') as f:
                digest = hashlib.file_digest(f, 'sha256').hexdigest()
            if digest != entry['sha256']:
                raise ValueError('Model SHA256 mismatch: ' + entry['name'])
        else:
            digest = hashlib.sha1(f"blob {entry['size']}\0".encode())
            with p.open('rb') as f:
                while block := f.read(4 * 1024 ** 2):
                    digest.update(block)
            if digest.hexdigest() != entry['git_blob_sha1']:
                raise ValueError('Model Git blob hash mismatch: ' + entry['name'])
    return model, folder


def duration(audio: pathlib.Path) -> float:
    ffprobe = ROOT / 'runtime/ffmpeg/ffmpeg-7.1.1-full_build-shared/bin/ffprobe.exe'
    p = subprocess.run([str(ffprobe), '-v', 'error', '-select_streams', 'a:0',
                        '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', str(audio)],
                       capture_output=True, text=True, encoding='utf-8', check=True)
    data = json.loads(p.stdout)
    if not data.get('streams'):
        raise ValueError('No audio stream')
    seconds = float(data['format']['duration'])
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('Invalid media duration')
    return seconds


def validate_segments(data, seconds):
    if not isinstance(data, dict) or not isinstance(data.get('segments'), list) or not data['segments']:
        raise ValueError('Alignment input requires a nonempty segments list')
    result, previous = [], -1.0
    for item in data['segments']:
        if not isinstance(item, dict):
            raise ValueError('Invalid segment object')
        start, end, text = item.get('start'), item.get('end'), item.get('text')
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError('Segment times must be finite numbers')
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= seconds + 0.05 and start >= previous):
            raise ValueError('Segment time bounds/order invalid')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Segment text must be nonempty')
        result.append({'start': float(start), 'end': float(end), 'text': text})
        previous = start
    return result


def atomic_json(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False,
                         default=lambda x: x.item() if hasattr(x, 'item') else str(x))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as f:
            temporary = pathlib.Path(f.name)
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['asr', 'align', 'repair'], required=True)
    parser.add_argument('--audio', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--segments')
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.flags.utf8_mode or not pathlib.Path(sys.executable).resolve().is_relative_to(ROOT):
        raise RuntimeError('Use private Python with -I -X utf8')
    audio = local_file(args.audio, 'audio')
    segment_path = local_file(args.segments, 'segments') if args.segments else None
    if args.stage in ('align', 'repair') and segment_path is None:
        raise ValueError('--segments is required for align')
    output = pathlib.Path(args.output)
    if not output.is_absolute():
        raise ValueError('output must be absolute')
    output = output.resolve()
    if not output.is_relative_to((ROOT / 'jobs').resolve()) or output in [audio, segment_path]:
        raise ValueError('Output must stay in private jobs and cannot overwrite inputs')
    configure_private_runtime()
    seconds = duration(audio)
    model, folder = verify_model('asr' if args.stage in ('asr', 'repair') else 'alignment')
    import torch
    torch.set_num_threads(4)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; CPU fallback prohibited')
    result = {'schema_version': 1, 'stage': args.stage, 'device': 'cuda', 'language': 'en',
              'duration_seconds': seconds, 'model_revision': model['revision'],
              'audio_sha256': hashlib.file_digest(audio.open('rb'), 'sha256').hexdigest(),
              'review_status': 'pending'}
    with contextlib.redirect_stdout(sys.stderr):
        if args.stage in ('asr', 'repair'):
            import faster_whisper.utils
            faster_whisper.utils.download_model = no_network
            from faster_whisper import WhisperModel
            engine = WhisperModel(str(folder), device='cuda', compute_type='float16',
                                  cpu_threads=4, num_workers=1, local_files_only=True)
            if engine.model.device != 'cuda' or engine.model.compute_type != 'float16':
                raise RuntimeError('Unexpected ASR device/compute type')
            if args.stage == 'repair':
                prior = json.loads(segment_path.read_text(encoding='utf-8-sig'))
                if prior.get('audio_sha256') != result['audio_sha256']:
                    raise ValueError('Repair ASR audio hash mismatch')
                rows = prior['segments']
            else:
                segments, info = engine.transcribe(str(audio), language='en', beam_size=5,
                    word_timestamps=True, condition_on_previous_text=False, vad_filter=False)
                rows = [{'start': s.start, 'end': s.end, 'text': s.text,
                         'words': [{'word': w.word, 'start': w.start, 'end': w.end,
                                    'probability': w.probability} for w in (s.words or [])]}
                        for s in segments]
            from boundary_repair import candidates, repair_rows
            repair_evidence = []
            if candidates(rows):
                from faster_whisper.audio import decode_audio
                samples = decode_audio(str(audio), sampling_rate=16000)
                def decode_window(start, end):
                    pieces, _ = engine.transcribe(samples[int(start*16000):int(end*16000)],
                        language='en', beam_size=5, temperature=0, word_timestamps=True,
                        condition_on_previous_text=False, vad_filter=False)
                    return [{'word': w.word} for piece in pieces for w in (piece.words or [])]
                rows, repair_evidence = repair_rows(rows, decode_window, seconds)
            result['boundary_repair'] = repair_evidence
            result.update(segments=rows, word_segments=[w for s in rows for w in s['words']],
                          text=''.join(s['text'] for s in rows), compute_type='float16')
        else:
            import nltk
            nltk.data.path = [str(ROOT / 'cache/nltk')]
            nltk.download = no_network
            nltk.data.find('tokenizers/punkt_tab/english/')
            torch.hub.download_url_to_file = no_network
            from whisperx.alignment import load_align_model, align
            from whisperx.audio import load_audio
            transcript = validate_segments(json.loads(segment_path.read_text(encoding='utf-8-sig')), seconds)
            engine, metadata = load_align_model('en', 'cuda', model_name=str(folder),
                model_dir=str(ROOT / 'cache/huggingface'), model_cache_only=True)
            engine.eval()
            if next(engine.parameters()).device.type != 'cuda' or metadata['type'] != 'huggingface':
                raise RuntimeError('Unexpected alignment backend/device')
            aligned = align(transcript, engine, metadata, load_audio(str(audio)), 'cuda',
                            interpolate_method='ignore', return_char_alignments=False)
            result.update(aligned)
            result['interpolation'] = 'ignore'
            result['segments_sha256'] = hashlib.file_digest(segment_path.open('rb'), 'sha256').hexdigest()
        torch.cuda.synchronize()
    atomic_json(output, result)
    print(json.dumps({'ok': True, 'stage': args.stage, 'output': str(output),
                      'segments': len(result['segments']), 'review_status': 'pending'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)
