import pandas as pd
import json
import re
import argparse


def load_metadata(metadata_file):
    """Load metadata from the JSON file and convert it to a dictionary."""
    try:
        with open(metadata_file, "r") as f:
            metadata_list = json.load(f)
        # Convert the list of metadata to a dictionary with `id` as the key
        metadata_dict = {item["id"]: item for item in metadata_list}
        return metadata_dict
    except Exception as e:
        print(f"Error loading metadata file: {e}")
        return {}
    
def extract_question_answer(assistant_content):
    """Extract the question and answer from the assistant content."""
    try:
        # Match the 'Question' and 'Answer' sections
        question_match = re.search(r"Question:\s*(.*?)(?:\n|Answer:)", assistant_content, re.DOTALL)
        answer_match = re.search(r"Answer:\s*(.*)", assistant_content, re.DOTALL)

        # Extract the content if the match is found, otherwise set to None
        question = question_match.group(1).strip() if question_match else None
        answer = answer_match.group(1).strip() if answer_match else None

        return question, answer
    except Exception as e:
        print(f"Error extracting question and answer: {e}")
        return None, None


def postprocess_csv_with_metadata(input_csv, metadata_json, output_json):
    """Postprocess the CSV file using metadata and save the output to JSON."""
    try:
        # Read the metadata
        metadata = load_metadata(metadata_json)

        # Read the CSV file
        df = pd.read_csv(input_csv)

        # Initialize the output dictionary
        processed_data = {}

        for _, row in df.iterrows():
            try:
                # Extract ID and attribute
                unique_id = row["ID"]
                attribute = row["attribute"]
                full_response = row["generated_question"]

                # Extract content after the 'assistant' keyword
                match = re.search(r"assistant\s*(.*)", full_response, re.DOTALL)
                if match:
                    assistant_content = match.group(1).strip()
                else:
                    assistant_content = None

                # Extract question and answer
                question, answer = extract_question_answer(assistant_content) if assistant_content else (None, None)

                # Use the description from metadata
                description = metadata.get(unique_id, {}).get("image_description", "No description provided")

                # Add to the processed data dictionary
                processed_data[unique_id] = {
                    "attribute": attribute,
                    "image_description": description,
                    # "Q-A pair": assistant_content,  # Keep Q&A together
                    "question": question,
                    "answer": answer
                }
            except Exception as e:
                print(f"Error processing ID {row['ID']}: {e}")

        # Save to JSON
        with open(output_json, "w") as json_file:
            json.dump(processed_data, json_file, indent=4)
        print(f"Processed data saved to {output_json}")

    except Exception as e:
        print(f"Error processing the file: {e}")

if __name__ == "__main__":
    # Argument parser
    parser = argparse.ArgumentParser(description="Postprocess CSV with metadata.")
    parser.add_argument("--input_csv", type=str, required=True, help="Path to the input CSV file.")
    parser.add_argument("--metadata_json", type=str, required=True, help="Path to the metadata JSON file.")
    parser.add_argument("--output_json", type=str, required=True, help="Path to the output JSON file.")
    args = parser.parse_args()
    # File paths
    input_csv = args.input_csv  # Input CSV file
    metadata_json = args.metadata_json  # Metadata JSON file
    output_json = args.output_json  # Output JSON file
    # Postprocess the CSV file using metadata
    postprocess_csv_with_metadata(input_csv, metadata_json, output_json)

# The script loads metadata from a JSON file, processes a CSV file containing generated questions, and saves the processed data to a new JSON file. It extracts relevant information such as question, answer, and image description, and handles errors.

# To run the script, use the following command:
# python eval2_QA_generation_postprocessing.py \
#     --input_csv <input_csv> \
#     --metadata_json <metadata_json> \
#     --output_json <output_json>
