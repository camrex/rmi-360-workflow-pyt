#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
s3_transfer_config.py
=====================

S3 transfer configuration optimized for file size.

Provides adaptive multipart upload settings for maximum reliability
with large files (4GB+).
"""

from __future__ import annotations

try:
    from boto3.s3.transfer import TransferConfig
except ImportError:
    raise ImportError("boto3 is required. Install with: pip install boto3")


def get_transfer_config(file_size_bytes: int, max_workers: int = 16) -> TransferConfig:
    """
    Get optimized transfer config based on file size.

    Strategy:
    - Small files (<512MB): 8MB parts, standard concurrency for speed
    - Medium files (512MB-8GB): 64MB parts, reduced concurrency for stability
    - Large files (8GB+): 128MB parts, minimal concurrency for reliability

    Args:
        file_size_bytes: Size of file to upload
        max_workers: Maximum number of concurrent workers

    Returns:
        TransferConfig optimized for the file size
    """
    mb = 1024 * 1024
    gb = 1024 * mb

    if file_size_bytes < 512 * mb:
        # Small files: 8MB parts, standard concurrency
        return TransferConfig(
            multipart_threshold=16 * mb,
            multipart_chunksize=8 * mb,
            max_concurrency=min(max_workers, 8),
            use_threads=True,
            io_chunksize=8 * mb,
            max_io_queue=4
        )
    elif file_size_bytes < 8 * gb:
        # Medium-large files (512MB-8GB): 64MB parts, reduced concurrency
        return TransferConfig(
            multipart_threshold=64 * mb,
            multipart_chunksize=64 * mb,
            max_concurrency=min(max_workers, 6),
            use_threads=True,
            io_chunksize=16 * mb,
            max_io_queue=6
        )
    else:
        # Very large files (8GB+): 128MB parts, minimal concurrency for stability
        return TransferConfig(
            multipart_threshold=128 * mb,
            multipart_chunksize=128 * mb,
            max_concurrency=min(max_workers, 4),
            use_threads=True,
            io_chunksize=16 * mb,
            max_io_queue=8
        )


def get_boto_config():
    """
    Get enhanced boto3 client configuration for large file uploads.

    Features:
    - Adaptive retry mode with up to 12 attempts
    - Extended timeouts (20s connect, 5min read)
    - Increased connection pool for concurrent uploads

    Returns:
        botocore.config.Config instance
    """
    try:
        from botocore.config import Config
    except ImportError:
        raise ImportError("botocore is required (should come with boto3)")

    return Config(
        retries={
            'mode': 'adaptive',
            'max_attempts': 12
        },
        connect_timeout=20,      # 20s connection timeout
        read_timeout=300,        # 5min read timeout for large parts
        max_pool_connections=50  # More connection pool
    )
