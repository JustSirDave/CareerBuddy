"""
File Storage Service - S3/Cloudflare R2 integration
Handles document uploads and generates signed URLs
"""
import hashlib
from typing import Optional
from loguru import logger

from app.config import settings
from app.models import File
from sqlalchemy.orm import Session

# Initialize S3 client only if credentials are provided
_s3_client = None
if settings.s3_access_key_id and settings.s3_bucket:
    try:
        import boto3
        _s3_client = boto3.client(
            's3',
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region or 'auto'
        )
        logger.info("[storage] S3/R2 client initialized successfully")
    except Exception as e:
        logger.warning(f"[storage] Failed to initialize S3 client: {e}")


def upload_file(
    db: Session,
    job_id: str,
    file_bytes: bytes,
    kind: str,
    filename: str
) -> Optional[File]:
    """
    Upload file to S3/R2 and save metadata to database.

    Args:
        db: Database session
        job_id: Job ID this file belongs to
        file_bytes: File content as bytes
        kind: File type (e.g., "preview_pdf", "final_docx")
        filename: Original filename

    Returns:
        File model instance or None if upload failed
    """
    if not _s3_client:
        logger.error("[storage] S3 client not initialized, cannot upload")
        return None

    try:
        # Generate storage key (path in S3)
        storage_key = f"jobs/{job_id}/{kind}/{filename}"

        # Calculate checksum
        checksum = hashlib.sha256(file_bytes).hexdigest()

        # Determine content type
        content_type = _get_content_type(filename)

        # Upload to S3/R2
        _s3_client.put_object(
            Bucket=settings.s3_bucket,
            Key=storage_key,
            Body=file_bytes,
            ContentType=content_type,
            # Make file publicly readable (optional, depends on bucket policy)
            # ACL='public-read'  # Uncomment if needed
        )

        logger.info(f"[storage] Uploaded {len(file_bytes)} bytes to {storage_key}")

        # Save metadata to database
        file_record = File(
            job_id=job_id,
            kind=kind,
            storage_key=storage_key,
            checksum=checksum,
            size=len(file_bytes)
        )
        db.add(file_record)
        db.commit()
        db.refresh(file_record)

        logger.info(f"[storage] Created file record id={file_record.id}")
        return file_record

    except Exception as e:
        logger.error(f"[storage] Failed to upload file: {e}")
        db.rollback()
        return None


def get_download_url(storage_key: str, expires_in: int = 3600) -> Optional[str]:
    """
    Generate a presigned download URL for a file.

    Args:
        storage_key: S3 object key
        expires_in: URL expiration time in seconds (default 1 hour)

    Returns:
        Presigned URL or None if failed
    """
    if not _s3_client:
        logger.error("[storage] S3 client not initialized")
        return None

    try:
        url = _s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.s3_bucket,
                'Key': storage_key
            },
            ExpiresIn=expires_in
        )
        logger.info(f"[storage] Generated presigned URL for {storage_key}")
        return url

    except Exception as e:
        logger.error(f"[storage] Failed to generate presigned URL: {e}")
        return None


def get_public_url(storage_key: str) -> str:
    """
    Get public URL for a file (if bucket allows public access).

    Args:
        storage_key: S3 object key

    Returns:
        Public URL
    """
    if settings.s3_endpoint:
        # Cloudflare R2 or custom endpoint
        base_url = settings.s3_endpoint.rstrip('/')
        return f"{base_url}/{settings.s3_bucket}/{storage_key}"
    else:
        # Standard AWS S3
        region = settings.s3_region or 'us-east-1'
        return f"https://{settings.s3_bucket}.s3.{region}.amazonaws.com/{storage_key}"


def delete_file(db: Session, file_id: str) -> bool:
    """
    Delete file from S3 and database.

    Args:
        db: Database session
        file_id: File record ID

    Returns:
        True if successful, False otherwise
    """
    if not _s3_client:
        logger.error("[storage] S3 client not initialized")
        return False

    try:
        # Get file record
        file_record = db.query(File).filter(File.id == file_id).first()
        if not file_record:
            logger.warning(f"[storage] File {file_id} not found")
            return False

        # Delete from S3
        _s3_client.delete_object(
            Bucket=settings.s3_bucket,
            Key=file_record.storage_key
        )

        # Delete from database
        db.delete(file_record)
        db.commit()

        logger.info(f"[storage] Deleted file {file_id}")
        return True

    except Exception as e:
        logger.error(f"[storage] Failed to delete file: {e}")
        db.rollback()
        return False


def list_job_files(db: Session, job_id: str) -> list[File]:
    """
    Get all files for a job.

    Args:
        db: Database session
        job_id: Job ID

    Returns:
        List of File records
    """
    return db.query(File).filter(File.job_id == job_id).all()


def _get_content_type(filename: str) -> str:
    """Determine content type from filename"""
    if filename.endswith('.pdf'):
        return 'application/pdf'
    elif filename.endswith('.docx'):
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif filename.endswith('.doc'):
        return 'application/msword'
    elif filename.endswith('.txt'):
        return 'text/plain'
    else:
        return 'application/octet-stream'


# Fallback: Local filesystem storage (for development without S3)
def save_file_locally(job_id: str, file_bytes: bytes, filename: str) -> str:
    """
    Save file to local filesystem (development only).

    Args:
        job_id: Job ID
        file_bytes: File content
        filename: Filename

    Returns:
        Local file path
    """
    import os
    from pathlib import Path

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
    import subprocess
    import tempfile
    from pathlib import Path

    try:
        docx_path = Path(docx_path)
        if not docx_path.exists():
            logger.error(f"[convert_docx_to_pdf] File not found: {docx_path}")
            return None, ""

        # Create temporary directory for output
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Run LibreOffice conversion
            # --headless: run without GUI
            # --convert-to pdf: output format
            # --outdir: output directory
            cmd = [
                "libreoffice",
                "--headless",
                "--convert-to",
                "pdf",
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
