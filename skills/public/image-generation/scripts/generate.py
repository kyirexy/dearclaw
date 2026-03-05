import base64
import os
import time

import requests
from PIL import Image


def validate_image(image_path: str) -> bool:
    """
    Validate if an image file can be opened and is not corrupted.

    Args:
        image_path: Path to the image file

    Returns:
        True if the image is valid and can be opened, False otherwise
    """
    try:
        with Image.open(image_path) as img:
            img.verify()  # Verify that it's a valid image
        # Re-open to check if it can be fully loaded (verify() may not catch all issues)
        with Image.open(image_path) as img:
            img.load()  # Force load the image data
        return True
    except Exception as e:
        print(f"Warning: Image '{image_path}' is invalid or corrupted: {e}")
        return False


def generate_image(
    prompt_file: str,
    reference_images: list[str],
    output_file: str,
    aspect_ratio: str = "16:9",
) -> str:
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt = f.read()

    # Filter out invalid reference images
    valid_reference_images = []
    for ref_img in reference_images:
        if validate_image(ref_img):
            valid_reference_images.append(ref_img)
        else:
            print(f"Skipping invalid reference image: {ref_img}")

    if len(valid_reference_images) < len(reference_images):
        print(f"Note: {len(reference_images) - len(valid_reference_images)} reference image(s) were skipped due to validation failure.")

    # Convert aspect ratio format (16:9 -> 16:9, etc.)
    # GRSai supports: auto, 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, 5:4, 4:5, 21:9
    # Map common ratios
    aspect_ratio_map = {
        "16:9": "16:9",
        "9:16": "9:16",
        "4:3": "4:3",
        "3:4": "3:4",
        "1:1": "1:1",
        "21:9": "21:9",
    }
    gs_aspect_ratio = aspect_ratio_map.get(aspect_ratio, "auto")

    # Prepare reference images as URLs or base64
    reference_urls = []
    for ref_image in valid_reference_images:
        with open(ref_image, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        # For GRSai, we'll skip reference images in the prompt and just use the prompt
        # Reference images would need to be uploaded to a URL

    api_key = os.getenv("GRS_API_KEY")
    if not api_key:
        return "GRS_API_KEY is not set. Please set GRS_API_KEY environment variable."

    # Use GRSai API
    api_base = os.getenv("GRS_API_BASE", "https://grsai.dakka.com.cn")

    url = f"{api_base}/v1/draw/nano-banana"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    data = {
        "model": "nano-banana-2",
        "prompt": prompt,
        "aspectRatio": gs_aspect_ratio,
        "imageSize": "1K",
    }

    try:
        response = requests.post(url, headers=headers, json=data, stream=True)
        response.raise_for_status()

        # Parse stream response to get the final result
        result_data = None
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    try:
                        import json as json_module
                        json_str = line[6:]  # Remove "data: " prefix
                        data_obj = json_module.loads(json_str)
                        # Store the latest data, which will be the final result
                        result_data = data_obj
                        # Check if we have results
                        if result_data.get("results"):
                            break
                    except:
                        pass

        if result_data and result_data.get("results"):
            image_url = result_data["results"][0].get("url")
            if image_url:
                # Download the image
                img_response = requests.get(image_url)
                img_response.raise_for_status()
                with open(output_file, "wb") as f:
                    f.write(img_response.content)
                return f"Successfully generated image to {output_file}"

        # If no results yet, try polling for result
        if result_data and result_data.get("id"):
            task_id = result_data["id"]
            result_url = f"{api_base}/v1/draw/result"
            max_retries = 30
            for i in range(max_retries):
                time.sleep(2)
                poll_response = requests.post(
                    result_url,
                    headers=headers,
                    json={"id": task_id}
                )
                poll_response.raise_for_status()
                poll_data = poll_response.json()
                if poll_data.get("data", {}).get("status") == "succeeded":
                    image_url = poll_data["data"]["results"][0].get("url")
                    if image_url:
                        img_response = requests.get(image_url)
                        img_response.raise_for_status()
                        with open(output_file, "wb") as f:
                            f.write(img_response.content)
                        return f"Successfully generated image to {output_file}"
                elif poll_data.get("data", {}).get("status") == "failed":
                    failure_reason = poll_data.get("data", {}).get("failure_reason", "Unknown error")
                    return f"Failed to generate image: {failure_reason}"

            return f"Timeout waiting for image generation. Task ID: {task_id}"

        return f"Failed to generate image: {result_data}"

    except requests.exceptions.RequestException as e:
        return f"Error calling GRSai API: {e}"
    except Exception as e:
        return f"Error generating image: {e}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate images using GRSai API (nano-banana)")
    parser.add_argument(
        "--prompt-file",
        required=True,
        help="Absolute path to JSON prompt file",
    )
    parser.add_argument(
        "--reference-images",
        nargs="*",
        default=[],
        help="Absolute paths to reference images (space-separated)",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Output path for generated image",
    )
    parser.add_argument(
        "--aspect-ratio",
        required=False,
        default="16:9",
        help="Aspect ratio of the generated image",
    )

    args = parser.parse_args()

    try:
        print(
            generate_image(
                args.prompt_file,
                args.reference_images,
                args.output_file,
                args.aspect_ratio,
            )
        )
    except Exception as e:
        print(f"Error while generating image: {e}")
