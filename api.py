import os

import boto3 as boto3
from botocore.exceptions import NoCredentialsError
from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn

load_dotenv()
app = FastAPI()

origins = ['*']

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Replace these with your DigitalOcean Spaces credentials
ACCESS_KEY = os.getenv('ACCESS_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')
BUCKET_NAME = os.getenv('BUCKET_NAME')

s3 = boto3.client(
    's3',
    # Replace with your Spaces region's endpoint
    endpoint_url='https://nyc3.digitaloceanspaces.com',
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
)


@app.get("/")
async def root():
    return {"message": "Hello from Fastapi"}


@app.post("/upload_file/")
async def upload_file(file: UploadFile):
    try:
        s3.upload_fileobj(
            file.file,
            BUCKET_NAME,
            file.filename,
        )
        return {"message": "File uploaded successfully"}
    except NoCredentialsError:
        return {"error": "No AWS credentials found"}


@app.post("/file_link")
async def file_link(file_name: str):
    try:
        url = s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': file_name
            },
            ExpiresIn=300
        )
        return {"url": url}
    except NoCredentialsError:
        return {"error": "No AWS credentials found"}


if __name__ == "__main__":
    uvicorn.run(app, host='0.0.0.0', port=8000)
