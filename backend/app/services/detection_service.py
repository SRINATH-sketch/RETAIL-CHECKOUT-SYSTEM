import os
from ultralytics import YOLO
from app.config import Config
from app.utils.logger import logger

class DetectionService:
    """
    Service to load the YOLOv11 model and perform object detection on images/video frames.
    """
    def __init__(self):
        # Look for custom model first
        if os.path.exists(Config.CUSTOM_MODEL_PATH):
            model_path = Config.CUSTOM_MODEL_PATH
            logger.info(f"Loading custom YOLOv11 model from {model_path}...")
        else:
            model_path = Config.FALLBACK_MODEL_PATH
            logger.warning(
                f"Custom YOLOv11 model 'best.pt' not found at {Config.CUSTOM_MODEL_PATH}. "
                f"Falling back to pre-trained '{model_path}'. It will be downloaded automatically if not present."
            )

        try:
            self.model = YOLO(model_path)
            logger.info("YOLOv11 model successfully loaded.")
        except Exception as e:
            logger.exception(f"Failed to load YOLO model: {e}")
            raise RuntimeError(f"Failed to initialize YOLOv11 model: {e}")

    def detect_frame(self, frame, confidence_threshold=0.25):
        """
        Run YOLOv11 inference on a single frame.
        frame: numpy array (BGR image format)
        confidence_threshold: float (filter results with lower confidence)
        Returns: list of dicts: {"box": [x1, y1, x2, y2], "confidence": float, "class_name": str}
        """
        # Run inference using the loaded YOLO model
        # verbose=False suppresses standard YOLO logging output per frame to keep logs clean
        results = self.model(frame, conf=confidence_threshold, verbose=False)
        
        detections = []
        if not results:
            return detections
            
        result = results[0]
        boxes = result.boxes
        
        for box in boxes:
            # Get coordinates, confidence and class ID
            coords = box.xyxy[0].cpu().numpy() # [x1, y1, x2, y2]
            conf = float(box.conf[0].cpu().numpy())
            class_id = int(box.cls[0].cpu().numpy())
            class_name = self.model.names[class_id]
            
            detections.append({
                'box': [int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])],
                'confidence': conf,
                'class_name': class_name
            })
            
        return detections
