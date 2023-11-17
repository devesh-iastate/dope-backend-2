import json
import os

import aiohttp
import boto3 as boto3
import uvicorn
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, status, Form, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from io import BytesIO
import zipfile

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


@app.post("/api/upload_file/")
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

        # Save file in local folder
        local_folder_path = '/lss/baskarg-lab/onr-organic-muri/backup/' + folder
        os.makedirs(local_folder_path, exist_ok=True)
        local_file_path = os.path.join(local_folder_path, file.filename)
        with open(local_file_path, 'wb') as local_file:
            local_file.write(file_content)

        return JSONResponse(content={"message": "File uploaded successfully!"}, status_code=200)
    except NoCredentialsError:
        return {"error": "No AWS credentials found"}


@app.post("/api/generate_download_link/")
async def generate_download_link(request: Request):
    body = await request.json()
    file_path = body.get('filePath')
    token = body.get('token')
    # Verify the token
    token_status = await verify_token(token)
    if token_status != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Generate a presigned URL for downloading the file
    try:
        url = client.generate_presigned_url('get_object',
                                            Params={'Bucket': BUCKET_NAME, 'Key': file_path}, ExpiresIn=604800
                                            )
        return JSONResponse(content={"url": url}, status_code=200)

    except Exception as e:
        print(str(e))
        return {"error": str(e)}


@app.post("/api/download_folder/")
async def download_folder(request: Request):
    try:
        body = await request.json()
        folder = body.get('folder')
        print(folder)
        token = body.get('token')
        token_status = await verify_token(token)
        if token_status != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        # Create a BytesIO object to store the zip file
        in_memory_zip = BytesIO()

        with zipfile.ZipFile(in_memory_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for obj in client.list_objects(Bucket=BUCKET_NAME, Prefix=f"{folder}/")['Contents']:
                file_key = obj['Key']
                file_obj = client.get_object(Bucket=BUCKET_NAME, Key=file_key)
                file_data = file_obj['Body'].read()
                zf.writestr(file_key, file_data)

        in_memory_zip.seek(0)

        headers = {
            'Content-Disposition': f'attachment; filename={folder}.zip'
        }

        return Response(content=in_memory_zip.getvalue(), media_type="application/zip", headers=headers)
    except NoCredentialsError:
        return {"error": "No AWS credentials found"}


if __name__ == "__main__":
    uvicorn.run(app, host='0.0.0.0', port=8000)
