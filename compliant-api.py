from flask import Flask, request, jsonify
import google.generativeai as genai
import os
import typing_extensions as typing
import tempfile
import json

app = Flask(__name__)

# Define the compliance response schema
class ComplianceResponse(typing.TypedDict):
    compliant: bool
    reason: str

# Configure the Gemini API key
genai.configure(api_key=os.environ["G_API_KEY"])

# Set up the model
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction="""You are an AI system designed to evaluate product listings for compliance with platform regulations. Your role is to analyze both product descriptions and associated image to ensure complete compliance.\nProhibited Categories\nProducts and images are non-compliant if they contain or relate to:\n\nIntoxicants\n\nAlcoholic beverages\nTobacco products and smoking accessories\nRecreational drugs or drug paraphernalia\nVaping products and accessories\n\n\nAdult/NSFW Content\n\nExplicit sexual content\nSuggestive or provocative imagery\nAdult toys or related accessories\n\n\nGambling\n\nGambling devices\nLottery tickets\nBetting systems\nVirtual gambling items or currency\n\n\n\nEvaluation Process\n\nDescription Analysis\n\nReview product title and description\nCheck for explicit mentions or euphemisms for prohibited items\nIdentify attempts to circumvent restrictions through coded language\n\n\nImage Analysis\n\nExamine product image for prohibited content\nFlag mismatches between descriptions and images\nCheck for hidden or obscured prohibited elements\n\n\nCross-Reference\n\nCompare description against images for consistency\nFlag cases where compliant descriptions have non-compliant images or vice versa. Give short and concise reason for any non-compliance."""
)

blacklist_words = [
    "alcohol", "weed", "marijuana", "cannabis", "vodka", "whiskey", "beer",
    "tobacco", "cigarettes", "vape", "e-cigarettes", "smoking", "heroin",
    "cocaine", "meth", "opioids", "ecstasy", "narcotics", "gambling", "casino",
    "betting", "poker", "lottery", "nudity", "porn", "NSFW",
    "prostitution", "sex", "fetish", "lingerie", "stripper",
    "naked", "drugs", "hashish", "amphetamine",
    "explosives", "terrorism", "extremism", "illegal", "sutta", "daaru",
    "maal", "charsi", "ganja", "nashe", "chirkut", "tharki", "kamina",
    "behenchod", "madarchod", "chutiya", "harami", "bhosad", "bakchodi",
    "gaand", "suar", "hijra", "bastard", "rape", "molest", "dalali", "nanga",
    "lauda", "kidnap", "dacoit", "firangi", "dhamki", "suicide", "murders",
    "lootera", "darinda", "lafanga", "sadakchap", "gunda", "nashedi", "bawali",
    "opium", "hookah"
]

# Blacklisted words check
def contains_blacklisted_word(input_string):
    """
    Checks if any blacklisted word is present in the input string.
    
    Args:
        input_string (str): The string to check.
    
    Returns:
        bool: True if a blacklisted word is found, False otherwise.
    """

    # Normalize the string for case-insensitive matching
    normalized_string = input_string.lower()
    
    return any(word in normalized_string for word in blacklist_words)


@app.route('/check_compliance', methods=['POST'])
def check_compliance():

    image = request.files.get('photo')
    name = request.form.get('name')
    description = request.form.get('description')
    print(f"{request.files=}")
    print(f"{request.form=}")

    if(contains_blacklisted_word(f"{name} {description}")):
        print("Blacklisted word found")
        return jsonify({"compliant": False, "reason": "Does not comply with our Term of Service"})

    if not image or not description:
        print("Image and description are required")
        return jsonify({"error": "Image and description are required"}), 400

    # Ensure the image is in a supported format
    if image.mimetype not in ["image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"]:
        print("Unsupported image format")
        return jsonify({"error": "Unsupported image format"}), 400

    # Save the uploaded image temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(image.filename)[1]) as temp_file:
        image.save(temp_file.name)  # Save the image file to the temporary location
        temp_file_path = temp_file.name

    try:
        # Upload the image to Gemini's File API
        myfile = genai.upload_file(temp_file_path)

        # Prepare the prompt with the description and image reference
        prompt = ["Analyze the following product description and image for compliance with platform regulations(given in system prompt):", "\n\n", myfile, "\n\n", f"Description: {name} {description}"]

        # Generate a response using the model with a typed schema
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=ComplianceResponse  # custom schema class
            )
        )
        print(response.text)

        # Access the response data
        if response.candidates[0].finish_reason.name == 'SAFETY':
            # Extract safety ratings and find categories with a probability higher than "NEGLIGIBLE"
            non_negligible_ratings = [
                rating for rating in response.candidates[0].safety_ratings
                if rating.probability.name != "NEGLIGIBLE"
            ]
            
            # If we have non-negligible ratings, format the output as requested
            if non_negligible_ratings:
                reason = ', '.join(f"{rating.category.name[14:]} ({rating.probability.name})" for rating in non_negligible_ratings)
                result = {
                    "compliant": False,
                    "reason": reason
                }
                return jsonify(result)
            else:
                # In case no non-negligible ratings are found
                return jsonify({"compliant": True})
        else:
            try:
                response_data = json.loads(response.text.strip())
                return jsonify(response_data)
            except json.JSONDecodeError:
                # Handle the case where response.text is not valid JSON
                return jsonify({"error": "Invalid JSON response from the model"})

    except:
        return jsonify({"compliant": False, "reason": "Does not comply with our Term of Service"})
    finally:
        # Clean up the temporary file
        os.remove(temp_file_path)

# Run the Flask app
if __name__ == '__main__':
    app.run(debug=False)
