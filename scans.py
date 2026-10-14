"""File splitting and code reading before model inference."""
import subprocess
import tempfile
import zipfile
import io
from pathlib import Path

from PIL import Image


def pages(file_bytes, filename):
    suffix = Path(filename).suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            names = [n for n in archive.namelist() if not n.endswith("/")]
            if len(names) > 100:
                raise ValueError("ZIP has too many files")
            for name in names:
                if Path(name).suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                info = archive.getinfo(name)
                if info.file_size > 40 * 1024 * 1024:
                    raise ValueError("ZIP member too large")
                yield from pages(archive.read(name), name)
        return
    with tempfile.TemporaryDirectory() as d:
        source = Path(d) / ("input" + suffix)
        source.write_bytes(file_bytes)
        if suffix == ".pdf":
            subprocess.run(["pdftoppm", "-r", "220", "-png", str(source), str(Path(d) / "page")],
                           check=True, capture_output=True, timeout=120)
            paths = sorted(Path(d).glob("page-*.png"))
        elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            with Image.open(source) as img:
                img.verify()
            paths = [source]
        else:
            raise ValueError("Use a PDF, PNG, JPEG, or WebP")
        for path in paths:
            with Image.open(path) as img:
                if img.width * img.height > 35_000_000:
                    raise ValueError("Scan resolution is too large")
                rgb = img.convert("RGB")
                target = Path(d) / (path.stem + "-normalized.png")
                rgb.save(target)
                proc = subprocess.run(["zbarimg", "--quiet", "--raw", str(target)],
                                      capture_output=True, text=True, timeout=20)
                codes = [x for x in proc.stdout.splitlines() if x.strip()]
                # The supplied example puts two A5 works on one A4 scan.
                if len(codes) >= 2 and rgb.height > rgb.width:
                    midpoint = rgb.height // 2
                    for part in (rgb.crop((0, 0, rgb.width, midpoint)),
                                 rgb.crop((0, midpoint, rgb.width, rgb.height))):
                        with io.BytesIO() as buf:
                            part.save(buf, format="PNG")
                            yield buf.getvalue()
                else:
                    yield target.read_bytes()


def read_code(image_path):
    proc = subprocess.run(["zbarimg", "--quiet", "--raw", str(image_path)],
                          capture_output=True, text=True, timeout=20)
    codes = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
    return codes[0] if len(codes) == 1 else None


def read_name(image_path):
    proc = subprocess.run(["tesseract", str(image_path), "stdout", "-l", "pol+eng", "--psm", "6"],
                          capture_output=True, text=True, timeout=30)
    for line in proc.stdout.splitlines()[:12]:
        if "nazwisk" in line.lower() and ":" in line:
            return line.split(":", 1)[1].strip()
    return ""
