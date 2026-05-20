# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
"""
CareerBuddy - Storage Service
Cloud document upload via Cloudinary and DOCX-to-PDF conversion via LibreOffice.
"""
import asyncio
import tempfile
from pathlib import Path

from loguru import logger


async def save_document(job_id: str, file_bytes: bytes, filename: str) -> str:
    """Upload document to Cloudinary. Returns the secure URL."""
    from app.services.cloud_storage import upload_document
    return await upload_document(file_bytes, filename, job_id)


async def fetch_document_bytes(url: str) -> bytes:
    """Fetch raw bytes from a URL (used to retrieve Cloudinary documents)."""
    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


async def convert_docx_to_pdf(docx_path) -> tuple[bytes | None, str]:
    """Convert a DOCX file to PDF using LibreOffice.

    Returns (pdf_bytes, pdf_filename) or (None, "") on failure.
    """
    try:
        docx_path = Path(docx_path)
        if not docx_path.exists():
            logger.error(f"[convert_docx_to_pdf] File not found: {docx_path}")
            return None, ""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            cmd = [
                "libreoffice",
                "--headless",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                str(temp_dir_path),
                str(docx_path),
            ]
            logger.info(f"[convert_docx_to_pdf] Running: {' '.join(cmd)}")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                logger.error("[convert_docx_to_pdf] Conversion timed out after 30 seconds")
                return None, ""

            if proc.returncode != 0:
                logger.error(f"[convert_docx_to_pdf] LibreOffice error: {stderr.decode()}")
                return None, ""

            pdf_filename = docx_path.stem + ".pdf"
            pdf_path = temp_dir_path / pdf_filename
            if not pdf_path.exists():
                logger.error(f"[convert_docx_to_pdf] PDF not generated: {pdf_path}")
                return None, ""

            loop = asyncio.get_event_loop()
            pdf_bytes = await loop.run_in_executor(None, pdf_path.read_bytes)
            logger.info(f"[convert_docx_to_pdf] Converted ({len(pdf_bytes)} bytes)")
            return pdf_bytes, pdf_filename

    except Exception as e:
        logger.error(f"[convert_docx_to_pdf] Conversion failed: {e}")
        return None, ""
