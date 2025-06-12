import asyncio
import os
import mimetypes
import logging
from aiohttp import web

# Create a logger object.
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Create a console handler and set level to debug.
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# Create a formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add formatter to ch and fh
ch.setFormatter(formatter)

# Add ch and fh to logger
logger.addHandler(ch)

IMAGE_DIR = './assets'

async def assets(request):
    filename = request.match_info['filename']
    file_path = os.path.join(IMAGE_DIR, filename)

    # Check if the file exists
    if not os.path.exists(file_path):
        return web.HTTPNotFound(reason=f"File {filename} not found.")

    # Guess the content type
    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = 'application/octet-stream'
    
    return web.FileResponse(file_path, headers={"Content-Type": content_type})

async def list(request):
    filename = request.match_info['token']
    file_path = os.path.join(IMAGE_DIR, filename)

    # Check if the file exists
    if not os.path.exists(file_path):
        return web.HTTPNotFound(reason=f"File {filename} not found.")
   
    
    base_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5001")

    return web.json_response([f"http://{host}:{port}/assets/{filename}"])

async def success(request):
    token = request.match_info['token']
    logging.info("success: %s", token)
    return web.Response(text='Success')

async def failure(request):
    token = request.match_info['token']
    logging.info("failure: %s", token)
    return web.Response(text='Failure')

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = web.Application()
        
    asyncio_loop = asyncio.get_event_loop()

    port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "0.0.0.0")

    app.router.add_get('/assets/{filename}', assets) 
    app.router.add_get('/list/{token}', list) 
    app.router.add_put('/success/{token}', success)
    app.router.add_put('/failure/{token}', failure)
    
    web.run_app(
        app, access_log=None, host=host, port=port, loop=asyncio_loop
    )
