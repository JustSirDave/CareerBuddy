# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
"""
CareerBuddy - Cloudinary Storage
Uploads, deletes, and resolves URLs for generated documents.
"""
import asyncio

import cloudinary
import cloudinary.uploader
import cloudinary.utils
from loguru import logger


def _configure():
    from app.config import settings
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


async def upload_document(file_bytes: bytes, filename: str, job_id: str) -> str:
    """Upload document bytes to Cloudinary. Returns secure URL."""
    _configure()
    public_id = f"careerbuddy/jobs/{job_id}/{filename}"
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: cloudinary.uploader.upload(
            file_bytes,
            public_id=public_id,
            resource_type="raw",
            overwrite=True,
        ),
    )
    url = result["secure_url"]
    logger.info(f"[cloud_storage] Uploaded {filename} → {url}")
    return url


async def delete_document(job_id: str, filename: str) -> None:
    """Delete a document from Cloudinary."""
    _configure()
    public_id = f"careerbuddy/jobs/{job_id}/{filename}"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: cloudinary.uploader.destroy(public_id, resource_type="raw"),
    )
    logger.info(f"[cloud_storage] Deleted {public_id}")


def get_download_url(job_id: str, filename: str) -> str:
    """Build the Cloudinary URL for a document without an API call."""
    _configure()
    public_id = f"careerbuddy/jobs/{job_id}/{filename}"
    url, _ = cloudinary.utils.cloudinary_url(public_id, resource_type="raw")
    return url
