import cv2
from PIL import ImageFont, ImageDraw, Image
import numpy as np
import time  # Needed for the sleep function
import random 
import threading
from enum import IntEnum
import logging


# Get the logger for this module
logger = logging.getLogger(__name__)


class GesturesRequesterSystemStatus(IntEnum):
    IDLE = 1
    PROCESSING = 2
    DONE = 3
    FAILURE = 4

class GesturesRequester:
    DEBUG_OFF = 0
    DEBUG_INFO = 1
    DEBUG_THREADING = 2

    def __init__(self, number_of_gestures_to_request, gesture_detector, translator, debug_level=DEBUG_OFF):
        self.translator = translator
        self.number_of_gestures_to_request = number_of_gestures_to_request
        self.debug_level = debug_level
        self._overwrite_text = None
        self.overwrite_text_log = []
        self.process_status = GesturesRequesterSystemStatus.IDLE
        self.gesture_detector = gesture_detector
        self.gesture_detector.set_signal_trigger_callback(self.gesture_detected_callback)
        self.current_gesture_request = None
        self.gestures_list = []
        self.gestures_to_test = [{"gestureId": "starting", "label": "Starting", "time": 5000, "start_gesture": False, "take_picture_at_the_end": False}]
        self.current_gesture_started_at = time.time() * 1000  # Current time in milliseconds
        self.start_time = False
        self.current_gesture_index = 0  # To keep track of which gesture we're executing
        self.report_alive_callback = None
        self.ask_to_take_a_picture_callback = None
        self.font = self._load_font(font_path="Halant-Bold.ttf", font_scale=5, image_width=640)
        self.lastTextToRequest = ""
        self.lastTextToRequestImage = None

    def cleanup(self):
        logger.debug("GesturesRequester Cleanup") 
        del self.gesture_detector
        self.current_gesture_request = None
        self.gestures_list = []
        self.gestures_to_test = []
        self.report_alive_callback = None
        self.ask_to_take_a_picture_callback = None

    def __del__(self):
        logger.debug("GesturesRequester destroyed") 
  
    def _load_font(self, font_path="Halant-Bold.ttf", font_scale=1, image_width=640):
        font_size = int(font_scale * image_width / 2 * 0.02)
        font = ImageFont.truetype(font_path, font_size)
        return font

    def _create_text_image(self, text, font, margin, width, text_color_b = (0, 0, 0), border_thickness=2, border_color=(255, 255, 255)):
        background_color = (255, 255, 255, 0)  # White with transparency

        draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))  # Temporary image for calculating text size

        avg_char_width = draw.textbbox((0, 0), "A", font=font)[2]*0.7
        line_height = draw.textbbox((0, 0), "A", font=font)[3]

        lines = []
        words = text.split()
        line = ""

        max_chars_per_line = int((width - 2 * margin) / avg_char_width)

        for word in words:
            if len(line + ' ' + word) <= max_chars_per_line or not line:
                line = f'{line} {word}'.strip()
            else:
                lines.append(line)
                line = word
        lines.append(line)

        height = len(lines) * line_height + int(margin/2)

        size = (width, height)
        image = Image.new("RGBA", size, background_color)
        draw = ImageDraw.Draw(image)

        y = 0
        for line in lines:
            line_width = draw.textbbox((0, 0), line, font=font)[2]
            x = (width - line_width) / 2

            # Draw text with a border (outline)
            draw.text(
                (x, y), 
                line, 
                font=font, 
                fill=text_color_b, 
                stroke_width=border_thickness, 
                stroke_fill=border_color
            )

            y += line_height  # Move to the next line position
        return image

    def _pil_to_opencv(self, pil_image):
        """
        Convert a PIL Image (RGB or RGBA) to an OpenCV image format.
        Preserves the alpha channel if present.

        Parameters:
        pil_image (PIL.Image): The image to convert.

        Returns:
        numpy.ndarray: The converted OpenCV image.
        """

        # Convert the PIL image to a numpy array
        numpy_image = np.array(pil_image)

        # Check if the PIL image has an alpha channel
        if pil_image.mode == 'RGBA':
            # Convert RGBA to BGRA
            opencv_image = cv2.cvtColor(numpy_image, cv2.COLOR_RGBA2BGRA)
        elif pil_image.mode == 'RGB':
            # Convert RGB to BGR
            opencv_image = cv2.cvtColor(numpy_image, cv2.COLOR_RGB2BGR)
        else:
            opencv_image = numpy_image  # If not 'RGB' or 'RGBA', return as-is

        return opencv_image

    def _add_images(self, ocv_background, ocv_image, x=0, y=0):
        # Ensure the image to overlay (ocv_image) fits within the background dimensions
        bg_height, bg_width = ocv_background.shape[:2]
        img_height, img_width = ocv_image.shape[:2]

        # Check if x, y positions are valid
        if x >= bg_width or y >= bg_height:
            raise ValueError("The x and y positions must be within the background image dimensions.")

        # Calculate the size of the area to blend based on the foreground image size and position
        blend_area_width = img_width if x + img_width < bg_width else bg_width - x
        blend_area_height = img_height if y + img_height < bg_height else bg_height - y

        # If the foreground image exceeds the background boundaries, crop the overlay image
        if blend_area_width != img_width or blend_area_height != img_height:
            ocv_image = ocv_image[:blend_area_height, :blend_area_width]

        # Split out the channels from the foreground image
        img_bgra = ocv_image[..., :3]  # BGR channels
        img_alpha = ocv_image[..., 3] / 255.0  # Alpha channel normalized (as a mask)

        # Get the regions of interest (roi) in the background where we want to overlay
        roi = ocv_background[y:y + blend_area_height, x:x + blend_area_width]

        # Blend the images
        for c in range(0, 3):
            roi[..., c] = roi[..., c] * (1 - img_alpha) + img_bgra[..., c] * img_alpha

        # Put the modified ROI back into the original image
        ocv_background[y:y + blend_area_height, x:x + blend_area_width] = roi

        return ocv_background

    def gesture_detected_callback(self, gesture_label):
        logger.debug('Gesture Requester Thread>>>>>>%s', threading.current_thread().name)
        logger.debug('Gesture Detected:%s', gesture_label)
        self._move_to_next_gesture() #TODO: Thread safe (Maybe can generate some problems if we do it like this)
    
    def set_overwrite_text(self, text = None, failure = False):
        self._overwrite_text = text
        self.overwrite_text_log.append(text)
        if failure == True:
            self.process_status = GesturesRequesterSystemStatus.FAILURE

    def process_image(self, img, show_face = 0, npoints = None, warning_message = None):
        img_out = img.copy()
        if npoints:
            if show_face == 1:
                self._draw_square(img_out, npoints)
            elif show_face == 2:
                img_out = self._pixelate_outside_square(img_out, npoints)
        text, icon = self._process_requests()
        textToRequest = text
        textToRequestWarning = False
        if self._overwrite_text is not None:
            textToRequest = self._overwrite_text
        if icon is not None:
            self._add_icon_to_image(img_out, icon, 550, 400, 64, 64)
        if (warning_message):
            textToRequest = warning_message
            textToRequestWarning = True
        
        if self.lastTextToRequest != textToRequest:
            _, img_width = img.shape[:2]
            if textToRequestWarning:
                pil_text_image = self._create_text_image(
                    textToRequest,
                    self.font,
                    20,
                    img_width,
                    (255,255,0),
                    2,
                    (0,0,0)
                )
            else:
                pil_text_image = self._create_text_image(
                    textToRequest,
                    self.font,
                    20,
                    img_width,
                    (255,255,255),
                    2,
                    (0,0,0)
                )
            ocv_text_image = self._pil_to_opencv(pil_text_image)
            self.lastTextToRequestImage = ocv_text_image
            self.lastTextToRequest = textToRequest
        
        img_out = self._add_images(img_out, self.lastTextToRequestImage)
        
        return img_out
    
    def set_gestures_list(self, gestures):
        self.gestures_list = gestures
        self._generate_gestures_to_test_list(self.number_of_gestures_to_request)
        self._start_gestures_sequence()

    def set_report_alive_callback(self, report_alive_callback):
        self.report_alive_callback = report_alive_callback

    def set_ask_to_take_a_picture_callback(self, ask_to_take_a_picture_callback):
        self.ask_to_take_a_picture_callback = ask_to_take_a_picture_callback
    
    def _draw_square(self, img_out, npoints):
        # Convert normalized coordinates to pixel coordinates
        height, width = img_out.shape[:2]
        topPixel = int(npoints['topSquare'] * height)
        leftPixel = int(npoints['leftSquare'] * width)
        rightPixel = int(npoints['rightSquare'] * width)
        bottomPixel = int(npoints['bottomSquare'] * height)

        # Draw the square on the image
        color = (0, 255, 0)  # Green color for the square (BGR format)
        thickness = 2  # Thickness of the square's boundary line
        cv2.rectangle(img_out, (leftPixel, topPixel), (rightPixel, bottomPixel), color, thickness)

    def _pixelate_outside_square(self, img, npoints):
        # Convert normalized coordinates to pixel coordinates
        height, width = img.shape[:2]
        topPixel = int(npoints['topSquare'] * height)
        leftPixel = int(npoints['leftSquare'] * width)
        rightPixel = int(npoints['rightSquare'] * width)
        bottomPixel = int(npoints['bottomSquare'] * height)

        # Create the mask where white pixels represent regions to keep sharp
        mask = np.zeros((height, width), dtype=np.uint8)
        mask[topPixel:bottomPixel, leftPixel:rightPixel] = 255

        # Compute inverse mask where white pixels represent regions to pixelate
        inv_mask = cv2.bitwise_not(mask)

        # Pixelate the entire image
        pixelated_img = cv2.resize(cv2.resize(img, (width//10, height//10)), (width, height), interpolation=cv2.INTER_LINEAR)

        # Use the masks to combine the pixelated and original images
        sharp_region = cv2.bitwise_and(img, img, mask=mask)
        pixelated_region = cv2.bitwise_and(pixelated_img, pixelated_img, mask=inv_mask)

        # Combine the sharp and pixelated regions
        img_out = cv2.add(sharp_region, pixelated_region)

        return img_out
    
    def _add_icon_to_image(self, image, icon_x, x_pos, y_pos, out_width=32, out_height=32):
        # Check if the icon will be fully inside the image
        if x_pos<0 or y_pos<0 or (x_pos+out_width)>image.shape[1] or (y_pos+out_height)>image.shape[0]:
            logger.debug("Icon won't fit entirely in the image. So, not drawing the icon.")
            return image
        # Resize the icon
        icon = cv2.resize(icon_x, (out_width, out_height))
        # Create mask from the alpha channel
        mask = icon[:,:,3] == 0
        # Replace the area with the icon
        image[y_pos:y_pos+out_height, x_pos:x_pos+out_width][~mask] = icon[:,:,:3][~mask]
        return image
        
    def _process_requests(self):
        if self.start_time:
            self.current_gesture_started_at = time.time() * 1000  # Current time in milliseconds
            self.start_time = False
        if self.current_gesture_index != 0:
            # Check if it's time to change gesture
            current_time = time.time() * 1000
            elapsed_time = current_time - self.current_gesture_started_at
            if elapsed_time >= self.current_gesture_request['time']:
                if self.current_gesture_request["start_gesture"]:
                    self._reset_not_alive()
                else:
                    self._move_to_next_gesture(current_time)
        # Add text to the image
        #text = f"{self.current_gesture_request['label']}" if self.current_gesture_request else "No gesture"
        if self.current_gesture_request:
            gId = self.current_gesture_request['gestureId']
            translateId = "gestures." + gId + ".label"
            text = self.translator.translate(translateId)
        else:
            text = "No gesture"
        icon = self.current_gesture_request['icon'] if self.current_gesture_request and 'icon' in self.current_gesture_request else None
        return text, icon
    
    def _move_to_next_gesture(self, current_t = None):
        if self.current_gesture_index != 0:
            # If moving to the last detect that change
            if (self.current_gesture_index + 2) == len(self.gestures_to_test):
                logger.debug("Event!!! Is Alive Generated")
                if self.report_alive_callback:
                    self.report_alive_callback(True)
            if self.current_gesture_request["take_picture_at_the_end"]:
                logger.debug("Taking a picture")
                if self.ask_to_take_a_picture_callback:
                    self.ask_to_take_a_picture_callback()
            current_time = current_t
            if current_time == None:
                current_time = time.time() * 1000
            self.current_gesture_index += 1  # Move to next gesture
            if self.current_gesture_index < len(self.gestures_to_test):  # If there are gestures left
                self.current_gesture_request = self.gestures_to_test[self.current_gesture_index]
                self.current_gesture_started_at = current_time
                if self.current_gesture_request["start_gesture"]:
                    logger.debug('START GESTURE DETECTION:%s', self.current_gesture_request["label"])
                    self.gesture_detector.start_by_label(self.current_gesture_request["label"])
            #else:
            #    logger.debug("Finished all gestures")
    
    def _reset_not_alive(self):
        self.current_gesture_index = 0 # Reset, Not alive
        self.current_gesture_request = self.gestures_to_test[self.current_gesture_index]
        logger.debug("Event!!! NOT Alive Generated")
        if self.report_alive_callback:
            self.report_alive_callback(False)
 
    def _generate_gestures_to_test_list(self, number_of_gestures_to_request):
        self.gestures_to_test = [
                {"gestureId": "notAlive", "label": "Not Alive", "time": 5000, "start_gesture": False, "take_picture_at_the_end": False},
                {"gestureId": "starting", "label": "Starting", "time": 5000, "start_gesture": False, "take_picture_at_the_end": False}
            ]


        # Select two random gestures from the list
        selected_gestures = random.sample(self.gestures_list, number_of_gestures_to_request)

        for gesture in selected_gestures:
            self.gestures_to_test.append(
                {
                    "gestureId": gesture["gestureId"],
                    "label": gesture['label'],
                    "icon_path": gesture["icon_path"],
                    "icon": gesture["icon"],
                    "time": gesture['total_recommended_max_time'],
                    "start_gesture": True,
                    "take_picture_at_the_end": gesture['take_picture_at_the_end']
                }
            )
            self.gestures_to_test.append(
                {
                    "gestureId": "ok",
                    "label": "Ok",
                    "time": 3000,
                    "start_gesture": False,
                    "take_picture_at_the_end": False
                }
            )        
        self.gestures_to_test.append(
            {
                "gestureId": "youarealive",
                "label": "You Are Alive",
                "time": 5000,
                "start_gesture": False,
                "take_picture_at_the_end": False
            }
        )
        logger.debug('gestures_to_test: %s', self.gestures_to_test)

    def _start_gestures_sequence(self):
        self.current_gesture_index = 1 # 0 is reserved when the time out in gestures happens
        self.current_gesture_request = self.gestures_to_test[self.current_gesture_index]
        #self.current_gesture_started_at = time.time() * 1000  # Current time in milliseconds
        self.start_time = True
