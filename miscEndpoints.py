import os
from aiohttp import web
import mimetypes
from mediasoupSettings import set_setting
import shutil


# Directory where images are stored
IMAGE_DIR = 'saved_images_temp'

# Handler to serve individual images
async def mediasoup_images(request):
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



# Handler function for serving the images
async def serve_images(request):
    # Check if the directory exists
    if not os.path.exists(IMAGE_DIR):
        raise web.HTTPNotFound(reason=f"Directory {IMAGE_DIR} does not exist.")

    # Get list of image files
    image_files = [f for f in os.listdir(IMAGE_DIR) if f.endswith('.jpg')]

    image_files.sort()

    # Create an HTML response with the images
    html_content = "<html><head><title>Image Gallery</title></head><body><h1>Images</h1><ul>"

    for image_file in image_files:
        img_path = f'/mediasoup_images/{image_file}'
        html_content += f'<li><img src="{img_path}" style="max-width: 500px;"/><br>{image_file}</li>'

    html_content += "</ul></body></html>"

    return web.Response(text=html_content, content_type='text/html')


def clear_image_directory():
    # Ensure the directory exists
    if os.path.exists(IMAGE_DIR):
        # Remove all files in the directory
        shutil.rmtree(IMAGE_DIR)
        # Recreate the directory to ensure it's empty and still exists
        os.makedirs(IMAGE_DIR)

async def set_mediasoup_setting(request):
    try:
        # Parse the JSON body of the request
        data = await request.json()

        # Loop through each key-value pair in the JSON
        for key, value in data.items():
            if key == 'clear_saved_images' and value is True:
                # Clear the image directory if the key is 'clear_saved_images' and its value is true
                clear_image_directory()
            else:
                try:
                    # Use the set_setting function to update your settings for other keys
                    set_setting(key, value)
                except KeyError as e:
                    # If a key is not found, return a 400 response
                    return web.json_response({'error': str(e)}, status=400)

        # Respond with a success message
        return web.json_response({'message': 'Settings updated successfully.'}, status=200)
    except Exception as e:
        # Handle any other exceptions and return a 500 error
        return web.json_response({'error': 'Failed to parse JSON or update settings', 'details': str(e)}, status=500)