import boto3
import os
from dotenv import load_dotenv

load_dotenv()

s3_client = boto3.client(
    "s3",
    endpoint_url=os.getenv("R2_ENDPOINT_URL"),
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
)

BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
PUBLIC_URL = os.getenv("R2_PUBLIC_URL")


def upload_file_to_storage(file_obj, key: str) -> str:
    s3_client.upload_fileobj(file_obj, BUCKET_NAME, key)
    return f"{PUBLIC_URL}/{key}"


def delete_file_from_storage(key: str):
    s3_client.delete_object(Bucket=BUCKET_NAME, Key=key)