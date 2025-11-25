
from ultralytics import YOLO
import os
from config import config
import torch

_model = None
_class_names = {}
_model_imgsz = None  # Store the imgsz used when model was loaded
if torch.cuda.is_available():
    DEVICE = 0               
else:
    DEVICE = "cpu"
def load_model(model_path=None):
    global _model, _class_names, _model_imgsz
    if model_path is None:
        model_path = config.model_path
    try:
        _model = YOLO(model_path, task="detect")
        # Get class names
        if hasattr(_model, "names"):
            _class_names = _model.names
        elif hasattr(_model.model, "names"):
            _class_names = _model.model.names
        else:
            _class_names = {}
            config.model_load_error = "Class names not found"
        # Save available classes and model size
        config.model_classes = list(_class_names.values())
        config.model_file_size = os.path.getsize(model_path) if os.path.exists(model_path) else 0
        config.model_load_error = ""
        # Store the imgsz used when model was loaded to prevent runtime changes
        _model_imgsz = int(config.imgsz)
        return _model, _class_names
    except Exception as e:
        config.model_load_error = f"Failed to load model: {e}"
        _model = None
        _class_names = {}
        _model_imgsz = None
        return None, {}

def reload_model(model_path):
    return load_model(model_path)

def perform_detection(model, image):
    """Perform object detection on an image using the loaded model."""
    global _model_imgsz
    if model is None:
        print("[WARN] Model is None, cannot perform detection. Please check model loading.")
        return None
    
    try:
        # Use the imgsz that was used when model was loaded, not the current config.imgsz
        # This prevents crashes when config.imgsz is changed at runtime
        imgsz_to_use = _model_imgsz if _model_imgsz is not None else int(config.imgsz)
        
        results = model.predict(
            source=image,
            imgsz=imgsz_to_use,
            stream=True,
            conf=config.conf,
            iou=0.5,
            device=DEVICE,
            half=True,
            max_det=config.max_detect,
            agnostic_nms=False,
            augment=False,
            vid_stride=False,
            visualize=False,
            verbose=False,
            show_boxes=False,
            show_labels=False,
            show_conf=False,
            save=False,
            show=False
        )
        return results
    except Exception as e:
        print(f"[ERROR] Detection failed: {e}")
        return None

def get_class_names():
    return _class_names

def get_model_size(model_path=None):
    if not model_path:
        model_path = config.model_path
    return os.path.getsize(model_path) if os.path.exists(model_path) else 0
