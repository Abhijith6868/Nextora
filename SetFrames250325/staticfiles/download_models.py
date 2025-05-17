import urllib.request
import os

BASE_URL = "https://raw.githubusercontent.com/justadudewhohacks/face-api.js/master/weights/"
MODEL_FILES = [
    "tiny_face_detector_model-weights_manifest.json",
    "tiny_face_detector_model-shard1",
    "face_landmark_68_model-weights_manifest.json",
    "face_landmark_68_model-shard1"
]

def download_models():
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(models_dir, exist_ok=True)
    
    for file in MODEL_FILES:
        url = BASE_URL + file
        target_path = os.path.join(models_dir, file)
        print(f"Downloading {file}...")
        urllib.request.urlretrieve(url, target_path)
        print(f"Downloaded {file}")

if __name__ == "__main__":
    download_models()
