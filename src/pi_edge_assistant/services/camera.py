from __future__ import annotations

import asyncio
import uuid
from pathlib import Path


class CameraError(RuntimeError):
    pass


class CameraService:
    def __init__(self, runtime_dir: Path, width: int, height: int) -> None:
        self.runtime_dir = runtime_dir
        self.width = width
        self.height = height

    async def capture(self) -> Path:
        path = self.runtime_dir / f"capture-{uuid.uuid4().hex}.jpg"
        try:
            await asyncio.to_thread(self._capture_picamera2, path)
        except (ImportError, ModuleNotFoundError):
            await self._capture_rpicam(path)
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise CameraError(f"camera capture failed: {exc}") from exc
        if not path.exists() or path.stat().st_size == 0:
            raise CameraError("camera produced an empty image")
        await asyncio.to_thread(self._resize, path)
        return path

    def _capture_picamera2(self, path: Path) -> None:
        from picamera2 import Picamera2

        camera = Picamera2()
        try:
            config = camera.create_still_configuration(main={"size": (self.width, self.height)})
            camera.configure(config)
            camera.start()
            camera.capture_file(str(path))
        finally:
            camera.stop()
            camera.close()

    async def _capture_rpicam(self, path: Path) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                "rpicam-still",
                "--nopreview",
                "--immediate",
                "--width",
                str(self.width),
                "--height",
                str(self.height),
                "-o",
                str(path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise CameraError("neither Picamera2 nor rpicam-still is available") from exc
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise CameraError(stderr.decode(errors="replace").strip() or "rpicam-still failed")

    def _resize(self, path: Path) -> None:
        try:
            from PIL import Image
        except ImportError:
            return
        with Image.open(path) as image:
            image.thumbnail((self.width, self.height))
            image.convert("RGB").save(path, "JPEG", quality=85, optimize=True)
