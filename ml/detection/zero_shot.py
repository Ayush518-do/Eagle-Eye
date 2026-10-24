"""OWLv2 zero-shot detector: finds parts from text descriptions, with no training on our data.

Used for the classes that have no public training data (power_supply, io_module), and as a second,
independent opinion for mcb. Prompts come from classes.yaml.
"""
from __future__ import annotations

from PIL import Image

from ml.detection.boxes import load_classes, make_tiles, merge_tile_detections

MODEL_ID = "google/owlv2-base-patch16-ensemble"   # Apache-2.0


class OWLv2Detector:
    def __init__(self, threshold: float = 0.15, classes: list[str] | None = None, tile: int = 1536, device=None):
        import torch
        from transformers import Owlv2ForObjectDetection, Owlv2Processor
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = Owlv2Processor.from_pretrained(MODEL_ID)
        self.model = Owlv2ForObjectDetection.from_pretrained(MODEL_ID).to(self.device).eval()
        self.threshold, self.tile = threshold, tile
        self.prompts, self.prompt_class = [], []
        for c in load_classes():
            if classes is None or c["name"] in classes:
                for p in c["prompts"]:
                    self.prompts.append(p)
                    self.prompt_class.append(c["name"])

    def _predict_crop(self, crop: Image.Image) -> list[tuple]:
        import torch
        inputs = self.processor(text=[self.prompts], images=crop, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
        res = self.processor.post_process_grounded_object_detection(
            outputs, threshold=self.threshold, target_sizes=[(crop.height, crop.width)], text_labels=[self.prompts])[0]
        return [(b.tolist(), float(s), self.prompt_class[int(l)])
                for b, s, l in zip(res["boxes"], res["scores"], res["labels"])]

    def predict(self, image: Image.Image) -> list[dict]:
        """Full-size photo -> [{'bbox', 'score', 'class_name'}] in full-photo pixels."""
        image = image.convert("RGB")
        dets = []
        for t in make_tiles(image.width, image.height, tile=self.tile):
            for box, score, name in self._predict_crop(image.crop(tuple(t.box))):
                dets.append({"bbox": [box[0] + t.x, box[1] + t.y, box[2] + t.x, box[3] + t.y],
                             "score": score, "class_name": name})
        return merge_tile_detections(dets)
