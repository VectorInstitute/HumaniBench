#!/usr/bin/env python
import os
import json
import torch
import csv
from glob import glob
from PIL import Image
from argparse import ArgumentParser
from huggingface_hub import login
from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig


def resize_image(img_path, max_size=(350, 350)):
    """Resize image to fit within the specified max size."""
    try:
        image = Image.open(img_path).convert("RGB")
        image.thumbnail(max_size, Image.LANCZOS)
        return image
    except Exception as e:
        print(f"Error resizing image {img_path}: {e}")
        return None


def generate_caption(model, processor, image, prompt, device):
    """Generate a caption for the given image using the model."""
    try:
        # Construct a chat message with an image element and a text prompt.
        messages = [{
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": prompt}
            ]
        }]
        # Generate the input text using the processor's chat template.
        input_text = processor.apply_chat_template(messages, add_generation_prompt=True)
        
        # Prepare inputs including both the image and the text.
        inputs = processor(
            images=image,
            text=input_text,
            add_special_tokens=False,
            return_tensors="pt"
        ).to(device)
        
        with torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=150)
        
        caption = processor.decode(output[0], skip_special_tokens=True).strip()
        return caption
    except Exception as e:
        print(f"Error generating caption: {e}")
        return "Error"


def main():
    parser = ArgumentParser()
    parser.add_argument("--hf_token", type=str, required=True, help="HuggingFace token")
    parser.add_argument("--model_path", type=str, default="deepseek-ai/deepseek-vl2-tiny", help="Hugging Face model ID or local path")
    parser.add_argument("--csv_file", type=str, required=True, help="CSV file with image data")
    parser.add_argument("--results_folder", type=str, default="./results", help="Folder to save results")
    parser.add_argument("--results_file", type=str, default="caption_results_llama.json", help="Output JSON file")
    parser.add_argument("--image_folder", type=str, required=True, help="Folder containing images")
    parser.add_argument("--model_source", type=str, default="hf", help="'local' or 'hf'")
    parser.add_argument("--quantized", action="store_true", help="Use 4-bit quantization")
    args = parser.parse_args()

    # Log in to Hugging Face if using remote model.
    login(token=args.hf_token)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Create results folder if it doesn't exist.
    if not os.path.exists(args.results_folder):
        os.makedirs(args.results_folder, exist_ok=True)
        print(f"Created results folder: {args.results_folder}")
    
    # Load the processor and model.
    processor = AutoProcessor.from_pretrained(args.model_path, trust_remote_code=True)
    
    if args.quantized:
        # Configure BitsAndBytes for quantized model loading
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16
        )
        model = AutoModelForImageTextToText.from_pretrained(
            args.model_path,
            quantization_config=bnb_config,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True
        )
    else:
        model = AutoModelForImageTextToText.from_pretrained(
            args.model_path,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
    model.to(device)

    # Load image captions from CSV.
    csv_captions = {}
    samples = []
    with open(args.csv_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            img_id = os.path.splitext(row["Image"])[0]
            csv_captions[img_id] = {
                "csv_simple": row["simple_Caption"],
                "csv_emphatic": row["emphatic_Caption"]
            }
            samples.append({"id": img_id})

    # Map image IDs to file paths.
    image_files = glob(os.path.join(args.image_folder, "*.*"))
    valid_exts = [".jpg", ".jpeg", ".png", ".webp"]
    id_to_path = {
        os.path.splitext(os.path.basename(p))[0]: p
        for p in image_files if os.path.splitext(p)[1].lower() in valid_exts
    }

    # Define prompts for caption generation.
    prompts = {
        "model_simple": "Describe this image concisely and objectively.",
        "model_empathetic": "Describe this image in a compassionate, human-centered way."
    }

    results = []
    for sample in samples:
        sample_id = sample["id"]
        image_path = id_to_path.get(sample_id)
        if not image_path:
            print(f"Skipping {sample_id}: image not found.")
            continue
        
        image = resize_image(image_path)
        if image is None:
            continue
        
        result_entry = {
            "id": sample_id,
            "image_path": image_path,
            "csv_captions": csv_captions.get(sample_id, {}),
            "model_captions": {}
        }
        
        for cap_type, prompt in prompts.items():
            caption = generate_caption(model, processor, image, prompt, device)
            result_entry["model_captions"][cap_type] = caption
        
        results.append(result_entry)
        
        # Save intermediate progress.
        results_file_path = os.path.join(args.results_folder, args.results_file)
        with open(args.results_file, "w") as f:
            json.dump(results, f, indent=4)
    
    print(f"Processed {len(results)} images.")


if __name__ == "__main__":
    main()