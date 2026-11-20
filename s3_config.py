import os
import boto3
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET = os.getenv("S3_BUCKET")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION
)
