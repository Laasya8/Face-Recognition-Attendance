"""AI pipeline image quality verification checks."""

import cv2
import numpy as np


def check_blur(image_bgr, threshold=80.0):
    """Determine if an image is blurry using the Laplacian variance method.

    Returns a tuple: (is_valid: bool, variance: float)
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return variance >= threshold, float(variance)


def check_lighting(image_bgr, bbox, min_brightness=40.0, max_brightness=220.0):
    """Determine if the face bounding box region has poor lighting (too dark or too bright).

    Returns a tuple: (is_valid: bool, mean_brightness: float)
    """
    x1, y1, x2, y2 = bbox
    crop = image_bgr[max(y1, 0) : y2, max(x1, 0) : x2]
    if crop.size == 0:
        return False, 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(np.mean(gray))
    is_valid = min_brightness <= mean_brightness <= max_brightness
    return is_valid, mean_brightness
