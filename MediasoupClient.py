import os
from distutils.util import strtobool
from aiohttp import web
import sys
import json
import asyncio
import argparse
import secrets
from typing import Optional, Dict, Awaitable, Any, TypeVar
from asyncio.futures import Future
import mediasoupSettings

from pymediasoup import Device
from pymediasoup import AiortcHandler
from pymediasoup.transport import Transport
from pymediasoup.consumer import Consumer
from pymediasoup.producer import Producer
from pymediasoup.data_consumer import DataConsumer
from pymediasoup.data_producer import DataProducer
from pymediasoup.sctp_parameters import SctpStreamParameters

#from livenessDetector.LivenessDetector import LivenessDetector
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


class OutgoingVideoStreamTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.width = 640
        self.height = 480
        self.square_size = 50
        self.velocity = 5
        self.x_pos = 0
        self.y_pos = 0
        self.direction_x = 1
        self.direction_y = 1
        self.frames = []

        self.last_saved_time = 0
        self.save_dir = 'saved_images_temp'
        # Ensure the directory exists
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)        

    def add_frame(self, frame):
        self.frames.append(frame)

    def animate_frame(self, pts, time_base):
        # Create a blank frame
        frame = np.zeros((self.height, self.width, 3), np.uint8)

        # Draw a square
        cv2.rectangle(frame, (self.x_pos, self.y_pos),
                      (self.x_pos + self.square_size,
                       self.y_pos + self.square_size),
                      (0, 255, 0), -1)

        # Update square position for x
        self.x_pos += self.velocity * self.direction_x
        if self.x_pos < 0 or self.x_pos + self.square_size > self.width:
            self.direction_x = -self.direction_x
            self.x_pos += self.velocity * self.direction_x

        # Update square position for y
        self.y_pos += self.velocity * self.direction_y
        if self.y_pos < 0 or self.y_pos + self.square_size > self.height:
            self.direction_y = -self.direction_y
            self.y_pos += self.velocity * self.direction_y

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
    def __init__(self, add_frame_callback_fnc, width, height, loop=None, token="", rd="", d="", q="", lang="es"):
        self.width = width
        self.height = height
        number_of_gestures_to_request = 2

        self.add_frame_callback_fnc = add_frame_callback_fnc
                
        #self.livenessProcessor = LivenessDetector(
        #    loop,
        #    token,
        #    rd,
        #    d,
        #    q,
        #    lang,
        #    number_of_gestures_to_request
        #)
        self.liveness_server_client = GestureServerClient(
            server_executable_path="/Users/diegoaguilar/pruebas/mediapipe_mac/mediapipe/bazel-bin/livenessDetectorServerApp/livenessDetectorServer",
            model_path="/Users/diegoaguilar/Downloads/face_landmarker.task",
            gestures_folder_path="/Users/diegoaguilar/pruebas/mediapipe_mac/mediapipe/livenessDetectorServerApp/gestures",
            language="en",
            socket_path="/tmp/mysocket",
            num_gestures=2
        )

        # Set the callback functions
        self.liveness_server_client.set_report_alive_callback(self.report_alive_callback)

        self.last_saved_time = 0
        self.save_dir = 'saved_images_temp'
        # Ensure the directory exists
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
        

    def process_frame(self, i_frame):
        if self.add_frame_callback_fnc is not None:
            time_base = i_frame.time_base
            pts = i_frame.pts
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
            img_out = self.liveness_server_client.process_frame(img)

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

            # Convert frame to VideoFrame
            video_frame = VideoFrame.from_ndarray(img_out, format='bgr24')
            video_frame.pts = pts
            video_frame.time_base = time_base
            self.add_frame_callback_fnc(video_frame)

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
    def __init__(self, add_frame_callback_fnc=None, loop=None, token="", rd="", d="", q="", lang="es"):
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
            self.add_frame_callback_fnc,
            640,
            480,
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

    def get_liveness_processor(self):
        return self.video_processor.livenessProcessor

    def cleanup(self):
        # Cleanup logic
        if self.video_processor and self.video_processor.livenessProcessor:
            self.video_processor.livenessProcessor.cleanup()
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
        if self.video_processor and self.video_processor.livenessProcessor:
            self.video_processor.livenessProcessor.cleanup()
            self.video_processor = None


T = TypeVar("T")


class MobieraMediaSoupClient:
    def __init__(self, uri, loop=None, token="", rd="", d="", q="", lang="es", use_ice_relay=False):

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
        self._recorder = MyMediaIncomeVideoConsume(
            videoTrack.add_frame, loop=loop, token=token, rd=rd, d=d, q=q, lang=lang)
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
            done = self._recorder.get_liveness_processor().is_this_done()
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



async def runMediasoupClientTask(uri, loop, token, d, q, lang, use_ice_relay=False):
    demo = MobieraMediaSoupClient(
        uri=uri, loop=loop, token=token, rd="", d=d, q=q, lang = lang, use_ice_relay=use_ice_relay)
    logger.debug("PASS1")
    await loop.create_task(demo.run())
    print("################################## DONE >>>>>>>>>>>>>>>>>>>>>>>>>>><")
    await loop.create_task(asyncio.sleep(3))
    print("################################## Closing...")
    await loop.create_task(demo.leaveRoom())
    print("################################## Closing...DONE")
    demo = None

async def connectToMediasoupServer(request):
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
        loop.create_task(runMediasoupClientTask(uri, loop, token, d, q, lang, use_mediasoup_ice_relay))

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
