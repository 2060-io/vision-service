class FaceConfig:
    percentage_min_face_width = 0.1
    percentage_max_face_width = 0.5
    percentage_min_face_height = 0.1
    percentage_max_face_height = 0.7
    percentage_center_allowed_offset = 0.25
    wrong_face_width_message = "Face width is not in the correct range."
    wrong_face_height_message = "Face height is not in the correct range."
    wrong_face_center_message = "Face center is not in the correct position."
    face_not_detected_message = "Face detection failed. Check lighting conditions."
    show_face = 0 #0: No, 1: Square, 2: Pixelate Outside
    detect_glasses = False
    face_with_glasses_message = "You are using glasses, please remove them"