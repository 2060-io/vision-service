import os
import json
from jsonschema import validate, ValidationError
from typing import List
from livenessDetector.Gesture import Gesture
from gestures.gesturesSchema import gesturesSchema
import logging

# Get the logger for this module
logger = logging.getLogger(__name__)


class GestureDetector:
    def __init__(self):
        self.gestures: List[Gesture] = []
        self.signal_trigger_callback = None
        
    def cleanup(self):
        logger.debug("GestureDetector Cleanup") 
        del self.gestures
        self.signal_trigger_callback = None

    def __del__(self):
        logger.debug("GestureDetector destroyed") 
    
    def add_gesture(self, gesture: Gesture):
        self.gestures.append(gesture)

    def add_gesture_from_file(self, file_path):        
        if not os.path.exists(file_path):
            return False, None, None, None

        with open(file_path, 'r') as f:
            try:
                gesture_data = json.load(f)
                validate(instance=gesture_data, schema=gesturesSchema)

                if 'signal_index' in gesture_data or 'signal_key' in gesture_data:
                    gesture_to_add = Gesture(
                        gesture_data['gestureId'],
                        gesture_data['label'],
                        gesture_data['total_recommended_max_time'],
                        gesture_data['take_picture_at_the_end'],
                        gesture_data['instructions'],
                        signal_index=gesture_data.get('signal_index'),
                        signal_key=gesture_data.get('signal_key')
                    )
                    self.gestures.append(gesture_to_add)
                    return True, gesture_data['gestureId'], gesture_data['label'], gesture_data['icon_path'], gesture_data['total_recommended_max_time'], gesture_data['take_picture_at_the_end'] 

            except (json.JSONDecodeError, ValidationError):
                return False, None, None, None, None    
    
    def process_signal(self, value, signal_index):
        # Iteratate only if the gesture is working
        workingGestures = [gesture for gesture in self.gestures if gesture.working]
        for gesture in workingGestures:
            completed = gesture.update(value, signal_index)
            if completed:
                self.signal_trigger(gesture)

    def process_signals(self, signals_dictionary):
        workingGestures = [gesture for gesture in self.gestures if gesture.working]
        for gesture in workingGestures:
            if gesture.signal_key in signals_dictionary:
                completed = gesture.update(signals_dictionary[gesture.signal_key], signal_key=gesture.signal_key)
                if completed:
                    self.signal_trigger(gesture)

    def signal_trigger(self, gesture):
        logger.debug('Gesture %s triggered.', gesture.label)
        if self.signal_trigger_callback:
            self.signal_trigger_callback(gesture.label)
            #TODO: Thread safe implementation (Maybe in the callback or with a Queue)

    def set_signal_trigger_callback(self, callback):
        self.signal_trigger_callback = callback

    def reset_all(self):
        if len(self.gestures) > 0:
            for gesture in self.gestures:
                gesture.reset()
            return True
        else:
            return False

    def reset_by_index(self, gesture_index):
        if gesture_index < len(self.gestures):
            self.gestures[gesture_index].reset()
            return True
        else:
            return False

    def reset_by_label(self, gesture_label):
        for gesture in self.gestures:
            if gesture.get_label() == gesture_label:
                gesture.reset()
                return True
        return False

    def start_all(self):
        if len(self.gestures) > 0:
            for gesture in self.gestures:
                gesture.start()
            return True
        else:
            return False

    def start_by_index(self, gesture_index):
        if gesture_index < len(self.gestures):
            self.gestures[gesture_index].start()
            return True
        else:
            return False
    
    def start_by_label(self, gesture_label):
        for gesture in self.gestures:
            if gesture.get_label() == gesture_label:
                gesture.start()
                return True
        return False
        
    def stop_all(self):
        if len(self.gestures) > 0:
            for gesture in self.gestures:
                gesture.stop()
            return True
        else:
            return False

    def stop_by_index(self, gesture_index):
        if gesture_index < len(self.gestures):
            self.gestures[gesture_index].stop()
            return True
        else:
            return False
    
    def stop_by_label(self, gesture_label):
        for gesture in self.gestures:
            if gesture.get_label() == gesture_label:
                gesture.stop()
                return True
        return False

    def get_gestures(self):
        return self.gestures
    
    def get_gesture_by_label(self, gesture_label):
        for gesture in self.gestures:
            if gesture.get_label() == gesture_label:
                return gesture
        return None
    
    def get_event_from_gesture_label(self, gesture_label):
        gesture = self.get_gesture_by_label(gesture_label)
        if gesture is None:
            return None
        else:
            return gesture.get_event()

