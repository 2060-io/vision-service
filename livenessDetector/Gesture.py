import time
import logging

# Get the logger for this module
logger = logging.getLogger(__name__)


class Gesture:
    def __init__(self, gestureId, label, total_recommended_max_time, take_picture_at_the_end, sequence, signal_index=None, signal_key=None):
        self.working = False
        self.gestureId = gestureId
        self.label = label
        self.signal_index = signal_index
        self.signal_key = signal_key
        self.total_recommended_max_time = total_recommended_max_time
        self.take_picture_at_the_end = take_picture_at_the_end
        self.sequence = sequence
        self.current_index = 0
        self.start_time = time.time()  # Track the start time of the gesture

    def _check(self, value):
        if self.current_index >= len(self.sequence):
            return False

        current_check = self.sequence[self.current_index]

        if current_check.get("move_to_next_type") == "higher":
            return value > current_check["value"]
        elif current_check.get("move_to_next_type") == "lower":
            return value < current_check["value"]

        return False

    def update(self, value, index=None, signal_key=None):
        if self.working:
            if (index is not None and self.signal_index == index) or (signal_key is not None and self.signal_key == signal_key):
                if self._check(value):
                    if self.current_index == 0:
                        self.start_time = time.time()  # Record start time when we first start the gesture
                    self.current_index += 1
                    logger.debug('[%s] Current Index:%s', self.label, self.current_index)
                    if self.current_index >= len(self.sequence):
                        logger.debug('Gesture %s detected.', self.label)
                        return True
                else:
                    if self._check_reset(value):
                        self.reset()
        return False
    
    def _check_reset(self, value):
        if self.current_index >= len(self.sequence):
            return False

        current_check = self.sequence[self.current_index]
        if (not "reset" in current_check) or (not "type" in current_check["reset"]):
            return False

        reset_type = current_check["reset"]["type"]
        if reset_type == "lower":
            return value < current_check["reset"]["value"]
        elif reset_type == "higher":
            return value > current_check["reset"]["value"]
        elif reset_type == "timeout_after_ms":
            # If timeout has passed since start_time, return True
            return time.time() - self.start_time > current_check["reset"]["value"] / 1000  # Convert ms to s

        return False

    def stop(self):
        self.working = False
    
    def reset(self):
        logger.debug('[%s] Reset!!!!', self.label)
        self.current_index = 0
        self.start_time = time.time()  # Clear the start time when we reset

    def get_label(self):
        return self.label
    
    def get_total_recommended_max_time(self):
        return self.total_recommended_max_time

    def start(self):
        self.reset()
        self.working = True

