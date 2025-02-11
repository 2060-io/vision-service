import asyncio
from deepface import DeepFace
import tensorflow as tf
import cv2
import numpy as np
import multiprocessing
import logging

# Get the logger for this module
logger = logging.getLogger(__name__)

async def find_face(image):
    """
    Asynchronously finds faces in an image using DeepFace.

    This function attempts to extract faces from an input image asynchronously. If no faces are 
    detected, an empty list is returned.

    Args:
        image (np.ndarray): Input image as a numpy array.

    Returns:
        list: List of faces found in the image. Each face is represented as an np.ndarray.
              If no faces found, returns an empty list.

    Raises:
        ValueError: Raised when DeepFace.extract_faces encounters problems.
                     Handled in the function to return an empty list.
    """
    try:
        result = await asyncio.to_thread(DeepFace.extract_faces, image)
    except ValueError:
        result = []
    return result    

class FaceGlassesDetector:
    """
    A detector class to predict if glasses are present in an image using a trained TensorFlow Lite model.

    This class reads an image or a path to an image file, processes the image and feeds it into a pre-trained
    TensorFlow Lite model for glasses detection. The model predicts whether glasses are detected or not.

    Attributes:
        interpreter (tf.lite.Interpreter): Instance of a tensorflow lite Interpreter object.
        input_details (list): Input details of the model.
        output_details (list): Output details of the model.

    Methods:
       __init__(self, model_path: str)
           Initializes an instance of the class.

       load_glasses_interpreter(self, model_path: str)
           Loads a TensorFlow Lite interpreter using a provided glasses-no glasses model.

       find_glasses(self, glasses_image: Union[str, np.ndarray])
           Takes an image or a path to an image, processes the image and feeds it into the trained model 
           to detect if glasses are present.

    """    
    def __init__(self, model_path):
        """
        Initializes an instance of the class.

        Args:
            model_path (str): Path to the TensorFlow Lite glasses-no glasses model file.

        Attributes:
            interpreter (tf.lite.Interpreter, optional): A tensorflow lite Interpreter object. 
                Default is None.
            input_details (list, optional): A list containing the input details of the model.
                Default is None.
            output_details (list, optional): A list containing the output details of the model.
                Default is None.

        Note: 
            Immediately after initialization, it calls the `load_glasses_interpreter` method and loads
            the TensorFlow Lite model using the provided model path.
        """
        self.interpreter = None
        self.input_details = None
        self.output_details = None
        self.load_glasses_interpreter(model_path)

    def load_glasses_interpreter(self, model_path):
        """
        This method loads a TensorFlow Lite interpreter using a provided glasses-no glasses model.

        The method initiates an interpreter instance with a model from the provided path. It then allocates 
        tensors and retrieves details of input and output tensors which are stored as instance attributes 
        for use in other methods.

        Args:
            model_path (str): Path to the TensorFlow Lite glasses-no glasses model file.

        Note: 
            This method does not return anything but modifies the state of the instance by setting 
            `self.interpreter`, `self.input_details`, and `self.output_details`.
        """
        self.interpreter = tf.lite.Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        # Get input and output tensors.
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

    def find_glasses(self, glasses_image):
        """
        This method takes either an image or the path to an image, processes the image and feeds it into
        a trained model to detect if glasses are present in the image. 
    
        The method can handle both pre-loaded images (in the form of numpy arrays) and file paths to images.
    
        Args:
            glasses_image (Union[str, np.ndarray]): An image or a path to an image file. 
                If a path is provided, the image will be read using OpenCV's imread function.
    
        Returns:
            bool: True if the value predicted by the model is less than 0 (indicating glasses detected), 
                  False otherwise (indicating no glasses detected).
        """
        # If the input is a string (filepath), read the image
        if isinstance(glasses_image, str):
            glasses_image = cv2.imread(glasses_image)

        image = cv2.cvtColor(glasses_image, cv2.COLOR_BGR2RGB)
        # Resize the image to (160, 160)
        image_resized = cv2.resize(image, (160, 160))
        # Reshape the numpy array to have shape [1, 160, 160, 3]
        image_reshaped = np.reshape(image_resized, (1, 160, 160, 3))
        # Convert the numpy array to float32 type
        image_float32 = image_reshaped.astype('float32')
        # Now you can feed this into your model
        self.interpreter.set_tensor(self.input_details[0]['index'], image_float32)
        self.interpreter.invoke()
        output_data = self.interpreter.get_tensor(self.output_details[0]['index'])
        return output_data[0][0] < 0
    

    def threaded_find_glasses(self, glasses_image, callback):
        """
        This method runs the find_glasses method in a separate process and invokes 
        the specified callback function with the result when finished.

        Args:
            glasses_image (str or np.ndarray): Image or path to an image file.
            callback (Callable): Function to be called with the result of find_glasses. 
                The function should accept one argument for the result.
        """

        def worker(glasses_image, queue):
            result = self.find_glasses(glasses_image)
            queue.put(result)

        def listener(queue):
            while True:
                result = queue.get()
                if result is None:
                    break
                callback(result)

        queue = multiprocessing.Queue()

        process_worker = multiprocessing.Process(target=worker, args=(glasses_image, queue))
        process_listener = multiprocessing.Process(target=listener, args=(queue,))

        process_worker.start()
        process_listener.start()

        process_worker.join()
        queue.put(None)  # Signal to listener that worker has completed its task
        process_listener.join()
