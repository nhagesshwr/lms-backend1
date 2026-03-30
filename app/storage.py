import boto3
from botocore.config import Config
from dotenv import load_dotenv
import os
import uuid

load_dotenv()

B2_KEY_ID     = os.getenv("B2_KEY_ID")
B2_APP_KEY    = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
B2_ENDPOINT   = os.getenv("B2_ENDPOINT")

# Map MIME types to safe file extensions
_CONTENT_TYPE_EXT: dict[str, str] = {
    "application/pdf":  "pdf",
    "video/mp4":        "mp4",
    "video/webm":       "webm",
    "video/ogg":        "ogv",
    "image/jpeg":       "jpg",
    "image/png":        "png",
    "image/gif":        "gif",
    "image/webp":       "webp",
    "application/msword":                                                    "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-powerpoint":                                         "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}


def _safe_extension(content_type: str) -> str:
    """Return a whitelisted extension for the given MIME type, or 'bin' for unknown."""
    return _CONTENT_TYPE_EXT.get(content_type.split(";")[0].strip().lower(), "bin")


def get_b2_client():
    return boto3.client(
        "s3",
        endpoint_url=B2_ENDPOINT,
        aws_access_key_id=B2_KEY_ID,
        aws_secret_access_key=B2_APP_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-005",
    )


def upload_file(file_bytes: bytes, filename: str, content_type: str) -> str:
    """
    Upload bytes to B2 storage.
    The original filename is ignored; the stored key is uuid + extension
    derived from the MIME type so no user-controlled path components exist.
    """
    ext = _safe_extension(content_type)
    safe_key = f"{uuid.uuid4().hex}.{ext}"

    client = get_b2_client()
    client.put_object(
        Bucket=B2_BUCKET_NAME,
        Key=safe_key,
        Body=file_bytes,
        ContentType=content_type,
    )
    public_url = f"{B2_ENDPOINT}/file/{B2_BUCKET_NAME}/{safe_key}"
    return public_url


def get_signed_url(file_url: str, expires_in: int = 3600) -> str:
    try:
        client = get_b2_client()
        key = file_url.split("/")[-1]
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": B2_BUCKET_NAME, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception:
        return file_url


def delete_file(file_url: str) -> None:
    try:
        client = get_b2_client()
        key = file_url.split("/")[-1]
        client.delete_object(Bucket=B2_BUCKET_NAME, Key=key)
    except Exception as e:
        # Log but don't raise — deletion failure is non-critical
        print(f"[storage] delete_file failed: {e}")
