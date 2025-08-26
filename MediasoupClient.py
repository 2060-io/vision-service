import os
from aiohttp import web
import sys
import json
import asyncio
import argparse
import secrets
from typing import Optional, Dict, Awaitable, Any, TypeVar
from asyncio.futures import Future
from datetime import datetime
import mediasoupSettings

from pymediasoup import Device
from pymediasoup import AiortcHandler
from pymediasoup.transport import Transport
from pymediasoup.consumer import Consumer
from pymediasoup.producer import Producer
from pymediasoup.data_consumer import DataConsumer
from pymediasoup.data_producer import DataProducer
from pymediasoup.sctp_parameters import SctpStreamParameters


from mediaManager.MediaManagerSettings import generate_mm_settings
from mediaManager.MediaManager import MediaManager
from liveness_detector.server_launcher import GestureServerClient

import traceback

# Import aiortc
from aiortc import VideoStreamTrack

# Implement simple protoo client
import websockets
from random import random

import cv2
import numpy as np
from av import VideoFrame
import time

import logging

# Get the logger for this module
logger = logging.getLogger(__name__)

def strtobool(val):
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return 1
    elif val in ("n", "no", "f", "false", "off", "0"):
        return 0
    else:
        raise ValueError(f"invalid truth value: {val}")


class OutgoingVideoStreamTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.width = 640
        self.height = 480
        self.circle_radius = 15  # Starting radius for the circle
        self.max_radius = 45  # Maximum radius the circle can grow to
        self.min_radius = 15  # Minimum radius the circle can shrink to
        self.radius_growth = 0.5  # Smaller increments for a smooth pulsing effect
        self.growing = True  # State to determine if the circle is growing or shrinking
        self.frames = []

        self.last_saved_time = 0
        self.save_dir = 'saved_images_temp'
        # Ensure the directory exists
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)        

    def add_frame(self, frame):
        self.frames.append(frame)

    def animate_frame(self, pts, time_base, leave_blank=True):
        # Create a blank frame
        frame = np.zeros((self.height, self.width, 3), np.uint8)

        if not leave_blank:
            # Calculate center of the frame
            center_x = self.width // 2
            center_y = self.height // 2

            # Draw a circle at the center of the frame
            cv2.circle(frame, (center_x, center_y), int(self.circle_radius), (0, 255, 0), -1)

            # Update circle radius for smooth pulsing
            if self.growing:
                self.circle_radius += self.radius_growth
                if self.circle_radius >= self.max_radius:
                    self.growing = False
            else:
                self.circle_radius -= self.radius_growth
                if self.circle_radius <= self.min_radius:
                    self.growing = True

        # Convert frame to VideoFrame
        video_frame = VideoFrame.from_ndarray(frame, format='bgr24')
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        if len(self.frames) == 0:
            video_frame = self.animate_frame(pts, time_base)
        else:
            # Set video_frame to the last element
            video_frame = self.frames[-1]
            # Keep only the last element in the array
            self.frames = [self.frames[-1]]
            # Stamp timing here since processed frames are pushed asynchronously
            video_frame.pts = pts
            video_frame.time_base = time_base

        mediasoup_save_input_and_output = mediasoupSettings.get_setting("mediasoup_save_input_and_output")
        if mediasoup_save_input_and_output:
            # Save the video_frame image once per second
            current_time = time.time()
            if int(current_time) != self.last_saved_time and len(self.frames) > 0:
                timestamp = int(current_time)
                # Extract the image from the VideoFrame
                img = video_frame.to_ndarray(format='bgr24')
                filename = f"out_{timestamp}.jpg"
                filepath = os.path.join(self.save_dir, filename)
                cv2.imwrite(filepath, img)
                print(f"Saved {filepath}")
                self.last_saved_time = int(current_time)

        return video_frame


class FPSPrinter:
    def __init__(self, message):
        self.previous_time = None
        self.frame_times = []
        self.message = message

    async def print_fps(self):
        current_time = time.time()
        if self.previous_time is not None:
            time_diff = current_time - self.previous_time
            self.frame_times.append(time_diff)

            # Keep only the last 30 frame times
            if len(self.frame_times) > 30:
                self.frame_times.pop(0)

            fps = 1 / (sum(self.frame_times) / len(self.frame_times))
            print(f"{self.message}, Current FPS: {fps:.2f}")

        self.previous_time = current_time  # Update the previous time


class IncommingVideoProcessor:
    def __init__(self, add_frame_callback_fnc, width, height, vision_matcher_base_url, loop=None, token="", rd="", d="", q="", lang="es"):
        self.width = width
        self.height = height
        number_of_gestures_to_request = 2
        self.asyncio_loop = loop

        self.done = False #TODO: when done is True, the connecction should be closed
        self.pictures = []
        self.add_frame_callback_fnc = add_frame_callback_fnc

        #self.livenessProcessor = LivenessDetector(
        #    asyncio_loop=loop,
        #    verification_token=token,
        #    rd=rd,
        #    d=d,
        #    q=q,
        #    lang=lang,
        #    number_of_gestures_to_request=number_of_gestures_to_request,
        #    vision_matcher_base_url=vision_matcher_base_url

        mm_settings = generate_mm_settings(rd, d, q)
        self.mediaManager = MediaManager(mm_settings)
        self.vision_matcher_base_url = vision_matcher_base_url
        self.verification_token = token

        self.liveness_server_client = GestureServerClient(
            language=lang,
            socket_path=f"/tmp/mysocket_{token}",
            num_gestures=number_of_gestures_to_request,
            gestures_list=["blink", "smile", "openCloseMouth"], # Just for compability for now
            glasses_detector_mode = "WARNING_ONLY", # Use glasses detector
        )

        # Set the callback functions
        self.liveness_server_client.set_report_alive_callback(self.report_alive_callback)

        # NEW: receive processed frames asynchronously and forward to the outgoing track
        def image_callback(processed_bgr):
            try:
                # Convert to VideoFrame and push to the outgoing track
                vf = VideoFrame.from_ndarray(processed_bgr, format="bgr24")
                # pts/time_base will be stamped by OutgoingVideoStreamTrack.recv
                self.add_frame_callback_fnc(vf)
            except Exception as e:
                logger.error(f"image_callback error: {e}")

        self.liveness_server_client.set_image_callback(image_callback)

        # UPDATED: take_picture callback uses ONLY server-provided frame
        def take_picture_callback(take_picture, frame):
            if not take_picture:
                return
            if frame is None:
                # Server did not include an image; ignore (no local fallback).
                logger.warning("take_picture signaled but server provided no frame; ignoring.")
                return
            # Use only the server-provided image
            self.pictures.append(frame.copy())
            logger.debug("Take picture: stored server-provided frame")

        self.liveness_server_client.set_take_picture_callback(take_picture_callback)

        # start the liveness server
        self.liveness_server_client.start_server()

        self.last_saved_time = 0
        self.save_dir = 'saved_images_temp'
        # Ensure the directory exists
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)

    def report_alive_callback(self, alive):
        if (alive):
            logger.debug("The person is alive")
            self._compare_local_pictures_with_reference()
        else:
            logger.debug("The person is not alive")
            #self.gestures_requester.set_overwrite_text(
            #    self.translator.translate("error.not_verified"),
            #    True
            #)
            try:
                self.mediaManager.failure(
                    self.verification_token,
                    callback = lambda: setattr(self, 'done', True)
                )
            except Exception as e:
                logger.error("Error occurred:", str(e))
                #self.gestures_requester.set_overwrite_text(
                #    self.translator.translate("error.failure_report_error"),
                #    True
                #)

        print(f"Callback: The Person is {'alive' if alive else 'not alive'}.")
        self.done = True
        print(f"Is this done: {self.is_this_done()}")

    def process_frame(self, i_frame):
        if self.add_frame_callback_fnc is not None:
            # time_base = i_frame.time_base
            # pts = i_frame.pts
            img = i_frame.to_ndarray(format="bgr24")

            mediasoup_rotate_input_image = mediasoupSettings.get_setting("mediasoup_rotate_input_image")
            if mediasoup_rotate_input_image==90:
                # Rotate the image 90 degrees
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            elif mediasoup_rotate_input_image==-90:
                # Rotate the image -90 degrees
                img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

            mediasoup_flip_input_image = mediasoupSettings.get_setting("mediasoup_flip_input_image")
            if mediasoup_flip_input_image:
                # Flip the image along the vertical axis
                img = cv2.flip(img, 1)

            #img_out = self.livenessProcessor.process_image(img)
            # SEND ONLY: responses will arrive via image_callback
            self.liveness_server_client.process_frame(img)

            mediasoup_save_input_and_output = mediasoupSettings.get_setting("mediasoup_save_input_and_output")
            if mediasoup_save_input_and_output:
                # Save the original image once every second
                current_time = time.time()
                if int(current_time) != self.last_saved_time:
                    timestamp = int(current_time)
                    # Construct the full file path for saving
                    filename = f"in_{timestamp}.jpg"
                    filepath = os.path.join(self.save_dir, filename)
                    cv2.imwrite(filepath, img)
                    print(f"Saved {filepath}")
                    self.last_saved_time = int(current_time)

            # Do NOT convert to VideoFrame or push here; the image_callback does it

    def is_this_done(self):
        return self.done

    def _compare_local_pictures_with_reference(self):
        return self.asyncio_loop.create_task(self._async_compare_local_pictures_with_reference())

    async def _async_compare_local_pictures_with_reference(self):
        try:    
            #self.gestures_requester.set_overwrite_text(
            #    self.translator.translate("message.getting_reference_images")
            #)

            # Ensure downloaded_images path exists
            os.makedirs("./downloaded_images", exist_ok=True)

            ret = await self.mediaManager.download_images_from_token(
                self.verification_token,
                "./downloaded_images"
            )
            reference_images = ret["downloaded_images"]
            if ret["status"] == "error":
                logger.debug("Error getting reference images: %s", ret["msj"])
                #self.gestures_requester.set_overwrite_text(ret["msj"], True)
            else:
                logger.debug("Reference images downloaded successfully")
                #self.gestures_requester.set_overwrite_text(
                #    self.translator.translate("message.done")
                #)
        except Exception as e:
            # Handle the exception here
            logger.error("Exception...Error getting reference images:", str(e))
            #self.gestures_requester.set_overwrite_text(
            #    self.translator.translate("error.getting_reference_images"), 
            #    True
            #)
            reference_images = []

        if len(reference_images) > 0:
            logger.debug("reference images: %s", reference_images)
            distances = []
            for reference_image_path in reference_images:
                reference_image = cv2.imread(reference_image_path)
                p_index = 0
                for picture in self.pictures:
                    p_index += 1
                    try:
                        logger.debug('picture: %s', picture.shape)
                        #faces = await find_face(picture)
                        #if (len(faces) == 1):
                        #    logger.debug("The picture meets the criteria for an acceptable face match.")            
                        #else:
                        #    logger.debug("The picture doesn't meet the criteria for an acceptable face match.")
                        #    self.gestures_requester.set_overwrite_text(
                        #        self.translator.translate("message.doing_face_match") + " (" + 
                        #        str(p_index) + 
                        #        " " + self.translator.translate("message.of") + " " +
                        #        str(len(self.pictures)) + 
                        #        "). " + 
                        #        self.translator.translate("error.does_not_meet_criteria_for_acceptable_face_match")
                        #    )
                        #self.gestures_requester.set_overwrite_text(
                        #    self.translator.translate("message.doing_face_match") + " (" + 
                        #    str(p_index) + 
                        #    " " + self.translator.translate("message.of") + " " +
                        #    str(len(self.pictures)) + 
                        #    "). "
                        #)
                        result = await self._async_face_match(picture, reference_image)
                        logger.debug('face match result: %s', result)
                        distances.append(result['distance'])
                    except Exception as e:
                        # Handle the exception here
                        logger.error("Error occurred in face match: %s", str(e))
                        #self.gestures_requester.set_overwrite_text(
                        #    self.translator.translate("error.error_doing_face_match"), 
                        #    True
                        #)
                #TODO: Comment this line to avoid deleting the reference images
                os.remove(reference_image_path)

            total_distance = sum(distances)
            if len(distances) == 0:
                average_distance = 1
            else:
                average_distance = total_distance / len(distances)
            logger.debug('Average distance: %f', average_distance)
            if average_distance < 0.4:
                logger.debug("Verified!!")
                #self.gestures_requester.set_overwrite_text(
                #    self.translator.translate("message.verified")
                #)
                #self.gestures_requester.process_status = GesturesRequesterSystemStatus.DONE
                try:
                    self.mediaManager.success(
                        self.verification_token,
                        callback = lambda: setattr(self, 'done', True)
                    )
                except Exception as e:
                    # Handle the exception here
                    logger.error("Error occurred sending success: %s", str(e))
                    #self.gestures_requester.set_overwrite_text(
                    #    self.translator.translate("error.success_report"), 
                    #    True
                    #)
            else:
                logger.debug("Not Verified!!!")
                #self.gestures_requester.set_overwrite_text(
                #    self.translator.translate("error.not_verified"), 
                #    True
                #)
                try:
                    self.mediaManager.failure(
                        self.verification_token,
                        callback = lambda: setattr(self, 'done', True)
                    )
                except Exception as e:
                    # Handle the exception here
                    logger.error("Error occurred sending failure: %s", str(e))
                    #self.gestures_requester.set_overwrite_text(
                    #    self.translator.translate("error.failure_report_error"), 
                    #    True
                    #)
        else:
            logger.debug("No reference images found, not Verified!!!")
            #self.gestures_requester.set_overwrite_text(
            #    self.translator.translate("error.no_reference_images") + 
            #    ", " + 
            #    self.translator.translate("error.not_verified"), 
            #    True
            #)
            try:
                self.mediaManager.failure(
                    self.verification_token,
                    callback = lambda: setattr(self, 'done', True)
                )
            except Exception as e:
                # Handle the exception here
                logger.error("Error occurred sending failure (2): %s", str(e))
                #self.gestures_requester.set_overwrite_text(
                #    self.translator.translate("error.failure_report_error"), 
                #    True
                #)

    async def _async_face_match(self, image1, image2):
        matcher_save_match_images = mediasoupSettings.get_setting("matcher_save_match_images")
        if matcher_save_match_images:
            IMAGE_DIR = 'saved_images_temp'
            if not os.path.exists(IMAGE_DIR):
                os.makedirs(IMAGE_DIR)

            # Generate a timestamp
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

            # Save image1
            image1_filename = os.path.join(IMAGE_DIR, f"match_{self.match_counter}_{timestamp}_image1.jpg")
            cv2.imwrite(image1_filename, image1)

            # Save image2
            image2_filename = os.path.join(IMAGE_DIR, f"match_{self.match_counter}_{timestamp}_image2.jpg")
            cv2.imwrite(image2_filename, image2)
            print(f"Images saved as {image1_filename} and {image2_filename}")            

        # Call Face matcher
        # Convert image1 and image2 to DATA URLs
        import base64
        import aiohttp

        # Encode the image to PNG format (you can also use JPEG or other formats)
        _, buffer1 = cv2.imencode('.jpg', image1)
        _, buffer2 = cv2.imencode('.jpg', image2)

        # Create the data URL
        image1_url = f"data:image/jpeg;base64,{base64.b64encode(buffer1.tobytes()).decode('utf-8')}"
        image2_url = f"data:image/jpeg;base64,{base64.b64encode(buffer2.tobytes()).decode('utf-8')}"

        face_match_url = f"{self.vision_matcher_base_url}/face_match"

        headers = {
            'Content-Type': 'application/json',
        }
        body = {
            'image1_url': image1_url,
            'image2_url': image2_url,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(face_match_url, headers=headers, json=body) as response:
                logger.debug("response status: %s", response.status)
                logger.debug("response value: %s", await response.json())

        return await response.json()

    def __del__(self):
        self.liveness_server_client.stop_server()

async def my_incoming_video_consume(track, video_processor):
    #fps_printer = FPSPrinter("My incoming video consume")

    while True:
        try:
            frame = await track.recv()
            if track.kind == "video":
                #await fps_printer.print_fps()
                video_processor.process_frame(frame)
        except Exception as e:
            print(f"An error occurred: {e}")
            return


class MyMediaIncomeVideoConsume:
    def __init__(self, vision_matcher_base_url, add_frame_callback_fnc=None, loop=None, token="", rd="", d="", q="", lang="es"):
        self.__video_track = None
        self.add_frame_callback_fnc = add_frame_callback_fnc
        self.loop = loop
        self.token = token
        self.rd = rd
        self.d = d
        self.q = q
        self.lang = lang

        # Create a single video processor for all video tracks
        self.video_processor = IncommingVideoProcessor(
            add_frame_callback_fnc=self.add_frame_callback_fnc,
            width=640,
            height=480,
            vision_matcher_base_url=vision_matcher_base_url,
            loop=self.loop,
            token=self.token,
            rd=self.rd,
            d=self.d,
            q=self.q,
            lang=self.lang
        )

    def addTrack(self, track):
        # Only add the first video track and skip all others
        if track.kind == "video" and self.__video_track is None:
            self.__video_track = track
        else:
            print(f"Ignoring track of type: {track.kind}")

    async def start(self):
        if self.__video_track is not None:
            # Only process the first video track
            asyncio.ensure_future(my_incoming_video_consume(
                self.__video_track,
                video_processor=self.video_processor 
            ))

    def get_video_processor(self):
        return self.video_processor

    def cleanup(self):
        # Cleanup logic
        if self.video_processor and self.video_processor.liveness_server_client:
            # Ensure the server is stopped when cleaning up
            self.video_processor.liveness_server_client.stop_server()
            self.video_processor = None

    def __del__(self):
        logger.debug("MyMediaIncomeVideoConsume Destroyed")
        self.cleanup()

    async def stop(self):
        """
        Stop consuming the media.
        """
        if self.__video_track is not None:
            self.__video_track = None

        # Cleanup processor
        if self.video_processor and self.video_processor.liveness_server_client:
            # Stop the server client properly
            self.video_processor.liveness_server_client.stop_server()
            self.video_processor = None


T = TypeVar("T")


class MobieraMediaSoupClient:
    def __init__(self, uri, vision_matcher_base_url, loop=None, token="", rd="", d="", q="", lang="es", use_ice_relay=False):

        self.use_ice_relay = use_ice_relay
        if not loop:
            if sys.version_info.major == 3 and sys.version_info.minor == 6:
                loop = asyncio.get_event_loop()
            else:
                loop = asyncio.get_running_loop()
        self._loop = loop
        self._uri = uri
        self._answers: Dict[str, Future] = {}
        self._websocket = None
        self._device = None

        self._tracks = []

        # Use the custom video track with animation
        videoTrack = OutgoingVideoStreamTrack()
        self._recorder = MyMediaIncomeVideoConsume(vision_matcher_base_url=vision_matcher_base_url,
            add_frame_callback_fnc=videoTrack.add_frame, loop=loop, token=token, rd=rd, d=d, q=q, lang=lang)
        self._videoTrack = videoTrack

        self._tracks.append(videoTrack)

        self._sendTransport: Optional[Transport] = None
        self._recvTransport: Optional[Transport] = None

        self._producers = []
        self._consumers = []
        self._tasks = []
        self._closed = False

    # verify if the liveness detector is done
    async def liveness_detector_done_task(self):
        done = False
        counter = 0 # Counter for timeout (the identification shoudn't take more thatn 1 minute)
        while done==False:
            await asyncio.sleep(1.0)
            done = self._recorder.get_video_processor().is_this_done()
            print(f"-------> Liveness Detector Done: {done}")
            counter+=1
            if counter > 60:
                done=True

    # websocket receive task
    async def recv_msg_task(self):
        while True:
            await asyncio.sleep(0.5)
            if self._websocket is not None:
                message = json.loads(await self._websocket.recv())
                if message.get("response"):
                    if message.get("id") is not None:
                        self._answers[message.get("id")].set_result(message)
                elif message.get("request"):
                    if message.get("method") == "newConsumer":
                        await self.consume(
                            id=message["data"]["id"],
                            producerId=message["data"]["producerId"],
                            kind=message["data"]["kind"],
                            rtpParameters=message["data"]["rtpParameters"],
                        )
                        response = {
                            "response": True,
                            "id": message["id"],
                            "ok": True,
                            "data": {},
                        }
                        await self._websocket.send(json.dumps(response))
                    elif message.get("method") == "newDataConsumer":
                        await self.consumeData(
                            id=message["data"]["id"],
                            dataProducerId=message["data"]["dataProducerId"],
                            label=message["data"]["label"],
                            protocol=message["data"]["protocol"],
                            sctpStreamParameters=message["data"][
                                "sctpStreamParameters"
                            ],
                        )
                        response = {
                            "response": True,
                            "id": message["data"]["id"],
                            "ok": True,
                            "data": {},
                        }
                        await self._websocket.send(json.dumps(response))
                # elif message.get("notification"):
                    # print("message:", message)

    # wait for answer ready
    async def _wait_for(
        self, fut: Awaitable[T], timeout: Optional[float], **kwargs: Any
    ) -> T:
        try:
            return await asyncio.wait_for(fut, timeout=timeout, **kwargs)
        except asyncio.TimeoutError:
            raise Exception("Operation timed out")

    async def _send_request(self, request):
        self._answers[request["id"]] = self._loop.create_future()
        await self._websocket.send(json.dumps(request))

    # Generates a random positive integer.
    def generateRandomNumber(self) -> int:
        return round(random() * 10000000)

    async def run(self):
        self._websocket = await websockets.connect(self._uri, subprotocols=["protoo"])

        task_run_recv_msg = asyncio.create_task(self.recv_msg_task())
        self._tasks.append(task_run_recv_msg)
        # Task to verify if the liveness detector ended
        task_run_liveness_detector_done = asyncio.create_task(self.liveness_detector_done_task())
        self._tasks.append(task_run_liveness_detector_done)

        await self.load()
        await self.createSendTransport()
        await self.createRecvTransport()
        await self.produce()
        print("###################################################################")
        #await task_run_recv_msg
        await task_run_liveness_detector_done

    async def load(self):
        # Init device
        self._device = Device(
            handlerFactory=AiortcHandler.createFactory(tracks=self._tracks)
        )

        # Get Router RtpCapabilities
        reqId = self.generateRandomNumber()
        req = {
            "request": True,
            "id": reqId,
            "method": "getRouterRtpCapabilities",
            "data": {},
        }
        await self._send_request(req)
        ans = await self._wait_for(self._answers[reqId], timeout=15)
        print("##########################################################################")
        print("##########################################################################")
        print("##########################################################################")
        print("##########################################################################")
        print("########################### ROUTER RTP CAPABILITIES ######################")
        print(json.dumps(ans["data"], indent=4))
        print("##########################################################################")
        print("##########################################################################")
        print("##########################################################################")
        print("##########################################################################")

        remove_urn_3gpp_video_orientation = mediasoupSettings.get_setting("remove_urn_3gpp_video_orientation")
        if remove_urn_3gpp_video_orientation:
            header_extensions = ans["data"].get("headerExtensions", [])
            # Filter the header extensions
            filtered_header_extensions = [
                ext for ext in header_extensions if ext['uri'] != 'urn:3gpp:video-orientation'
            ]
            # Update the 'headerExtensions' with the filtered list
            ans["data"]["headerExtensions"] = filtered_header_extensions

        # Load Router RtpCapabilities
        await self._device.load(ans["data"])

    async def createSendTransport(self):
        if self._sendTransport is not None:
            return
        # Send create sendTransport request
        reqId = self.generateRandomNumber()
        req = {
            "request": True,
            "id": reqId,
            "method": "createWebRtcTransport",
            "data": {
                "forceTcp": False,
                "producing": True,
                "consuming": False,
                "sctpCapabilities": self._device.sctpCapabilities.dict(),
            },
        }
        await self._send_request(req)
        ans = await self._wait_for(self._answers[reqId], timeout=15)

        transport_params = {
            "id": ans["data"]["id"],
            "iceParameters": ans["data"]["iceParameters"],
            "iceCandidates": ans["data"]["iceCandidates"],
            "dtlsParameters": ans["data"]["dtlsParameters"],
            "sctpParameters": ans["data"]["sctpParameters"]
        }

        iceServers = ans["data"].get("iceServers", None)
        if iceServers is not None:
            transport_params["iceServers"] = iceServers
            if self.use_ice_relay:
                transport_params["iceTransportPolicy"] = 'relay'

        self._sendTransport = self._device.createSendTransport(**transport_params)

        @self._sendTransport.on("connect")
        async def on_connect(dtlsParameters):
            reqId = self.generateRandomNumber()
            req = {
                "request": True,
                "id": reqId,
                "method": "connectWebRtcTransport",
                "data": {
                    "transportId": self._sendTransport.id,
                    "dtlsParameters": dtlsParameters.dict(exclude_none=True),
                },
            }
            await self._send_request(req)
            ans = await self._wait_for(self._answers[reqId], timeout=15)
            print("on_connect:", ans)

        @self._sendTransport.on("produce")
        async def on_produce(kind: str, rtpParameters, appData: dict):
            reqId = self.generateRandomNumber()
            req = {
                "id": reqId,
                "method": "produce",
                "request": True,
                "data": {
                    "transportId": self._sendTransport.id,
                    "kind": kind,
                    "rtpParameters": rtpParameters.dict(exclude_none=True),
                    "appData": appData,
                },
            }
            await self._send_request(req)
            ans = await self._wait_for(self._answers[reqId], timeout=15)
            return ans["data"]["id"]

        @self._sendTransport.on("producedata")
        async def on_producedata(
            sctpStreamParameters: SctpStreamParameters,
            label: str,
            protocol: str,
            appData: dict,
        ):

            reqId = self.generateRandomNumber()
            req = {
                "id": reqId,
                "method": "produceData",
                "request": True,
                "data": {
                    "transportId": self._sendTransport.id,
                    "label": label,
                    "protocol": protocol,
                    "sctpStreamParameters": sctpStreamParameters.dict(
                        exclude_none=True
                    ),
                    "appData": appData,
                },
            }
            await self._send_request(req)
            ans = await self._wait_for(self._answers[reqId], timeout=15)
            return ans["data"]["id"]

    async def produce(self):
        if self._sendTransport is None:
            await self.createSendTransport()

        # Join room
        reqId = self.generateRandomNumber()
        req = {
            "request": True,
            "id": reqId,
            "method": "join",
            "data": {
                "displayName": "pymediasoup",
                "device": {"flag": "python", "name": "python", "version": "0.1.0"},
                "rtpCapabilities": self._device.rtpCapabilities.dict(exclude_none=True),
                "sctpCapabilities": self._device.sctpCapabilities.dict(
                    exclude_none=True
                ),
            },
        }
        await self._send_request(req)
        ans = await self._wait_for(self._answers[reqId], timeout=15)
        print("produce:", ans)

        # produce
        videoProducer: Producer = await self._sendTransport.produce(
            track=self._videoTrack, stopTracks=False, appData={}
        )
        self._producers.append(videoProducer)

        # produce data
        # await self.produceData()

    async def produceData(self):
        if self._sendTransport is None:
            await self.createSendTransport()

        dataProducer: DataProducer = await self._sendTransport.produceData(
            ordered=False,
            maxPacketLifeTime=5555,
            label="chat",
            protocol="",
            appData={"info": "my-chat-DataProducer"},
        )
        self._producers.append(dataProducer)
        while not self._closed:
            await asyncio.sleep(1)
            # dataProducer.send("hello")

    async def createRecvTransport(self):
        if self._recvTransport is not None:
            return
        # Send create recvTransport request
        reqId = self.generateRandomNumber()
        req = {
            "request": True,
            "id": reqId,
            "method": "createWebRtcTransport",
            "data": {
                "forceTcp": False,
                "producing": False,
                "consuming": True,
                "sctpCapabilities": self._device.sctpCapabilities.dict(),
            },
        }
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(">>>>>>>>>>>>>>>>> CREATE RECV TRANSPOIRT>>>>>>>>>>>>>>>>>>>>")
        print(req)
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")

        await self._send_request(req)
        ans = await self._wait_for(self._answers[reqId], timeout=15)

        transport_params = {
            "id": ans["data"]["id"],
            "iceParameters": ans["data"]["iceParameters"],
            "iceCandidates": ans["data"]["iceCandidates"],
            "dtlsParameters": ans["data"]["dtlsParameters"],
            "sctpParameters": ans["data"]["sctpParameters"]
        }

        iceServers = ans["data"].get("iceServers", None)
        if iceServers is not None:
            transport_params["iceServers"] = iceServers
            if self.use_ice_relay:
                transport_params["iceTransportPolicy"] = 'relay'

        self._recvTransport = self._device.createRecvTransport(**transport_params)

        @self._recvTransport.on("connect")
        async def on_connect(dtlsParameters):
            reqId = self.generateRandomNumber()
            req = {
                "request": True,
                "id": reqId,
                "method": "connectWebRtcTransport",
                "data": {
                    "transportId": self._recvTransport.id,
                    "dtlsParameters": dtlsParameters.dict(exclude_none=True),
                },
            }
            await self._send_request(req)
            ans = await self._wait_for(self._answers[reqId], timeout=15)
            print("rcv_on_connect:", ans)

    async def consume(self, id, producerId, kind, rtpParameters):
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(">>>>>>>>>>>>>>>>>>>>>>>>>> CONSUME >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(f"kind: {kind}")
        print(rtpParameters)
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        if self._recvTransport is None:
            await self.createRecvTransport()
        consumer: Consumer = await self._recvTransport.consume(
            id=id, producerId=producerId, kind=kind, rtpParameters=rtpParameters
        )
        self._consumers.append(consumer)
        self._recorder.addTrack(consumer.track)
        await self._recorder.start()

    async def consumeData(
        self,
        id,
        dataProducerId,
        sctpStreamParameters,
        label=None,
        protocol=None,
        appData={},
    ):
        pass
        dataConsumer: DataConsumer = await self._recvTransport.consumeData(
            id=id,
            dataProducerId=dataProducerId,
            sctpStreamParameters=sctpStreamParameters,
            label=label,
            protocol=protocol,
            appData=appData,
        )
        self._consumers.append(dataConsumer)

        @dataConsumer.on("message")
        def on_message(message):
            print(f"DataChannel {label}-{protocol}: {message}")

    async def close(self):
        for consumer in self._consumers:
            print("################### Closing Consumer")
            await consumer.close()
        for producer in self._producers:
            print("################### Closing Producer")
            await producer.close()
        for task in self._tasks:
            print("################### Closing Task")
            task.cancel()
        if self._sendTransport:
            print("################### Closing Send Transport")
            await self._sendTransport.close()
        if self._recvTransport:
            print("################### Closing Recv Transport")
            await self._recvTransport.close()

        print("################### Closing Socket")
        await self._websocket.close()
        print("################### Closing Recorder")
        await self._recorder.stop()
        print("################### Close Done")

    async def leaveRoom(self):
        try:
            print('**** Initialize leaveRoom method ****')
            # Generate a unique request ID
            reqId = self.generateRandomNumber()

            # Create the leaveCall request
            req = {
                "request": True,
                "id": reqId,
                "method": "leaveRoom",
                "data": {}
            }

            # Send the request to the server
            await self._send_request(req)

            # Wait for the server response
            ans = await self._wait_for(self._answers[reqId], timeout=15)

            await self._websocket.close()

        except Exception as e:
            print(f"Error in leaveRoom: {e}")



async def runMediasoupClientTask(uri, vision_matcher_base_url, loop, token, d, q, lang, use_ice_relay=False):
    demo = MobieraMediaSoupClient(
        uri=uri, vision_matcher_base_url=vision_matcher_base_url, loop=loop, token=token, rd="", d=d, q=q, lang = lang, use_ice_relay=use_ice_relay)
    logger.debug("PASS1")
    await loop.create_task(demo.run())
    print("################################## DONE >>>>>>>>>>>>>>>>>>>>>>>>>>><")
    await loop.create_task(asyncio.sleep(3))
    print("################################## Closing...")
    await loop.create_task(demo.leaveRoom())
    print("################################## Closing...DONE")
    demo = None

async def connectToMediasoupServer(vision_matcher_base_url, request):
    """
    Asynchronously handles connecting to a Mediasoup server, using parameters provided in the HTTP request.

    This function receives an HTTP request that includes 'roomid', 'token', 'rd', 'd', and 'q' as query parameters.
    It generates a unique 'peerId' and constructs a WebSocket URI to connect to the Mediasoup server.
    An instance of MobieraMediaSoupClient is created and its 'run' method is executed in the event loop.

    Args:
        request (aiohttp.web.Request): The request instance containing query parameters necessary for the connection.

    Returns:
        aiohttp.web.Response: An HTTP response object. The response will have a status of 200 if the connection
                              was successful, or 500 if there was an error.

    Raise:
       Exception: In case of any general error during the execution, returns an HTTP response with status code 500.
    """
    logger.debug("connectToMediasoupServer")
    try:
         # Parse the JSON body
        data = await request.json()
        # Extract parameters from the JSON body
        full_url = data.get('ws_url')
        d = data.get('datastore_base_url')
        q = data.get('callback_base_url')
        token = data.get('token')
        lang = data.get('lang')

        logger.debug(f"fullurl:{full_url}")
        logger.debug(f"d:{d}")
        logger.debug(f"q:{q}")
        logger.debug(f"token:{token}")
        logger.debug(f"lang:{lang}")

        use_mediasoup_ice_relay_str = os.environ.get("USE_MEDIASOUP_ICE_RELAY", "false")
        use_mediasoup_ice_relay = bool(strtobool(use_mediasoup_ice_relay_str))
        logger.debug(f"use_mediasoup_ice_relay:{use_mediasoup_ice_relay}")

        if full_url:
            uri = full_url

        # run event loop
        loop = None
        if sys.version_info.major == 3 and sys.version_info.minor == 6:
            loop = asyncio.get_event_loop()
        else:
            loop = asyncio.get_running_loop()
        logger.debug("Getted the loop:" + str(loop))
        logger.debug("uri:" + uri)

        # Run in another task
        loop.create_task(runMediasoupClientTask(uri, vision_matcher_base_url, loop, token, d, q, lang, use_mediasoup_ice_relay))

        textobj = {
            "msj": f'Successfully connected:',
            "mm_response": ""
        }
        status = 200
        return web.Response(text=json.dumps(textobj), status=status)
    except Exception as e:
        error_traceback = traceback.format_exc()
        textobj = {
            "msj": f'Error connecting to Mediasoup Server:',
            "error_response": str(e),
            "traceback": error_traceback
        }
        return web.Response(text=json.dumps(textobj), status=500)