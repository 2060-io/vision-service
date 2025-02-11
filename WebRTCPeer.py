import asyncio
import json
import logging
import uuid
import cv2
from aiohttp import web
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from av import VideoFrame
from livenessDetector.LivenessDetector import LivenessDetector
#import threading

logger = logging.getLogger("WebServer")

# Get the logger for aiortc and set its level to WARNING
logger_aiortc = logging.getLogger('aiortc')
logger_aiortc.setLevel(logging.WARNING)
# Get the logger for aioice and set its level to WARNING
logger_aioice = logging.getLogger('aioice')
logger_aioice.setLevel(logging.WARNING)


pcs = set()
relay = MediaRelay()
videoTransforms = {}

class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an another track.
    """

    kind = "video"

    def __init__(self, asyncio_loop, verification_token, rd, d, q, lang, number_of_gestures_to_request, track):
        super().__init__()
        self.track = track
        self.livenessProcessor = LivenessDetector(
            asyncio_loop, 
            verification_token,
            rd,
            d,
            q,
            lang, 
            number_of_gestures_to_request
        )

    def cleanup(self):
        if self.livenessProcessor:
            self.livenessProcessor.cleanup()
            self.livenessProcessor = None
    
    def __del__(self):
        logger.debug("VideoTransformTrack Destoyed")
        self.cleanup()
        
    async def recv(self):
        #logger.debug("WebRTC Peer>>>>>> %s",threading.current_thread().name)
        frame = await self.track.recv()
        
        # perform Image processing
        img = frame.to_ndarray(format="bgr24")        
        img_out = self.livenessProcessor.process_image(img)

        # rebuild a VideoFrame, preserving timing information
        new_frame = VideoFrame.from_ndarray(img_out, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame

def log_info(xsource, msg, *args):
    logger.info(xsource + " " + msg, *args)

async def offer(asyncio_loop, number_of_gestures_to_request, request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    logger.debug("!! Verification token: %s", params.get("token"))
    verification_token = params.get("token")
    rd = params.get("rd")
    d = params.get("d")
    q = params.get("q")
    lang = params.get("lang")
    pc = RTCPeerConnection()
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    log_info(pc_id, "Created for %s", request.remote)

    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str) and message.startswith("ping"):
                channel.send("pong" + message[4:])

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info(pc_id, "Connection state is %s", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        log_info(pc_id, "Track %s received", track.kind)

        if track.kind == "video":
            videoTransforms[verification_token] = VideoTransformTrack(
                asyncio_loop,
                verification_token,
                rd,
                d,
                q,
                lang,
                number_of_gestures_to_request,
                relay.subscribe(track)
            )

            pc.addTrack(
                videoTransforms[verification_token]
            )

        @track.on("ended")
        async def on_ended():
            log_info(pc_id, "Track %s ended", track.kind)

    # handle offer
    await pc.setRemoteDescription(offer)

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )

async def get_gestures_requester_process_status(request):
    verification_token = request.query.get("token")
    if verification_token in videoTransforms:
        vt = videoTransforms[verification_token]
        status = vt.livenessProcessor.get_gestures_requester_process_status()
        log = vt.livenessProcessor.get_gestures_requester_overwrite_text_log()
        ret = {
            "status": status,
            "log": log
        }
        return web.Response(text=json.dumps(ret))
    else:
        ret = {
            "status": "no_status",
            "log": ""
        }
        return web.Response(text=json.dumps(ret))

async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()