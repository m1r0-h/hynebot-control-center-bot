# Bot control program without motor control

import os
import time
import socketio
import requests
from dotenv import load_dotenv
from datetime import datetime
import threading


def initialize_connection(): # Load the necessary variables from the .env file 
    # Load environment variables from .env file
    load_dotenv()

    # Access the variables
    bot_login_token = os.getenv("BOT_LOGIN_TOKEN", "")
    server_verify_token = os.getenv("SERVER_VERIFY_TOKEN", "")
    verify_ssl = os.getenv("VERIFY_SSL", "True").lower() == "true"
    server_address = os.getenv("SERVER_ADDRESS", None)

    # Create a http session
    http_session = requests.Session()
    http_session.verify = verify_ssl

    # Create a Socket.IO client
    sio = socketio.Client(http_session=http_session)

    return sio, server_address, bot_login_token, server_verify_token


def register_events(sio, server_verify_token): # Handle events

    verified = False # Boolean to check if the server has been verified

    @sio.event
    def connect():
        print("Connected to server, waiting for token...")

    @sio.event
    def connectionError(data):
        print("Connection error")

    # Event to handle disconnection
    @sio.event
    def disconnect():
        print("Disconnected from server")

    # Event to handle server check
    @sio.event
    def auth(data):
        nonlocal verified # Point to the non-local variable "verified" to modify it instead of making a whole new local "verified" variable
        received_token = data.get("token")
        if received_token == server_verify_token:
            print("Correct token received, server verified.")
            verified = True
        else:
            print("Incorrect token, disconnecting...")
            sio.disconnect()

    # Event to handle control messages
    @sio.event
    def controlMessage(data):
        nonlocal verified 
        if verified:
            global message_received # Point to the global "message_received" variable

            # Check message format
            if (not data) or ("time" not in data) or ("controlMessage" not in data):
                sio.emit("botErrorMessage", {"errorMessage": "Invalid control message"})
                return

            # Check contol message time - If the message is too old or new, ignore it
            now = datetime.now()
            current_time = int(now.timestamp() * 1000)
            if (data.get("time") < current_time - 1000): # If message is too old
                sio.emit("botErrorMessage", {"errorMessage": "The message was received too late. The delay is too much."})
                return
            elif (data.get("time") > current_time + 1000): # If message is too new
                print(data.get("time"))
                print(current_time + 1000)
                sio.emit("botErrorMessage", {"errorMessage": "Invalid message time"})
                return

            # Message is ok
            message_received = True
            sio.emit("clearBot") # Clear old error messages

            # Check the control message and do something accordingly
            if (len(data["controlMessage"]) == 0): # No control message
                return
            
            # The bot can be made to react to the control message in any way
            # TODO add reactions
            # Example reactions...

            # controlMessage includes "w" key - Go forward
            if ("controlMessage" in data and "w" in data["controlMessage"]):
                if data["controlMessage"]["w"] == True:
                    print(str(now) + " - forward")
            # Go left
            if "controlMessage" in data and "a" in data["controlMessage"]:
                if data["controlMessage"]["a"] == True:
                    print(str(now) + " - left")
            # Go back
            if "controlMessage" in data and "s" in data["controlMessage"]:
                if data["controlMessage"]["s"] == True:
                    print(str(now) + " - backwards")
            # Go right
            if "controlMessage" in data and "d" in data["controlMessage"]:
                if data["controlMessage"]["d"] == True:
                    print(str(now) + " - right")
        else:
            print("Message received before verification.")
            print("Disconnecting...")
            sio.disconnect()

    # Event to handle latiency test
    @sio.event
    def latencyTestRequest(data):
        if not data or "startTime" not in data:
            return
        sio.emit("latencyTestResult", {"startTime": data["startTime"]}) # Corresponds to the delay test message

    # Event to handle error messages
    @sio.event
    def errorMessage(data):
        print(data.get("errorMessage")) 


# The idea of ​​this function is to run in the background
# and stop the bot if there are no new control messages
def check_for_messages():
    while True:
        global message_received
        time.sleep(0.5)  # Check interval
        if not message_received:
            print("No message received - Stop bot.")
        else:
            message_received = False  # Reset the "message_received" flag after checking


def connect_to_server():
    try:
        # Load the necessary variables from the .env file 
        sio, server_address, bot_login_token, server_verify_token = initialize_connection()

        # Register event handlers
        register_events(sio, server_verify_token)

        # Connect to the server
        sio.connect(server_address, headers={"Authorization": f"Bearer {bot_login_token}"})

        # Clean old error messages
        sio.emit("clearBot")

        # Start the message checking thread
        thread = threading.Thread(target=check_for_messages)
        thread.daemon = True  # Automatically terminate thread when the main program exits
        thread.start()

        # TODO Send sensor data
        # Example...
        data = {"Sensor1": "1.123", "Sensor2": "3567123323211328", "Sensor3": "0.23"} # Make data
        sensorTime = int(time.time() * 1000) # Timestamp
        sio.emit("sensorData", {"time": sensorTime, "sensorData": data}) # Send sensor data
        
        # Wait for new messages
        sio.wait()
    except Exception as e:
        print(f"Failed to connect: {e}")

#Global variables
message_received = False # For stopping the bot if there are no new control messages (check_for_messages)

if __name__ == "__main__":
    connect_to_server()