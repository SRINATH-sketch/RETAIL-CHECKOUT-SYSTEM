import joblib
import pandas as pd


# Load chatbot model
model = joblib.load("model/chatbot_model.pkl")
vectorizer = joblib.load("model/vectorizer.pkl")

# Load products
products = pd.read_csv("data/products.csv")


def chatbot_response(message):

    # Convert message into TF-IDF
    vector_message = vectorizer.transform([message])

    # Predict intent
    prediction = model.predict(vector_message)
    intent = prediction[0]

    # Find product mentioned
    product_name = None

    for product in products["name"]:
        if str(product).lower() in message.lower():
            product_name = product
            break

    # Product price
    if intent == "product_price":

        if product_name:
            product = products[
                products["name"].str.lower() == product_name.lower()
            ]

            if not product.empty:
                price = product.iloc[0]["price"]
                return f"{product_name.capitalize()} costs ₹{price} per unit."

        return "Which product's price would you like to know?"

    # Greeting
    elif intent == "greeting":
        return "Hello! How can I help you?"

    # Goodbye
    elif intent == "goodbye":
        return "Thank you! Have a nice day."

    # Product availability
    elif intent == "product_availability":

        if product_name:
            return f"Yes, we have {product_name} available in our store."

        return "Which product would you like to check?"

    # Product search
    elif intent == "product_search":

        if product_name:
            product = products[
                products["name"].str.lower() == product_name.lower()
            ]

            if not product.empty:
                return f"Yes, we have the {product_name} in our store."

        return "Which product are you looking for?"

    # Other intents for now
    else:
        return "I'm sorry, I don't understand your request."