import os
import asyncio
from livenessDetector.FaceProcessor import FaceProcessor
from livenessDetector.GestureDetector import GestureDetector
from livenessDetector.GesturesRequester import GesturesRequester, GesturesRequesterSystemStatus
from livenessDetector.liveness_detector_face_config import FaceConfig
from imagesComparator.imageFinder import find_face, FaceGlassesDetector
from mediaManager.MediaManagerSettings import generate_mm_settings
from mediaManager.MediaManager import MediaManager
from imagesComparator.imageFinder import FaceGlassesDetector
from livenessDetector.tranlationManager import TranslationManager
import threading
from deepface import DeepFace
import cv2
import logging
import mediasoupSettings
from datetime import datetime

# Get the logger for this module
logger = logging.getLogger(__name__)

#############################################################
# UTILITY FUNCTIONS
#############################################################
def drawValueOf(name, value, minValue, maxValue, maxCharacters, decimalPlaces):
    normalized_value = (value - minValue) / (maxValue - minValue)
    num_hashes = int(normalized_value * maxCharacters)
    if num_hashes > maxCharacters:
        num_hashes = maxCharacters
    result = '#' * num_hashes
    formatted_value = "{:.{}f}".format(value, decimalPlaces)  # Format value with specified number of decimal places
    return "{} {} {}".format(name, formatted_value, result)

#############################################################
# MAIN CLASS
#############################################################

class LivenessDetector:
    DEBUG_OFF = 0
    DEBUG_INFO = 1
    DEBUG_THREADING = 2

    def __init__(self, asyncio_loop, verification_token, rd, d, q, lang, number_of_gestures_to_request, debug_level=DEBUG_OFF):
        logger.debug("ASYNCIO LOOP: %s", asyncio_loop)
        self.translator = TranslationManager(locale=lang, locales_dir="./gestures/locales/")
        self.asyncio_loop = asyncio_loop
        self.verification_token = verification_token
        self.done = False
        self.debug_level = debug_level
        self.faceGlassesDetector = None
        self.glasses = False
        self.frames_counter = 0
        self.cfg = FaceConfig()
        if self.cfg.detect_glasses:
            self.faceGlassesDetector = FaceGlassesDetector("./imagesComparator/model.tflite")
        self.faceProcessor = FaceProcessor()
        self.faceProcessor.set_callback(
            self.face_processor_result_all_callback
        )
        self.gesture_detector = GestureDetector()
        self.gestures_requester = GesturesRequester(
            number_of_gestures_to_request, 
            self.gesture_detector,
            self.translator, 
            GesturesRequester.DEBUG_THREADING
        )
        self.gestures_requester.set_report_alive_callback(
            self.gestures_requester_result_callback
        )
        self.gestures_requester.set_ask_to_take_a_picture_callback(
            self.gestures_requester_take_a_picture_callback
        )

        mm_settings = generate_mm_settings(rd, d, q)
        self.mediaManager = MediaManager(mm_settings)
        
        self.gestures_list = []
        self.pictures = []
        self.take_a_picture = False

        self.face_square_normalized_points = {}

        gesture_files = [f for f in os.listdir('./gestures') if f.endswith('.json')]
        for file in gesture_files:
            logger.debug('Gesture file: %s', file)
            ret, gestureId, label, icon_path, total_recommended_max_time, take_picture_at_the_end = self.gesture_detector.add_gesture_from_file(f'./gestures/{file}')
            if not ret and self.debug_level >= self.DEBUG_INFO:
                logger.debug("!!!!!!!!!!!!!!!!!!!!!!!!!!!! %s gesture not added", file)    
            else:
                # Load the icon
                icon = cv2.imread(icon_path, -1)
                # If there is no alpha channel, add one
                if (icon is not None) and (icon.shape[2] == 3):
                    icon = cv2.cvtColor(icon, cv2.COLOR_BGR2BGRA)
          
                self.gestures_list.append(
                    {
                        "gestureId": gestureId,
                        "label": label, 
                        "icon_path": icon_path,
                        "icon": icon,
                        "total_recommended_max_time": total_recommended_max_time,
                        "take_picture_at_the_end": take_picture_at_the_end
                    }
                )
        self.gestures_requester.set_gestures_list(self.gestures_list)
        #DeepFace.build_model("VGG-Face")
        self.match_counter = 0

    def is_this_done(self):
        return self.done

    def cleanup(self):
        logger.debug("LivenessDetector Cleanup")
        self.faceProcessor.cleanup()
        del self.faceProcessor
        self.faceProcessor = None
        
        self.gesture_detector.cleanup()
        del self.gesture_detector
        self.gesture_detector = None
        
        self.gestures_requester.cleanup()
        del self.gestures_requester
        self.gestures_requester = None

        #if not self.task.done():
        #    self.task.cancel()
        #    self.task = None
    
    def __del__(self):
        logger.debug("LivenessDetector Destoyed")

    def process_image(self, img):
        self.frames_counter += 1
        height, width = img.shape[:2]
        if width > height:
            resized_img = cv2.resize(img, (640, int(640 * height / width)))
        else:
            resized_img = cv2.resize(img, (int(480 * width / height), 480))
        
        if self.cfg.detect_glasses and self.frames_counter % 30 == 0:
            self.glasses = self.faceGlassesDetector.find_glasses(resized_img)
        
        self.faceProcessor.process_image(resized_img)
        warning_text = self._verify_correct_face()
        img_out = self.gestures_requester.process_image(resized_img, self.cfg.show_face, self.face_square_normalized_points, warning_text)
        if self.take_a_picture:
            self.take_a_picture = False
            picture = resized_img.copy()
            self.pictures.append(picture)
        return img_out

    def face_processor_result_callback(self, blendshapes, transformationValues):
        logger.debug("Liveness Detector Thread>>>>>> %s", threading.current_thread().name)        
        
        if "Eye blikn Right" in blendshapes:
            self._debug_print(
                self.DEBUG_INFO,
                drawValueOf(name="Eye blikn Right  ", value=blendshapes["Eye blikn Right"], minValue=0, maxValue=0.8, maxCharacters=30, decimalPlaces=10)     
            )
            self.gesture_detector.process_signal(blendshapes["Eye blikn Right"], 2) 
        if "jaw Open" in blendshapes:
            self._debug_print(
                self.DEBUG_INFO,
                drawValueOf(name="jaw Open         ", value=blendshapes["jaw Open"], minValue=0, maxValue=0.8, maxCharacters=30, decimalPlaces=10) 
            )
            self.gesture_detector.process_signal(blendshapes["jaw Open"], 0) # jaw Open    
        if "Mouth Smile Right" in blendshapes:
            self._debug_print(
                self.DEBUG_INFO,
                drawValueOf(name="Mouth Smile Right", value=blendshapes["Mouth Smile Right"], minValue=0, maxValue=0.8, maxCharacters=30, decimalPlaces=10) 
            )
            self.gesture_detector.process_signal(blendshapes["Mouth Smile Right"], 1) # Mouth Smile Right
        if "Yaw" in transformationValues:
            self._debug_print(
                self.DEBUG_INFO,
                "YAW \u2190\u2192:"+ str(transformationValues["Yaw"])    
            )
            self.gesture_detector.process_signal(transformationValues["Yaw"], 3) 
        if "Pitch" in transformationValues:
            self._debug_print(
                self.DEBUG_INFO,
                "PITCH \u2191\u2193:" + str(transformationValues["Pitch"])  # Upwards arrow (represents PITCH)    
            )
            self.gesture_detector.process_signal(transformationValues["Pitch"], 4) 
        if "Roll" in transformationValues:
            self._debug_print(
                self.DEBUG_INFO,
                "ROLL \u223C:"+ str(transformationValues["Roll"])   # Tilde (represents ROLL)    
            )
            self.gesture_detector.process_signal(transformationValues["Roll"], 5) 
        if "Translation Vector" in transformationValues:
            self._debug_print(
                self.DEBUG_INFO, 
                "Translation Vector: " + str(transformationValues["Translation Vector"])
            )

    def face_processor_result_all_callback(self, blendshapes, transformationValues):
        self._debug_print(self.DEBUG_THREADING, "Liveness Detector Thread>>>>>>" + threading.current_thread().name)
        # Join the two signals
        signals_dictionary = {**blendshapes, **transformationValues}
        self.gesture_detector.process_signals(signals_dictionary)

        if 'Top Square' in transformationValues:
            top_square = transformationValues['Top Square']
        else:
            top_square = None

        if 'Left Square' in transformationValues:
            left_square = transformationValues['Left Square']
        else:
            left_square = None

        if 'Right Square' in transformationValues:
            right_square = transformationValues['Right Square']
        else:
            right_square = None

        if 'Bottom Square' in transformationValues:
            bottom_square = transformationValues['Bottom Square']
        else:
            bottom_square = None

        # If any of the values are None, assign None to self.face_square_normalized_points
        if None in [top_square, left_square, right_square, bottom_square]:
            self.face_square_normalized_points = {}
        else:
            self.face_square_normalized_points = {
                'topSquare': top_square,
                'leftSquare': left_square,
                'rightSquare': right_square,
                'bottomSquare': bottom_square
            }        

    def gestures_requester_result_callback(self, alive):
        if (alive):
            logger.debug("The person is alive")
            self._compare_local_pictures_with_reference()
        else:
            logger.debug("The person is not alive")
            self.gestures_requester.set_overwrite_text(
                self.translator.translate("error.not_verified"),
                True
            )
            try:
                self.mediaManager.failure(
                    self.verification_token,
                    callback = lambda: setattr(self, 'done', True)
                )
            except Exception as e:
                logger.error("Error occurred:", str(e))
                self.gestures_requester.set_overwrite_text(
                    self.translator.translate("error.failure_report_error"),
                    True
                )

            self.mediaManager.failure(
                self.verification_token,
                callback = lambda: setattr(self, 'done', True)
            )
    
    def gestures_requester_take_a_picture_callback(self):
        logger.debug("Take a picture")
        self.take_a_picture = True

    def get_gestures_requester_process_status(self):
        return self.gestures_requester.process_status
    
    def get_gestures_requester_overwrite_text_log(self):
        return self.gestures_requester.overwrite_text_log

    def _debug_print(self, level_required, message):
        if self.debug_level >= level_required:
            print(message)

    def _verify_correct_face(self):
        # Check if face_square_normalized_points exists and contains all required keys.
        required_keys = ['topSquare', 'leftSquare', 'rightSquare', 'bottomSquare']
        if not hasattr(self, 'face_square_normalized_points') or \
           not all(key in self.face_square_normalized_points for key in required_keys):
            return self.translator.translate("warning.face_not_detected_message")

        if self.glasses:
            return self.translator.translate("warning.face_with_glasses_message")
        # get the coordinates of the square
        top_square = self.face_square_normalized_points['topSquare']
        left_square = self.face_square_normalized_points['leftSquare']
        right_square = self.face_square_normalized_points['rightSquare']
        bottom_square = self.face_square_normalized_points['bottomSquare']

        # calculate the width and height of the detected face
        face_width = right_square - left_square
        face_height = bottom_square - top_square

        # calculate the center of the detected face
        face_center_x = (right_square + left_square) / 2.0
        face_center_y = (top_square + bottom_square) / 2.0

        # check if the face width is between the min and max percentage of the image width
        min_face_width = self.cfg.percentage_min_face_width
        max_face_width = self.cfg.percentage_max_face_width
        if not (min_face_width <= face_width <= max_face_width):
            return self.translator.translate("warning.wrong_face_width_message")

        # check if the face height is between the min and max percentage of the image height
        min_face_height = self.cfg.percentage_min_face_height
        max_face_height = self.cfg.percentage_max_face_height
        if not (min_face_height <= face_height <= max_face_height):
            return self.translator.translate("warning.wrong_face_height_message")

        # check if the center of the face is within the allowed offset from the center of the image
        allowed_offset = self.cfg.percentage_center_allowed_offset
        if not (0.5 - allowed_offset <= face_center_x <= 0.5 + allowed_offset):
            return self.translator.translate("warning.wrong_face_center_message")
        if not (0.5 - allowed_offset <= face_center_y <= 0.5 + allowed_offset):
            return self.translator.translate("warning.wrong_face_center_message")

        # if none of the conditions failed, return None indicating the face 
        # is in correct position and that there are no messages to warning
        return None

    def _face_match_callback_function(self, result, id):
        # Do something with the result
        logger.debug("callback result, id=", id, ", ", result)

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
        
        result = await asyncio.to_thread(DeepFace.verify, image1, image2, align = False)
        return result

    def _compare_local_pictures_with_reference(self):
        return self.asyncio_loop.create_task(self._async_compare_local_pictures_with_reference())    

    async def _async_compare_local_pictures_with_reference(self):
        self.faceProcessor.set_do_process_image(False)
        try:    
            self.gestures_requester.set_overwrite_text(
                self.translator.translate("message.getting_reference_images")
            )
            ret = await self.mediaManager.download_images_from_token(
                self.verification_token,
                "./downloaded_images"
            )
            reference_images = ret["downloaded_images"]
            if ret["status"] == "error":
                self.gestures_requester.set_overwrite_text(ret["msj"], True)
            else:
                self.gestures_requester.set_overwrite_text(
                    self.translator.translate("message.done")
                )
        except Exception as e:
            # Handle the exception here
            logger.error("Error getting reference images:", str(e))
            self.gestures_requester.set_overwrite_text(
                self.translator.translate("error.getting_reference_images"), 
                True
            )
            reference_images = []

        if len(reference_images) > 0:
            logger.debug("reference images: %s", reference_images)
            distances = []
            for reference_image_path in reference_images:
                faces = await find_face(reference_image_path)
                if (len(faces) == 1):
                    logger.debug("The reference image (%s) meets the criteria for an acceptable face picture.", reference_image_path)            
                else:
                    logger.debug("The reference image (%s) doesn't meet the criteria for an acceptable face picture.", reference_image_path)            
                reference_image = cv2.imread(reference_image_path)
                p_index = 0
                for picture in self.pictures:
                    p_index += 1
                    try:
                        logger.debug('picture: %s', picture.shape)
                        faces = await find_face(picture)
                        if (len(faces) == 1):
                            logger.debug("The picture meets the criteria for an acceptable face match.")            
                        else:
                            logger.debug("The picture doesn't meet the criteria for an acceptable face match.")
                            self.gestures_requester.set_overwrite_text(
                                self.translator.translate("message.doing_face_match") + " (" + 
                                str(p_index) + 
                                " " + self.translator.translate("message.of") + " " +
                                str(len(self.pictures)) + 
                                "). " + 
                                self.translator.translate("error.does_not_meet_criteria_for_acceptable_face_match")
                            )
                        self.gestures_requester.set_overwrite_text(
                            self.translator.translate("message.doing_face_match") + " (" + 
                            str(p_index) + 
                            " " + self.translator.translate("message.of") + " " +
                            str(len(self.pictures)) + 
                            "). "
                        )
                        result = await self._async_face_match(picture, reference_image)
                        logger.debug('face match result: %s', result)
                        distances.append(result['distance'])
                    except Exception as e:
                        # Handle the exception here
                        logger.error("Error occurred in face match: %s", str(e))
                        self.gestures_requester.set_overwrite_text(
                            self.translator.translate("error.error_doing_face_match"), 
                            True
                        )
                #TODO: Remove this comment: os.remove(reference_image_path)
            total_distance = sum(distances)
            if len(distances) == 0:
                average_distance = 1
            else:
                average_distance = total_distance / len(distances)
            logger.debug('Average distance: %f', average_distance)
            if average_distance < 0.4:
                logger.debug("Verified!!")
                self.gestures_requester.set_overwrite_text(
                    self.translator.translate("message.verified")
                )
                self.gestures_requester.process_status = GesturesRequesterSystemStatus.DONE
                try:
                    self.mediaManager.success(
                        self.verification_token,
                        callback = lambda: setattr(self, 'done', True)
                    )
                except Exception as e:
                    # Handle the exception here
                    logger.error("Error occurred sending success: %s", str(e))
                    self.gestures_requester.set_overwrite_text(
                        self.translator.translate("error.success_report"), 
                        True
                    )
            else:
                logger.debug("Not Verified!!!")
                self.gestures_requester.set_overwrite_text(
                    self.translator.translate("error.not_verified"), 
                    True
                )
                try:
                    self.mediaManager.failure(
                        self.verification_token,
                        callback = lambda: setattr(self, 'done', True)
                    )
                except Exception as e:
                    # Handle the exception here
                    logger.error("Error occurred sending failure: %s", str(e))
                    self.gestures_requester.set_overwrite_text(
                        self.translator.translate("error.failure_report_error"), 
                        True
                    )
        else:
            logger.debug("No reference images found, not Verified!!!")
            self.gestures_requester.set_overwrite_text(
                self.translator.translate("error.no_reference_images") + 
                ", " + 
                self.translator.translate("error.not_verified"), 
                True
            )
            try:
                self.mediaManager.failure(
                    self.verification_token,
                    callback = lambda: setattr(self, 'done', True)
                )
            except Exception as e:
                # Handle the exception here
                logger.error("Error occurred sending failure (2): %s", str(e))
                self.gestures_requester.set_overwrite_text(
                    self.translator.translate("error.failure_report_error"), 
                    True
                )

    