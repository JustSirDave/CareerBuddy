"""
CareerBuddy - File Storage Service
Handles local document storage and DOCX to PDF conversion
Author: Sir Dave
"""
import os
import subprocess
import tempfile
from pathlib import Path
from loguru import logger
def save_file_locally(job_id: str, file_bytes: bytes, filename: str) -> str:
    """
    Save file to local filesystem.

    Args:
        job_id: Job ID
        file_bytes: File content
        filename: Filename

    Returns:
        Local file path
    """
    # Create directory structure
    output_dir = Path("output") / "jobs" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    file_path = output_dir / filename
    file_path.write_bytes(file_bytes)

    logger.info(f"[storage] Saved file locally to {file_path}")
    return str(file_path)


def convert_docx_to_pdf(docx_path) -> tuple[bytes | None, str]:
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

        # Create temporary directory for output
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Run LibreOffice conversion with PDF export filter
            # --headless: run without GUI
            # --convert-to: output format with filter options
            # --outdir: output directory
            # Filter options:
            # - SelectPdfVersion=1 (PDF 1.4)
            # - UseTaggedPDF=false (disable tagging for exact layout)
            # - ExportBookmarks=false
            # - ExportNotes=false
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
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            if result.returncode != 0:
                logger.error(f"[convert_docx_to_pdf] LibreOffice error: {result.stderr}")
                return None, ""
            
            # Find the generated PDF
            pdf_filename = docx_path.stem + ".pdf"
            pdf_path = temp_dir_path / pdf_filename
            
            if not pdf_path.exists():
                logger.error(f"[convert_docx_to_pdf] PDF not generated: {pdf_path}")
                return None, ""
            
            # Read PDF bytes
            pdf_bytes = pdf_path.read_bytes()
            logger.info(f"[convert_docx_to_pdf] Successfully converted to PDF ({len(pdf_bytes)} bytes)")
            
            return pdf_bytes, pdf_filename
    
    except subprocess.TimeoutExpired:
        logger.error("[convert_docx_to_pdf] Conversion timed out after 30 seconds")
        return None, ""
    except Exception as e:
        logger.error(f"[convert_docx_to_pdf] Conversion failed: {e}")
        return None, ""
