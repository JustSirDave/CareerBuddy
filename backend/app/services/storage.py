"""
CareerBuddy - File Storage Service
Handles local document storage and DOCX to PDF conversion
Author: Sir Dave
"""
import asyncio
import os
import tempfile
from pathlib import Path
from loguru import logger


async def save_file_locally(job_id: str, file_bytes: bytes, filename: str) -> str:
    """
    Save file to local filesystem.

    Args:
        job_id: Job ID
        file_bytes: File content
        filename: Filename

    Returns:
        Local file path
    """
    from app.config import settings
    output_dir = Path(settings.output_dir) / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    file_path = output_dir / filename
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, file_path.write_bytes, file_bytes)

    logger.info(f"[storage] Saved file locally to {file_path}")
    return str(file_path)


async def convert_docx_to_pdf(docx_path) -> tuple[bytes | None, str]:
    """
    Convert a DOCX file to PDF using LibreOffice.

    Args:
        docx_path: Path to the .docx file (string or Path object)

    Returns:
        Tuple of (PDF bytes, PDF filename) or (None, "") if conversion fails
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
                str(docx_path)
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
            logger.info(f"[convert_docx_to_pdf] Successfully converted to PDF ({len(pdf_bytes)} bytes)")
            return pdf_bytes, pdf_filename

    except Exception as e:
        logger.error(f"[convert_docx_to_pdf] Conversion failed: {e}")
        return None, ""
