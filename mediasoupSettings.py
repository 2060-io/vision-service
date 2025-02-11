# Default settings
_config = {
    'mediasoup_save_input_and_output': False,
    'mediasoup_rotate_input_image': 0,
    'mediasoup_flip_input_image': True,
    'remove_urn_3gpp_video_orientation': False,
    'matcher_save_match_images': False
}

def get_setting(key):
    """Retrieve the value of a specified setting."""
    # Return the value if it exists, otherwise raise a KeyError
    if key in _config:
        return _config[key]
    else:
        raise KeyError(f"Setting '{key}' not found.")

def set_setting(key, value):
    """Set the value of a specified setting."""
    # Update the setting if it exists, otherwise raise a KeyError
    if key in _config:
        _config[key] = value
    else:
        raise KeyError(f"Setting '{key}' not found.")

def add_setting(key, value):
    """Add a new setting key-value pair."""
    if key not in _config:
        _config[key] = value
    else:
        raise KeyError(f"Setting '{key}' already exists.")

def all_settings():
    """Return a copy of all settings for inspection."""
    return _config.copy()