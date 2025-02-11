import os
import json
import uuid
import aiohttp
import asyncio
import logging

# Get the logger for this module
logger = logging.getLogger(__name__)


class MediaManager:
    def __init__(self, settings):
        self.data_store_base_url = settings.get('data_store_base_url')
        self.create_resource = settings.get('create_resource')
        self.upload_resource = settings.get('upload_resource')
        self.serve_media_resource = settings.get('serve_media_resource')
        self.delete_media_resource = settings.get('delete_media_resource')
        self.vision_service_api_url = settings.get('vision_service_api_url')
        self.link_resource = settings.get('link_resource')
        self.success_resource = settings.get('success_resource')
        self.failure_resource = settings.get('failure_resource')
        self.list_resource = settings.get('list_resource')

    def new_identity(self, image_path, token, loop=None):
        if not loop:
            loop = asyncio.get_event_loop()
        return loop.create_task(self._new_identity(image_path, token))

    def download_images_from_token(self, token, download_path='.', callback=None, loop=None):
        if not loop:
            loop = asyncio.get_event_loop()
        return loop.create_task(self._download_images_from_token(token, download_path, callback))

    def success(self, token, loop=None, callback=None):
        if not loop:
            loop = asyncio.get_event_loop()
        
        async def wrapper():
            try:
                await self._success(token)
            except Exception as e:
                logger.error(f"An error occurred while calling _success: {e}")
            finally:
                if callback:
                    callback()
        
        return loop.create_task(wrapper())

    def failure(self, token, loop=None, callback=None):
        if not loop:
            loop = asyncio.get_event_loop()
        
        async def wrapper():
            try:
                await self._failure(token)
            except Exception as e:
                logger.error(f"An error occurred while calling _failure: {e}")
            finally:
                if callback:
                    callback()
            
        return loop.create_task(wrapper())
    
    async def _new_identity(self, image_path, token):
        logger.debug("image path: %s", image_path)
        
        # Create a UUID
        file_uuid = str(uuid.uuid4())
        logger.debug("uuid: %s", file_uuid)
        ret = {
            "file_uuid":file_uuid, 
            "status":"ok",
            "msj":""
        }

        # Create Media by specifying its uuid and noc (number of chunks = 1)
        logger.debug("Create Media by specifying its uuid and noc (number of chunks = 1)")
        url = self.data_store_base_url + self.create_resource + '/' + file_uuid + '/1' + f'?token={token}'
        logger.debug("url: %s", url)
        headers = {
            'Content-Type': 'application/json',
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                logger.debug("response: %s", response.status)
                if (response.status >= 400):
                    ret["status"] = "error"
                    ret["msj"] = "Data Store: Create Media by specifying its uuid and noc. Response with status:" + str(response.status)
                    os.remove(image_path)
                    return ret

        # Upload Media by specifying its uuid and chunk (0)
        logger.debug("Upload Media by specifying its uuid and chunk (0)")
        url = self.data_store_base_url + self.upload_resource + '/' + file_uuid + '/0' + f'?token={token}'
        logger.debug("url: %s", url)
        with open(image_path, 'rb') as f:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data={'chunk': f}) as response:
                    logger.debug("Response: %s", response.status)
                    if (response.status >= 400):
                        ret["status"] = "error"
                        ret["msj"] = "Data Store: Upload Media by specifying its uuid and chunk (0). Response with status:" + str(response.status)
                        os.remove(image_path)
                        return ret
        
        # Link the Image with the token on the vision service api
        logger.debug("Link the Image with the token on the vision service api")
        url = self.vision_service_api_url + self.link_resource + '/' + token + '/' + file_uuid
        logger.debug("url: %s", url)
        async with aiohttp.ClientSession() as session:
            async with session.put(url) as response:
                logger.debug("Response: %s", response.status)
                if (response.status >= 400):
                    ret["status"] = "error"
                    ret["msj"] = "Registry: Link the Image with the token on the vision service api. Response with status:" + str(response.status)
                    os.remove(image_path)
                    return ret

        # Call Success on the vision service api
        logger.debug("Call Success on the vision service api")
        url = self.vision_service_api_url + self.success_resource + '/' + token
        async with aiohttp.ClientSession() as session:
            async with session.put(url) as response:
                logger.debug("Response: %s", response.status)
                if (response.status >= 400):
                    ret["status"] = "error"
                    ret["msj"] = "Registry: Call Success on the vision service api. Response with status:" + str(response.status)
                    os.remove(image_path)
                    return ret

        os.remove(image_path)
        return ret

    async def _download_images_from_token(self, token, download_path='.', callback=None):
        # Call List on the vision service api
        logger.debug("Call List on the vision service api")
        url = self.vision_service_api_url + self.list_resource + '/' + token
        logger.debug(url)
        downloaded_images = []  # Keep track of downloaded images
        ret = {
            "downloaded_images":downloaded_images, 
            "status":"ok",
            "msj":""
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                logger.debug("Response: %s", response)
                if (response.status >= 400):
                    ret["status"] = "error"
                    ret["msj"] = "Data Store: Call List on the vision service api. Response with status:" + str(response.status)
                    return ret

                # Print the response JSON data
                data = await response.json()
                logger.debug("Response JSON data: %s", json.dumps(data, indent=4))
                for item in data:
                    logger.debug("resource item: %s", item)
                   
                    # If its a data URL, 
                    if item.startswith("data"):
                        import re, base64
                        pattern = r"data:(?P<mime>[\w/\-\.]+);(?P<encoding>\w+),(?P<data>.*)"
                        match = re.match(pattern, item)
                        if match:
                            mime = match.group("mime")
                            encoding = match.group("encoding")
                            b64_data = match.group("data")

                            [mime_type, file_ext] = mime.split('/')
                            if mime_type == 'image' and encoding == 'base64':
                                file_path = f"{download_path}/image_{str(uuid.uuid4())}.{file_ext}"
                                with open(file_path, "wb") as file:
                                    binary_data = base64.b64decode(b64_data)
                                    file.write(binary_data)
                                logger.debug("Image downloaded successfully.")
                                downloaded_images.append(file_path)  # Add downloaded image to the list
                            else:
                                error_msg = "Only base64-encoded images are supported: MIME: %s encoding: %s", mime, encoding
                                logger.error(error_msg)
                                ret["status"] = "error"
                                ret["msj"] = error_msg
                        else:
                            error_msg = "Not a well-formed data URL: %s", item
                            logger.error(error_msg)
                            ret["status"] = "error"
                            ret["msj"] = error_msg
                    else:
                        if item.startswith("http"):
                            # Full URL
                            image_url = item
                            file_path = f"{download_path}/image_{str(uuid.uuid4())}.jpg" 
                        else:
                            # consider it as a relative UUID to download from Data Store
                            image_url = self.data_store_base_url + self.serve_media_resource + '/' + item
                            file_path = f"{download_path}/image_{item}.jpg" 

                        async with session.get(image_url) as image_response:
                            if image_response.status == 200:
                                with open(file_path, "wb") as file:
                                    while True:
                                        chunk = await image_response.content.read(1024)
                                        if not chunk:
                                            break
                                        file.write(chunk)
                                logger.debug("Image downloaded successfully.")
                                downloaded_images.append(file_path)  # Add downloaded image to the list
                            else:
                                logger.error("Failed to download image. Status code: %s", image_response.status)
                                ret["status"] = "error"
                                ret["msj"] = "Data Store: Download the image. Response with status:" + str(response.status)

        ret["downloaded_images"] = downloaded_images
        # Call the callback function if provided
        if callback is not None:
            callback(token, downloaded_images)        
        return ret

    async def _success(self, token):
        # Call Success on the vision service api
        logger.debug("Call Success on the vision service api")
        url = self.vision_service_api_url + self.success_resource + '/' + token
        logger.debug(f"URL: {url}")
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(url, timeout=10) as response:  # 10 seconds timeout
                    response.raise_for_status()  # Raise an HTTPError for bad responses
                    logger.debug("Response: %s", response)
            except asyncio.TimeoutError:
                logger.error("Request to %s timed out.", url)
            except aiohttp.ClientError as e:
                logger.error(f"Client error occurred: {e}")

    async def _failure(self, token):
        # Call Failure on the vision service api
        logger.debug("Call Failure on the vision service api")
        url = self.vision_service_api_url + self.failure_resource + '/' + token
        logger.debug(f"URL: {url}")
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(url, timeout=10) as response:  # 10 seconds timeout
                    response.raise_for_status()  # Raise an HTTPError for bad responses
                    logger.debug("Response: %s", response)
            except asyncio.TimeoutError:
                logger.error("Request to %s timed out.", url)
            except aiohttp.ClientError as e:
                logger.error(f"Client error occurred: {e}")