import time
import numpy as np
import mediapipe as mp
import logging

# Get the logger for this module
logger = logging.getLogger(__name__)


#import threading

FaceLandmarkerResult = mp.tasks.vision.FaceLandmarkerResult
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
VisionRunningMode = mp.tasks.vision.RunningMode

#############################################################
# UTILITY FUNCTIONS
#############################################################
def _get_angles_from_rotation_matrix(rotation_matrix):
    """
    Calculates the yaw, pitch, and roll angles from the rotation matrix.

    Args:
        rotation_matrix: The rotation matrix.

    Returns:
        A tuple of yaw, pitch, and roll angles.
    """

    yaw = np.arctan2(rotation_matrix[2, 0], rotation_matrix[2, 1])
    pitch = np.arctan2(rotation_matrix[1, 2], np.sqrt(rotation_matrix[0, 2]**2 + rotation_matrix[2, 2]**2))
    roll = np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])

    return yaw, pitch, roll


#############################################################
# MAIN CLASS
#############################################################
class FaceProcessor:
    def __init__(self):
        self.resultsCallbackFn = None        
        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path="./livenessDetector/face_landmarker.task"),
            running_mode=VisionRunningMode.LIVE_STREAM,
            output_face_blendshapes = True,
            output_facial_transformation_matrixes = True,
            result_callback=self._process_result)
        self.landmarker = FaceLandmarker.create_from_options(options)
        self._do_process_image = True        
    
    def cleanup(self):
        logger.debug("FaceProcessor Cleanup") 
        del self.landmarker
        self.landmarker = None

    def __del__(self):
        logger.debug("FaceProcessor destroyed") 

    def process_image(self, img):
        if (self._do_process_image):
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img)
            current_time_millis = int(round(time.time() * 1000))
            self.landmarker.detect_async(mp_image, current_time_millis)
    
    def set_do_process_image(self, value):
        self._do_process_image = value

    def _process_result(self, result: FaceLandmarkerResult, output_image: mp.Image, timestamp_ms: int):
        lastBlendshapes = {}
        importantTransformationValues = {}
        if result and result.face_blendshapes and result.face_blendshapes[0]:
            lastBlendshapes = {b.category_name: b.score for b in result.face_blendshapes[0]}
            
        if (result and
            result.facial_transformation_matrixes and
            result.facial_transformation_matrixes[0].any()):
                # Convert the transformation matrix to NumPy arrays.
                transformation_matrix = np.array(result.facial_transformation_matrixes[0])
                rotation_matrix = transformation_matrix[:3, :3]
                translation_vector = transformation_matrix[:3, 3]
                yaw, pitch, roll = _get_angles_from_rotation_matrix(rotation_matrix)
                importantTransformationValues["Transformation Yaw"] = yaw
                importantTransformationValues["Transformation Pitch"] = pitch
                importantTransformationValues["Transformation Roll"] = roll
                importantTransformationValues["Transformation Translation Vector"] = translation_vector

        if (result and
            result.face_landmarks and
            result.face_landmarks[0]):
                importantTransformationValues["Top Square"] = result.face_landmarks[0][10].y
                importantTransformationValues["Left Square"] = result.face_landmarks[0][227].x
                importantTransformationValues["Right Square"] = result.face_landmarks[0][345].x
                importantTransformationValues["Bottom Square"] = result.face_landmarks[0][152].y
        else:
                importantTransformationValues["Top Square"] = None
                importantTransformationValues["Left Square"] = None
                importantTransformationValues["Right Square"] = None
                importantTransformationValues["Bottom Square"] = None
        
        if self.resultsCallbackFn:
            self.resultsCallbackFn(lastBlendshapes, importantTransformationValues)

    def set_callback(self, callbackFn):
         self.resultsCallbackFn = callbackFn

