import asyncio
import os
from distutils.util import strtobool
from functools import partial
import ssl
import logging
from aiohttp import web

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
    verbose = os.environ.get("VERBOSE")
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
    host = os.environ.get("HOST", "0.0.0.0")
    connect_to_mediasoup_path = "/join-call"

    vision_matcher_base_url = os.environ.get("VISION_MATCHER_BASE_URL", "http://localhost:5123")
    logging.info("vision_matcher_base_url: %s", vision_matcher_base_url)
    
    number_of_gestures_to_request = int(os.environ.get("NUMBER_OF_GESTURES_TO_REQUEST",2))
    logging.info("NUMBER_OF_GESTURES_TO_REQUEST: %d", number_of_gestures_to_request)
    enable_debug_endpoints_str = os.environ.get("ENABLE_DEBUG_ENDPOINTS", "false")
    enable_debug_endpoints = bool(strtobool(enable_debug_endpoints_str))
    logging.info("enable_debug_endpoints: %s", enable_debug_endpoints_str)

    glasses_detector_mode = os.environ.get("GLASSES_DETECTOR_MODE", "OFF")
    logging.info(f"glasses_detector_mode:{glasses_detector_mode}")

    use_mediasoup_ice_relay_str = os.environ.get("USE_MEDIASOUP_ICE_RELAY", "false")
    use_mediasoup_ice_relay = bool(strtobool(use_mediasoup_ice_relay_str))
    logging.info(f"use_mediasoup_ice_relay:{use_mediasoup_ice_relay}")

    app = web.Application()
        
    asyncio_loop = asyncio.get_event_loop()
    logging.info("Asyncio loop: %s", asyncio_loop)
    # Pass the environment variable to the offer function when invoked by aiohttp
    app.router.add_post(connect_to_mediasoup_path, partial(connectToMediasoupServer, vision_matcher_base_url, use_mediasoup_ice_relay, glasses_detector_mode))

    if enable_debug_endpoints:
        app.router.add_get('/ms_images', serve_images)  # Add route to view images
        app.router.add_get('/mediasoup_images/{filename}', mediasoup_images)
        app.router.add_post('/set_mediasoup_setting', set_mediasoup_setting)
    
    web.run_app(
        app, access_log=None, host=host, port=port, ssl_context=ssl_context, loop=asyncio_loop
    )
