"""Build the single-file HarmonyOS PC player from the shared offline UI."""

import argparse
import base64
import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "macos"
OUTPUT = HERE / "dist" / "听力课堂-鸿蒙电脑.html"


def replace_one(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"Expected one instance of {before!r} in the shared player")
    return text.replace(before, after, 1)


def inline_hash(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def build() -> str:
    html = (SHARED / "听力课堂.html").read_text(encoding="utf-8")
    style = (SHARED / "player.css").read_text(encoding="utf-8")
    sprite = base64.b64encode((SHARED / "assets/cats-frames.png").read_bytes()).decode("ascii")
    style = replace_one(style, 'url("assets/cats-frames.png")', 'url("data:image/png;base64,' + sprite + '")')
    scripts = [
        (SHARED / "subtitles.js").read_text(encoding="utf-8"),
        (HERE / "hash-audio.js").read_text(encoding="utf-8"),
        (SHARED / "player.js").read_text(encoding="utf-8"),
    ]
    script = "\n".join(scripts)
    if "</script" in script.lower() or "</style" in style.lower():
        raise ValueError("Shared source contains an HTML raw-text ending tag")
    html = replace_one(html, '<html lang="zh-CN">', '<html lang="zh-CN" data-platform="harmonyos">')
    html = replace_one(html, "<title>听力课堂</title>", "<title>听力课堂 · 鸿蒙电脑</title>")
    html = replace_one(html, 'id="open">打开音频</button>', 'id="open">打开音频和字幕</button>')
    html = replace_one(html, 'id="folder">', 'id="folder" hidden>')
    html = replace_one(html, "拖入 MP3，开始听力课堂", "打开音频和字幕，开始精听")
    html = replace_one(
        html, "把音频拖到这里\n同名 JSON / SRT 字幕自动加载",
        "拖入音频与同名 JSON / SRT 字幕\n也可点击“打开音频和字幕”",
    )
    html = replace_one(html, "⌘C 复制", "Ctrl+C 复制")
    html = replace_one(
        html, "<script src=\"subtitles.js\" defer></script>\n  <script src=\"player.js\" defer></script>\n",
        "",
    )
    html = replace_one(html, '<link rel="stylesheet" href="player.css">', f"<style>{style}</style>")
    html = replace_one(html, "</body>", f"<script>{script}</script>\n</body>")
    html = replace_one(
        html, "script-src 'self'; style-src 'self'; img-src 'self'",
        f"script-src {inline_hash(script)}; style-src {inline_hash(style)}; img-src data:",
    )
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    output = parser.parse_args().output
    artifact = build().encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(artifact)
    print(f"{output.resolve()} ({len(artifact)} bytes)")


if __name__ == "__main__":
    main()
