"""PDF via existing Poppler executables; PPTX via standard-library ZIP/XML."""
import hashlib
import io
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zlib
from zipfile import BadZipFile, ZipFile

from .models import IngestionError, SourceChunk, SourceMaterial, normalized, stable_id

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 100
MAX_EXTRACTED_CHARS = 200_000
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _chunk(material_id: str, kind: str, number: int, text: str, failed=False) -> SourceChunk:
    clean = normalized(text)
    return SourceChunk(stable_id("src", material_id, kind, number), kind, number,
                       text, clean, "unreadable" if failed else "extracted" if clean else "empty")


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=15, check=False, env={**os.environ, "LC_ALL": "C"})


def _pdf(data: bytes, material_id: str) -> tuple[list[SourceChunk], list[str]]:
    info, extract = shutil.which("pdfinfo"), shutil.which("pdftotext")
    if not info or not extract:
        raise IngestionError("PDF extraction requires existing Poppler pdfinfo and pdftotext on PATH; nothing was installed.")
    chunks, issues = [], []
    with tempfile.TemporaryDirectory(prefix="course-pdf-") as directory:
        path = Path(directory) / "source.pdf"
        path.write_bytes(data)  # trusted snapshot, never pass caller paths to subprocess
        try:
            result = _run([info, str(path)])
            count = re.search(rb"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
            if result.returncode or not count:
                return [], ["pdf_unreadable_or_encrypted"]
            pages = int(count[1])
            if not 1 <= pages <= MAX_PAGES:
                raise IngestionError(f"PDF must contain 1–{MAX_PAGES} pages.")
            total = 0
            for number in range(1, pages + 1):
                try:
                    page = _run([extract, "-f", str(number), "-l", str(number),
                                 "-enc", "UTF-8", "-nopgbrk", str(path), "-"])
                    text = page.stdout.decode("utf-8", errors="strict")
                    failed = bool(page.returncode or page.stderr)
                except (subprocess.TimeoutExpired, UnicodeError, OSError):
                    text, failed = "", True
                total += len(text)
                if total > MAX_EXTRACTED_CHARS:
                    raise IngestionError("PDF extracted text exceeds the MVP size limit.")
                chunks.append(_chunk(material_id, "page", number, text, failed))
                if failed:
                    issues.append(f"page_{number}_unreadable")
        except subprocess.TimeoutExpired:
            return [], ["pdf_metadata_timeout"]
        except OSError:
            return [], ["pdf_extractor_failed"]
    return chunks, issues


def _xml(data: bytes) -> ET.Element:
    # Reject declarations even in UTF-16 input; no DTD/entity expansion is needed.
    if b"<!DOCTYPE" in data.upper().replace(b"\x00", b"") or b"<!ENTITY" in data.upper().replace(b"\x00", b""):
        raise ValueError("DTD not allowed")
    return ET.fromstring(data)


def _pptx(data: bytes, material_id: str) -> tuple[list[SourceChunk], list[str]]:
    chunks, issues = [], []
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (len(entries) > 2000 or sum(item.file_size for item in entries) > 40 * 1024 * 1024
                    or len({item.filename for item in entries}) != len(entries)):
                raise IngestionError("PPTX archive exceeds limits or has duplicate members.")
            presentation = _xml(archive.read("ppt/presentation.xml"))
            relationships = _xml(archive.read("ppt/_rels/presentation.xml.rels"))
            mapping = {}
            for relationship in relationships.findall(f"{{{REL}}}Relationship"):
                key = relationship.get("Id")
                if not key or key in mapping:
                    raise ValueError("Invalid relationship IDs")
                mapping[key] = relationship
            slides = presentation.findall(f"{{{P}}}sldIdLst/{{{P}}}sldId")
            if not 1 <= len(slides) <= MAX_PAGES:
                raise IngestionError(f"PPTX must contain 1–{MAX_PAGES} slides.")
            total = 0
            targets = set()
            for number, slide in enumerate(slides, 1):
                try:
                    relation = mapping[slide.attrib[f"{{{R}}}id"]]
                    target = relation.attrib["Target"]
                    part = posixpath.normpath(posixpath.join("ppt", target))
                    if (relation.get("TargetMode", "Internal") != "Internal"
                            or relation.get("Type") != R + "/slide"
                            or not re.fullmatch(r"ppt/slides/[^/]+\.xml", part)
                            or ".." in target.split("/") or part in targets):
                        raise ValueError("Invalid slide target")
                    targets.add(part)
                    root = _xml(archive.read(part))
                    if root.tag != f"{{{P}}}sld":
                        raise ValueError("Invalid slide root")
                    paragraphs = []
                    for paragraph in root.iter(f"{{{A}}}p"):
                        paragraphs.append("".join("\n" if child.tag == f"{{{A}}}br" else child.text or ""
                                                  for child in paragraph.iter()
                                                  if child.tag in {f"{{{A}}}t", f"{{{A}}}br"}))
                    text = "\n".join(paragraphs)
                    failed = False
                except (KeyError, ET.ParseError, ValueError, RuntimeError, BadZipFile, NotImplementedError, zlib.error):
                    text, failed = "", True
                total += len(text)
                if total > MAX_EXTRACTED_CHARS:
                    raise IngestionError("PPTX extracted text exceeds the MVP size limit.")
                chunks.append(_chunk(material_id, "slide", number, text, failed))
                if failed:
                    issues.append(f"slide_{number}_unreadable")
    except IngestionError:
        raise
    except (BadZipFile, KeyError, ET.ParseError, ValueError, RuntimeError, NotImplementedError, zlib.error):
        return [], ["pptx_unreadable"]
    return chunks, issues


def extract_material(path: str | Path) -> SourceMaterial:
    path = Path(path)
    kind = path.suffix.lower().lstrip(".")
    if kind not in {"pdf", "pptx"}:
        raise IngestionError("Only PDF and PPTX are supported.")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        raise IngestionError("Cannot read the source file.") from exc
    if len(data) > MAX_FILE_BYTES:
        raise IngestionError("Source files must be at most 20 MB.")
    digest = hashlib.sha256(data).hexdigest()
    material_id = stable_id("mat", path.name, digest)
    chunks, issues = (_pdf if kind == "pdf" else _pptx)(data, material_id)
    states = {chunk.status for chunk in chunks}
    if "extracted" in states:
        status = "partial" if issues or "empty" in states else "extracted"
    else:
        status = "unreadable" if issues else "empty"
    return SourceMaterial(material_id, path.name, digest, kind, tuple(chunks), status, tuple(issues))
