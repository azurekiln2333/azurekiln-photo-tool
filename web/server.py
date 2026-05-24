from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


WEB_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_DIR.parent
STATIC_DIR = WEB_DIR / "static"
JOB_ROOT = WEB_DIR / ".jobs"
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
JOB_TTL_SECONDS = 12 * 60 * 60

sys.path.insert(0, str(PROJECT_ROOT))

from flyme_livephoto_fix_core import LivePhotoFixTool, check_photo_type  # noqa: E402
from merge_live_photo import make_live_photo  # noqa: E402
from split_huawei_live_photo import is_huawei_live_photo, split_live_photo  # noqa: E402


@dataclass
class UploadFile:
    field_name: str
    filename: str
    content: bytes


@dataclass
class MultipartData:
    fields: dict[str, str]
    files: list[UploadFile]


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _safe_filename(name: str) -> str:
    name = unquote(name).replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[\x00-\x1f<>:\"|?*]+", "_", name)
    name = name.strip(". ")
    return name or f"upload-{uuid.uuid4().hex}"


def _unique_path(directory: Path, filename: str) -> Path:
    path = directory / _safe_filename(filename)
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 10_000):
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Too many duplicate files named {filename}")


def _parse_content_disposition(value: str) -> tuple[str, dict[str, str]]:
    parts = [part.strip() for part in value.split(";")]
    kind = parts[0].lower() if parts else ""
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, raw = part.split("=", 1)
        raw = raw.strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1].replace('\\"', '"')
        params[key.strip().lower()] = raw
    return kind, params


def _parse_multipart(body: bytes, content_type: str) -> MultipartData:
    match = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type)
    if not match:
        raise ValueError("Missing multipart boundary")

    boundary = (match.group(1) or match.group(2)).encode("utf-8")
    delimiter = b"--" + boundary
    fields: dict[str, str] = {}
    files: list[UploadFile] = []

    for raw_part in body.split(delimiter):
        part = raw_part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].rstrip(b"\r\n")
        header_blob, separator, content = part.partition(b"\r\n\r\n")
        if not separator:
            continue

        headers: dict[str, str] = {}
        for line in header_blob.decode("iso-8859-1").split("\r\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        disposition = headers.get("content-disposition", "")
        _, params = _parse_content_disposition(disposition)
        field_name = params.get("name", "")
        filename = params.get("filename")
        if filename:
            files.append(UploadFile(field_name, filename, content))
        elif field_name:
            fields[field_name] = content.decode("utf-8", errors="replace")

    return MultipartData(fields=fields, files=files)


def _write_uploads(files: list[UploadFile], upload_dir: Path) -> list[Path]:
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for upload in files:
        if not upload.filename:
            continue
        path = _unique_path(upload_dir, upload.filename)
        path.write_bytes(upload.content)
        saved.append(path)
    return saved


def _zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(source_dir.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(source_dir))


def _summarize_zip(zip_path: Path) -> dict[str, object]:
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    return {
        "file_count": len(names),
        "size": zip_path.stat().st_size,
        "preview": names[:20],
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _pair_by_stem(paths: list[Path]) -> tuple[list[tuple[Path, Path]], list[Path], list[Path]]:
    images = [p for p in paths if p.suffix.lower() in {".jpg", ".jpeg"}]
    videos = [p for p in paths if p.suffix.lower() in {".mp4", ".mov"}]
    video_by_stem = {p.stem.lower(): p for p in videos}
    pairs: list[tuple[Path, Path]] = []
    unpaired_images: list[Path] = []
    used_videos: set[Path] = set()

    for image in images:
        video = video_by_stem.get(image.stem.lower())
        if video:
            pairs.append((image, video))
            used_videos.add(video)
        else:
            unpaired_images.append(image)

    unpaired_videos = [p for p in videos if p not in used_videos]
    return pairs, unpaired_images, unpaired_videos


def _process_merge(uploaded: list[Path], output_dir: Path, fields: dict[str, str]) -> dict[str, object]:
    copy_static = fields.get("copy_static", "false") == "true"
    pairs, unpaired_images, unpaired_videos = _pair_by_stem(uploaded)
    log: list[str] = []
    success = 0
    failed = 0
    skipped = len(unpaired_videos)

    for image, video in pairs:
        output_path = _unique_path(output_dir, f"{image.stem}.jpg")
        try:
            make_live_photo(str(image), str(video), str(output_path))
            success += 1
            log.append(f"OK merge: {image.name} + {video.name} -> {output_path.name}")
        except Exception as exc:
            failed += 1
            log.append(f"FAIL merge: {image.name} + {video.name}: {exc}")

    for image in unpaired_images:
        if copy_static:
            target = _unique_path(output_dir, image.name)
            shutil.copy2(image, target)
            log.append(f"COPY static photo: {image.name}")
        else:
            skipped += 1
            log.append(f"SKIP static photo without matching video: {image.name}")

    for video in unpaired_videos:
        log.append(f"SKIP video without matching photo: {video.name}")

    return {
        "summary": {
            "mode": "merge",
            "merged": success,
            "failed": failed,
            "skipped": skipped,
            "uploaded": len(uploaded),
        },
        "log": log,
    }


def _process_split(uploaded: list[Path], output_dir: Path, fields: dict[str, str]) -> dict[str, object]:
    copy_non_live = fields.get("copy_non_live", "false") == "true"
    success = 0
    failed = 0
    skipped = 0
    log: list[str] = []

    for path in uploaded:
        if path.suffix.lower() not in {".jpg", ".jpeg"}:
            skipped += 1
            log.append(f"SKIP unsupported file: {path.name}")
            continue
        try:
            if not is_huawei_live_photo(path):
                if copy_non_live:
                    target = _unique_path(output_dir, path.name)
                    shutil.copy2(path, target)
                    log.append(f"COPY non-live photo: {path.name}")
                else:
                    skipped += 1
                    log.append(f"SKIP non-live photo: {path.name}")
                continue
            jpg_out, mp4_out, _, _ = split_live_photo(str(path), str(output_dir))
            success += 1
            log.append(f"OK split: {path.name} -> {Path(jpg_out).name} + {Path(mp4_out).name}")
        except Exception as exc:
            failed += 1
            log.append(f"FAIL split: {path.name}: {exc}")

    return {
        "summary": {
            "mode": "split",
            "split": success,
            "failed": failed,
            "skipped": skipped,
            "uploaded": len(uploaded),
        },
        "log": log,
    }


def _process_flyme(uploaded: list[Path], output_dir: Path, fields: dict[str, str]) -> dict[str, object]:
    copy_unchanged = fields.get("copy_unchanged", "true") == "true"
    success = 0
    failed = 0
    skipped = 0
    copied = 0
    log: list[str] = []
    engine: LivePhotoFixTool | None = None

    for path in uploaded:
        if path.suffix.lower() not in {".jpg", ".jpeg"}:
            skipped += 1
            log.append(f"SKIP unsupported file: {path.name}")
            continue

        is_meizu, is_live, is_fixed, _ = check_photo_type(path)
        needs_fix = is_meizu and is_live and not is_fixed
        if not needs_fix:
            if copy_unchanged:
                target = _unique_path(output_dir, path.name)
                shutil.copy2(path, target)
                copied += 1
                log.append(f"COPY unchanged photo: {path.name}")
            else:
                skipped += 1
                log.append(f"SKIP photo that does not need Flyme fix: {path.name}")
            continue

        try:
            if engine is None:
                engine = LivePhotoFixTool()
            target = _unique_path(output_dir, path.name)
            ok, message = engine.fix_photo(path, target)
            if ok:
                success += 1
                log.append(f"OK flyme fix: {path.name} -> {target.name}")
            else:
                failed += 1
                log.append(f"FAIL flyme fix: {path.name}: {message}")
        except Exception as exc:
            failed += 1
            log.append(f"FAIL flyme fix: {path.name}: {exc}")

    return {
        "summary": {
            "mode": "flyme",
            "fixed": success,
            "copied": copied,
            "failed": failed,
            "skipped": skipped,
            "uploaded": len(uploaded),
        },
        "log": log,
    }


def _cleanup_jobs() -> None:
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for path in JOB_ROOT.iterdir():
        try:
            if now - path.stat().st_mtime < JOB_TTL_SECONDS:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError:
            pass


def _process_request(multipart: MultipartData) -> dict[str, object]:
    mode = multipart.fields.get("mode", "").strip().lower()
    if mode not in {"merge", "split", "flyme"}:
        raise ValueError("Invalid mode")
    if not multipart.files:
        raise ValueError("No files uploaded")

    _cleanup_jobs()
    job_id = uuid.uuid4().hex
    job_dir = JOB_ROOT / job_id
    upload_dir = job_dir / "uploads"
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    uploaded = _write_uploads(multipart.files, upload_dir)
    if not uploaded:
        raise ValueError("No valid files uploaded")

    if mode == "merge":
        result = _process_merge(uploaded, output_dir, multipart.fields)
    elif mode == "split":
        result = _process_split(uploaded, output_dir, multipart.fields)
    else:
        result = _process_flyme(uploaded, output_dir, multipart.fields)

    zip_path = JOB_ROOT / f"{job_id}.zip"
    _zip_directory(output_dir, zip_path)
    result.update(
        {
            "ok": True,
            "download_url": f"/api/download/{job_id}.zip",
            "zip": _summarize_zip(zip_path),
        }
    )
    return result


class WebHandler(BaseHTTPRequestHandler):
    server_version = "AzureKilnPhotoWeb/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file(STATIC_DIR / "index.html")
            return
        if parsed.path.startswith("/static/"):
            relative = parsed.path.removeprefix("/static/").lstrip("/")
            self._send_file(STATIC_DIR / relative)
            return
        if parsed.path.startswith("/api/download/") and parsed.path.endswith(".zip"):
            file_name = Path(parsed.path).name
            self._send_file(JOB_ROOT / file_name, download_name=file_name)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/process":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self._send_json({"ok": False, "error": "Expected multipart/form-data"}, HTTPStatus.BAD_REQUEST)
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0 or content_length > MAX_UPLOAD_BYTES:
            self._send_json({"ok": False, "error": "Upload is empty or too large"}, HTTPStatus.BAD_REQUEST)
            return

        try:
            body = self.rfile.read(content_length)
            multipart = _parse_multipart(body, content_type)
            result = _process_request(multipart)
            self._send_json(result)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, download_name: str | None = None) -> None:
        try:
            resolved = path.resolve()
            allowed_roots = [STATIC_DIR.resolve(), JOB_ROOT.resolve()]
            if not any(_is_relative_to(resolved, root) for root in allowed_roots):
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            if not resolved.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            data = resolved.read_bytes()
            mime_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(data)))
            if download_name:
                self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Unable to read file")


def main() -> None:
    host = os.environ.get("AZUREKILN_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("AZUREKILN_WEB_PORT", "8765"))
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    with ThreadingHTTPServer((host, port), WebHandler) as server:
        print(f"AzureKiln Photo Tool Web is running at http://{host}:{port}")
        print("Press Ctrl+C to stop.")
        server.serve_forever()


if __name__ == "__main__":
    main()
