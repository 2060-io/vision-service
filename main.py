import asyncio
import os
from distutils.util import strtobool
from functools import partial
import ssl
import logging
from aiohttp import web

from WebRTCPeer import offer, on_shutdown, get_gestures_requester_process_status
from MediasoupClient import connectToMediasoupServer
from dotenv import load_dotenv
from miscEndpoints import mediasoup_images, serve_images, set_mediasoup_setting
import mediasoupSettings

load_dotenv(override=True)
# Create a logger object.
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Create a console handler and set level to debug.
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# Create a file handler and set level to debug.
fh = logging.FileHandler('app.log')
fh.setLevel(logging.DEBUG)

# Create a formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add formatter to ch and fh
ch.setFormatter(formatter)
fh.setFormatter(formatter)

# Add ch and fh to logger
logger.addHandler(ch)
logger.addHandler(fh)



if __name__ == "__main__":
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "loglevel;error"
    verbose = os.environ.get("VERVOSE_APP")
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    cert_file = os.environ.get("CERT_FILE_APP")
    key_file = os.environ.get("KEY_FILE_APP")
    if cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(cert_file, key_file)
    else:
        ssl_context = None

    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST")
    verification_index_path = os.environ.get("VERIFICATION_INDEX_PATH")
    logging.info("verification_index_path: %s", verification_index_path)
    verification_client_js_path = os.environ.get("VERIFICATION_CLIENT_JS_PATH")
    capture_index_path = os.environ.get("CAPTURE_INDEX_PATH")
    offer_path = os.environ.get("OFFER_PATH")
    picture_path = os.environ.get("PICTURE_PATH")
    connect_to_mediasoup_path = os.environ.get("CONNECT_TO_MEDIASOUP_SERVER_PATH")
    requester_status_path = os.environ.get("REQUESTER_STATUS_PATH")
    logging.info("requester_status_path: %s", requester_status_path)
    number_of_gestures_to_request = int(os.environ.get("NUMBER_OF_GESTURES_TO_REQUEST",2))
    vision_matcher_base_url = os.environ.get("VISION_MATCHER_BASE_URL", "http://localhost:5123")
    logging.info("vision_matcher_base_url: %s", vision_matcher_base_url)
    
    logging.info("NUMBER_OF_GESTURES_TO_REQUEST: %d", number_of_gestures_to_request)
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    
    asyncio_loop = asyncio.get_event_loop()
    logging.info("Asyncio loop: %s", asyncio_loop)
    # Pass the environment variable to the offer function when invoked by aiohttp
    app.router.add_post(offer_path, partial(offer, asyncio_loop, number_of_gestures_to_request, vision_matcher_base_url))
    app.router.add_post(connect_to_mediasoup_path, partial(connectToMediasoupServer, vision_matcher_base_url))
    app.router.add_get(requester_status_path, get_gestures_requester_process_status)


    app.router.add_get('/ms_images', serve_images)  # Add route to view images
    app.router.add_get('/mediasoup_images/{filename}', mediasoup_images)
    app.router.add_post('/set_mediasoup_setting', set_mediasoup_setting)
    
    web.run_app(
        app, access_log=None, host=host, port=port, ssl_context=ssl_context, loop=asyncio_loop
    )
