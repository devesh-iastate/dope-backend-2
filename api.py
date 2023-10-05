import json
import os

import boto3 as boto3
from botocore.exceptions import NoCredentialsError
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import uvicorn
import aiohttp

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
admin_username = os.getenv('admin_username')
admin_apiKey = os.getenv('admin_apiKey')
GROUP_ID = os.getenv('GROUP_ID')
APP_ID = os.getenv('APP_ID')

client = boto3.client(
    's3',
    # Replace with your Spaces region's endpoint
    endpoint_url='https://nyc3.digitaloceanspaces.com',
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
)


async def verify_token(user_token):
    admin_token_url = "https://realm.mongodb.com/api/admin/v3.0/auth/providers/mongodb-cloud/login"
    data = {
        "username": admin_username,
        "apiKey": admin_apiKey
    }
    async with aiohttp.ClientSession() as session:

        async with session.post(admin_token_url, json=data) as response:
            if response.status == 200:
                admin_token = await response.json()
            else:
                return response
        admin_access_token = admin_token["access_token"]
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + admin_access_token
    }
    payload = json.dumps({
        "token": user_token
    })
    client_verify_token_url = f"https://realm.mongodb.com/api/admin/v3.0/groups/{GROUP_ID}/apps/{APP_ID}/users/verify_token"
    async with aiohttp.ClientSession() as session:
        async with session.post(client_verify_token_url, headers=headers, data=payload) as response:
            if response.status == 200:
                return 200
            else:
                return response



@app.post("/upload_file/")
async def upload_file(folder: str = Form(...), token: str = Form(...), file: UploadFile = File(...)):
    try:
        # Check if the folder exists
        token_status = await verify_token(token)
        if token_status != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        folder_exists = False
        for obj in client.list_objects(Bucket=BUCKET_NAME)['Contents']:
            if obj['Key'].startswith(folder + '/'):
                folder_exists = True
                break

        # If folder does not exist, create it
        if not folder_exists:
            client.put_object(Bucket=BUCKET_NAME, Key=(folder + '/'))

        # Upload the file to the folder
        file_content = await file.read()
        file_key = f'{folder}/{file.filename}'
        client.put_object(Bucket=BUCKET_NAME, Key=file_key, Body=file_content)

        # Generate a presigned URL for downloading the file
        url = client.generate_presigned_url('get_object',
                                            Params={'Bucket': BUCKET_NAME, 'Key': file_key}
                                            )

        return JSONResponse(content={"message": "File uploaded successfully!", "url": url}, status_code=200)
    except NoCredentialsError:
        return {"error": "No AWS credentials found"}


if __name__ == "__main__":
    uvicorn.run(app, host='0.0.0.0', port=8000)
