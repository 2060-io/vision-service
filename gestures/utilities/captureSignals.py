import cv2
import mediapipe as mp
from mediapipe import solutions
from mediapipe.framework.formats import landmark_pb2
import numpy as np
import time

#SIGNAL_NAME = "eyeLookDownLeft"
#SIGNAL_NAME = "eyeLookUpLeft"
#SIGNAL_NAME = "eyeLookInLeft"
#SIGNAL_NAME = "eyeLookInRight"
#SIGNAL_NAME = "eyeLookOutLeft"
#SIGNAL_NAME = "eyeLookOutRight"
SIGNAL_NAME = "eyeBlinkLeft"





MinValue = 0
MaxValue = 0.8
MaxCharacters = 30
DecimalPlaces = 10


print(mp.__version__)

# Initialize webcam
cap = cv2.VideoCapture(0)

BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
FaceLandmarkerResult = mp.tasks.vision.FaceLandmarkerResult
VisionRunningMode = mp.tasks.vision.RunningMode


def draw_landmarks_on_image(rgb_image, detection_result):
  face_landmarks_list = detection_result.face_landmarks
  annotated_image = np.copy(rgb_image)

  # Loop through the detected faces to visualize.
  for idx in range(len(face_landmarks_list)):
    face_landmarks = face_landmarks_list[idx]

    # Draw the face landmarks.
    face_landmarks_proto = landmark_pb2.NormalizedLandmarkList()
    face_landmarks_proto.landmark.extend([
      landmark_pb2.NormalizedLandmark(x=landmark.x, y=landmark.y, z=landmark.z) for landmark in face_landmarks
    ])

    solutions.drawing_utils.draw_landmarks(
        image=annotated_image,
        landmark_list=face_landmarks_proto,
        connections=mp.solutions.face_mesh.FACEMESH_TESSELATION,
        landmark_drawing_spec=None,
        connection_drawing_spec=mp.solutions.drawing_styles
        .get_default_face_mesh_tesselation_style())
    solutions.drawing_utils.draw_landmarks(
        image=annotated_image,
        landmark_list=face_landmarks_proto,
        connections=mp.solutions.face_mesh.FACEMESH_CONTOURS,
        landmark_drawing_spec=None,
        connection_drawing_spec=mp.solutions.drawing_styles
        .get_default_face_mesh_contours_style())
    solutions.drawing_utils.draw_landmarks(
        image=annotated_image,
        landmark_list=face_landmarks_proto,
        connections=mp.solutions.face_mesh.FACEMESH_IRISES,
          landmark_drawing_spec=None,
          connection_drawing_spec=mp.solutions.drawing_styles
          .get_default_face_mesh_iris_connections_style())

  return annotated_image

lastTimestamp = int(round(time.time() * 1000))
lastLandmarks = None
lastBlendshapes = None
lastImage = None


def decompose_rotation_matrix(rotation_matrix):
  """Decomposes a rotation matrix into yaw, pitch, and roll angles.

  Args:
    rotation_matrix: A 3x3 rotation matrix.

  Returns:
    A tuple containing the yaw, pitch, and roll angles in radians.
  """

  yaw = np.arctan2(rotation_matrix[2, 1], rotation_matrix[2, 2])
  pitch = np.arcsin(-rotation_matrix[2, 0])
  roll = np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])

  return yaw, pitch, roll

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

def drawValueOf(name, value, minValue, maxValue, maxCharacters, decimalPlaces):
    normalized_value = (value - minValue) / (maxValue - minValue)
    num_hashes = int(normalized_value * maxCharacters)
    if num_hashes > maxCharacters:
        num_hashes = maxCharacters
    result = '#' * num_hashes
    formatted_value = "{:.{}f}".format(value, decimalPlaces)  # Format value with specified number of decimal places
    print("{} {} {}".format(name, formatted_value, result))

# Create a face landmarker instance with the live stream mode:
def print_result(result: FaceLandmarkerResult, output_image: mp.Image, timestamp_ms: int):
    global lastTimestamp, lastLandmarks, lastBlendshapes, lastImage
    lastLandmarks = result
    if (result and
        result.face_blendshapes and
        result.face_blendshapes[0]):
        lastBlendshapes = {b.category_name: b.score for b in result.face_blendshapes[0]}
        drawValueOf(name=SIGNAL_NAME, value=lastBlendshapes[SIGNAL_NAME], minValue=MinValue, maxValue=MaxValue, maxCharacters=MaxCharacters, decimalPlaces=DecimalPlaces) 
        #print(lastBlendshapes["eyeLookDownLeft"])


    if (result and
        result.facial_transformation_matrixes and
        result.facial_transformation_matrixes[0].any()):
        # Convert the transformation matrix to NumPy arrays.
        transformation_matrix = np.array(result.facial_transformation_matrixes[0])
        rotation_matrix = transformation_matrix[:3, :3]
        translation_vector = transformation_matrix[:3, 3]
        #yaw, pitch, roll = _get_angles_from_rotation_matrix(rotation_matrix)
        yaw, pitch, roll = decompose_rotation_matrix(rotation_matrix)

        
        #print("YAW \u2190\u2192:", yaw)
        #print("PITCH \u2191\u2193:", pitch)  # Upwards arrow (represents PITCH)
        #print("ROLL \u223C:", roll)   # Tilde (represents ROLL)
        #print("Translation Vector:", translation_vector)
    lastImage = output_image    

options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path="../../livenessDetector/face_landmarker.task"),
    running_mode=VisionRunningMode.LIVE_STREAM,
    output_face_blendshapes = True,
    output_facial_transformation_matrixes = True,
    result_callback=print_result)

with FaceLandmarker.create_from_options(options) as landmarker:
    while cap.isOpened():
        ret, frame = cap.read()
        current_time_millis = int(round(time.time() * 1000))
        if not ret:
            break
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        # Send live image data to perform face landmarking.
        # The results are accessible via the `result_callback` provided in
        # the `FaceLandmarkerOptions` object.
        # The face landmarker must be created with the live stream mode.
        landmarker.detect_async(mp_image, current_time_millis)
        
        if cv2.waitKey(1) & 0xFF == 27:  # Press Esc to exit
            break
        
        if (lastLandmarks != None):
            res_image = draw_landmarks_on_image(lastImage.numpy_view(), lastLandmarks)
            output_ndarray = res_image
        else:
            output_ndarray = mp_image.numpy_view()
        
        cv2.imshow('MediaPipe Face Landmarks', output_ndarray)
    
    # Release the webcam and destroy all windows
    cap.release()
    cv2.destroyAllWindows()

    