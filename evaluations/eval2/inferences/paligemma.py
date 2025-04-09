import torch
import json
import os
import time
from argparse import ArgumentParser
import logging
from PIL import Image
from tqdm import tqdm
from transformers import PaliGemmaProcessor, PaliGemmaForConditionalGeneration
from transformers.image_utils import load_image

# Model paths
MODEL_DIR = "/model-weights/paligemma2-10b-mix-448"  # Local model path (not yet available)
HF_MODEL_ID = "google/paligemma2-10b-mix-448"           # Hugging Face Model ID

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.environ["HF_HOME"] = ""
os.environ["TRANSFORMERS_CACHE"] = ""
offload_folder = ""

def load_model(model_source="local"):
    """Load and return the PaliGemma model and processor."""
    model_path = MODEL_DIR if model_source == "local" else HF_MODEL_ID
    logger.info(f"Loading PaliGemma model from {model_path}...")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = PaliGemmaForConditionalGeneration.from_pretrained(
        model_path,
        cache_dir=os.environ["TRANSFORMERS_CACHE"],
        torch_dtype=torch.bfloat16,
        device_map="auto"
    ).eval()
    processor = PaliGemmaProcessor.from_pretrained(
        model_path,
        cache_dir=os.environ["TRANSFORMERS_CACHE"]
    )
    return model, processor

def resize_image(img_path, max_size=(350, 350)):
    """Resize the image while preserving its aspect ratio."""
    try:
        image = Image.open(img_path).convert("RGB")
        image.thumbnail(max_size, Image.LANCZOS)
        return image
    except Exception as e:
        logger.error(f"Error resizing image {img_path}: {e}")
        return None

def process_sample(model, processor, img_path, question):
    """Generate an answer for a single image-question pair."""
    try:
        image = resize_image(img_path)
        if image is None:
            return "Error: Could not process image"
        
        user_prompt = (
            f"Given question, answer in the following format:"
            f"Question:{question}"
            f"Answer:<answer> Reasoning:<reasoning> in the context of the image."
        )
        
        model_inputs = processor(text=user_prompt, images=image, return_tensors="pt").to(torch.bfloat16).to(model.device)
        input_len = model_inputs["input_ids"].shape[-1]
        
        with torch.inference_mode():
            generation = model.generate(**model_inputs, max_new_tokens=256, do_sample=False)
            generation = generation[0][input_len:]
            decoded = processor.decode(generation, skip_special_tokens=True)
        return decoded
    except Exception as e:
        logger.error(f"Error processing {img_path}: {e}")
        return "Error"

def evaluate(model, processor, dataset, image_folder, save_path, mode="single"):
    """Process the dataset and save results to a JSON file."""
    results = []
    logger.info(f"Starting evaluation in {mode} mode...")
    prev_path = ""
    for i, data in enumerate(tqdm(dataset, unit="sample")):
        img_path = os.path.join(image_folder, f"{data['ID']}.jpg")
        if not os.path.exists(img_path):
            logger.warning(f"Image not found for ID {data['ID']} at {img_path}")
            continue
        answer = process_sample(model, processor, img_path, data["Question"])
        results.append({
            "ID": data["ID"],
            "Question": data["Question"],
            "Predicted_Answer": answer,
            "Ground_Truth": data["Answer"],
            "Attribute": data["Attribute"],
        })
        if i % 10 == 0:
            intermediate_results_path = save_path.replace(".json", f"_intermediate_{i}_{time.strftime('%Y%m%d_%H%M%S')}.json")
            with open(intermediate_results_path, "w") as f:
                json.dump(results, f, indent=4, default=str)
            if prev_path:
                os.remove(prev_path)
            logger.info(f"Intermediate results saved to {intermediate_results_path} and deleted {prev_path}.")
            prev_path = intermediate_results_path
    with open(save_path, "w") as f:
        json.dump(results, f, indent=4, default=str)
    logger.info(f"Results saved to {save_path}.")

if __name__ == "__main__":
    start_time = time.time()
    parser = ArgumentParser()
    parser.add_argument("--dataset", type=str, default="./data/eval2/QA_Eval2.json", help="Path to dataset")
    parser.add_argument("--image_folder", type=str, default="./data/processed_images", help="Path to image folder")
    parser.add_argument("--device", type=str, default="cuda", help="Device to run the model on")
    parser.add_argument("--save_path", type=str, default="./results/results_PaliGemma_mix.json", help="Output file to save results")
    parser.add_argument("--model_source", type=str, default="local", help="Model source: 'local' or 'hf'")
    parser.add_argument("--mode", type=str, default="single", choices=["single", "batch"], help="Single or batch processing")
    args = parser.parse_args()
    
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    model, processor = load_model(args.model_source)
    model.to(device)
    
    with open(args.dataset, "r") as f:
        dataset = json.load(f)
    logger.info(f"Loaded dataset with {len(dataset)} samples.")
    evaluate(model, processor, dataset, args.image_folder, args.save_path, args.mode)
    logger.info(f"Total time taken: {time.time() - start_time:.2f} seconds")
