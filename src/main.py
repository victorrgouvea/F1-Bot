import os
from flask import Flask, jsonify, request
from mangum import Mangum
from asgiref.wsgi import WsgiToAsgi
from discord_interactions import verify_key_decorator
import json
import datetime
import boto3
from stripe import checkout
from src.utils import generate_schedule_embed, next_gp, formatted_driver_standings, formatted_constructor_standings
from src.stripe_payment import generate_payment_link, check_payment_status

# Uncomment for local testing
# from dotenv import load_dotenv
# load_dotenv()

# Change for local testing
# SCHEDULE_PATH = "../data/schedule"
SCHEDULE_PATH = "data/schedule"

DISCORD_PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY")

s3 = boto3.client("s3")
BUCKET_NAME = 'f1-bot-channels'

app = Flask(__name__)
asgi_app = WsgiToAsgi(app)
handler = Mangum(asgi_app)

@app.route("/", methods=["POST"])
async def interactions():
    print(f"Request: {request.json}")
    raw_request = request.json
    return interact(raw_request)

def update_channels(raw_request):
    channel = raw_request["channel"]
    channel_id = channel["id"]
    chat_id = channel.get("guild_id")
    channel_type = "guild"
    if chat_id is None:
        chat_id = channel["recipients"][0]["id"]
        channel_type = "dm"
    
    response = s3.get_object(Bucket=BUCKET_NAME, Key='guild_channel.json')
    data = json.loads(response['Body'].read())
    
    # Check if the command is subscribe or unsubscribe
    # doing it here to avoid getting s3 object twice 
    if raw_request["data"]["name"] == "subscribe":
        sub = True
    elif raw_request["data"]["name"] == "unsubscribe":
        sub = False
    else:
        sub = data.get(chat_id, {}).get("sub")
        
    data[chat_id] = {
        "channel_id": channel_id,
        "channel_type": channel_type,
        "sub": True if sub is None else sub,  # True if sub is None means it's the first time
    }
    
    s3.put_object(Bucket=BUCKET_NAME, Key='guild_channel.json', Body=json.dumps(data))

# Comment decorator for local testing
@verify_key_decorator(DISCORD_PUBLIC_KEY)
def interact(raw_request):
    if raw_request["type"] == 1:
       return jsonify({"type": 1})

    data = raw_request["data"]
    command_name = data["name"]
    user_id = raw_request['member']['user']['id'] if 'guild' in raw_request else raw_request['user']['id']
    user_name = raw_request['member']['user']['global_name'] if 'guild' in raw_request else raw_request['user']['global_name']
    message_content = "I don't understand this command, try again!"
    
    # save_user_name(user_id, user_name)
    update_channels(raw_request)
    
    if command_name == "hello":
        message_content = "Hello there!"
    elif command_name == "about":
        message_content = "I am a bot made to help you with your F1 needs!"
    elif command_name == "song":
        message_content = "The Dutch National Anthem never leaves my playlist!"
    elif command_name == "winner":
        message_content = "I don't have this info right now, but it should be Max Verstappen..."
    elif command_name == "subscribe":
        message_content = "You are now subscribed to the Grand Prix schedule updates!"
    elif command_name == "unsubscribe":
        message_content = "You are now unsubscribed from the Grand Prix schedule updates!"
    elif command_name == "ticket":
        payment_link = generate_payment_link(user_id)
        message_content = f"Here is the link to buy your F1 ticket:\n{payment_link}"
    elif command_name == "race":
        if check_payment_status(user_id):
            message_content = "Welcome to the race, thank you for buying your ticket!"
        else:
            message_content = "You need to buy a ticket to access the race! Type /ticket to get the payment link."
    elif command_name == "standings":
        tag = data["options"][0]
        if tag["name"] == 'drivers':
            standings = formatted_driver_standings()
            
            content = "Here are the current driver standings!"
            embed = {
                "title": "Driver Standings",
                "url": f"https://www.formula1.com/en/results/{datetime.date.today()}/drivers.html",
                "color": 16711680,
                "fields": standings,
            }

        elif tag["name"] == 'constructors':
            standings = formatted_constructor_standings()
            
            content = "Here are the current constructor standings!"
            embed = {
                "title": "Constructor Standings",
                "url": f"https://www.formula1.com/en/results/{datetime.date.today()}/team.html",
                "color": 16711680,
                "fields": standings,
            }
            
        response_data = {
            "type": 4,
            "data": {
                "content": content,
                "embeds": [embed]
            }
        }
        return jsonify(response_data)

    elif command_name == "gp":
        tag = data["options"][0]
        if tag["name"] == 'location':
            location = tag["options"][0]["value"]
            content = "Here is the schedule for the requested Grand Prix weekend!"
        elif tag["name"] == 'next':
            # da pra buscar isso uma vez só de tempos em tempos e guardar em algum lugar
            location = next_gp(SCHEDULE_PATH)[0]
            content = "Here is the schedule for the next Grand Prix weekend!"
            
        embed = generate_schedule_embed(SCHEDULE_PATH, location)
        
        if "error" in embed:
            message_content = "Location name not found, try again with a valid Grand Prix location!"
        else:
            response_data = {
                "type": 4,
                "data": {
                    "content": content,
                    "embeds": [embed]
                }
            }
            return jsonify(response_data)
        
    response_data = {
        "type": 4,
        "data": {"content": message_content}
    }
        
    return jsonify(response_data)
    
if __name__ == "__main__":
    app.run(debug=True)