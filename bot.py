# Does not work well. Attempt to add bot motor control based on Robert's codes
# Can move the bot, but the motors take a long time to respond, if they respond at all.
import os
import time
import socketio
import requests
from dotenv import load_dotenv
from datetime import datetime
import threading

#Imprts related to Trinamic
from serial import Serial
import TMCL
import pymodbus
# from pymodbus.pdu import ModbusRequest
from pymodbus.client import ModbusSerialClient
# from pymodbus.transaction import ModbusRtuFramer

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException
from pymodbus.pdu import ExceptionResponse
from pymodbus.transaction import (
    #    ModbusAsciiFramer,
    #    ModbusBinaryFramer,
    ModbusRtuFramer,
    
)

def initialize_connection(): # Load the necessary variables from the .env file 
    # Load environment variables from .env file
    load_dotenv()

    # Access the variables
    bot_login_token = os.getenv("BOT_LOGIN_TOKEN", "")
    server_verify_token = os.getenv("SERVER_VERIFY_TOKEN", "")
    verify_ssl = os.getenv("VERIFY_SSL", "True").lower() == "true"
    server_address = os.getenv("SERVER_ADDRESS", None)
    trinamic_port = os.getenv("TRINAMIC_PORT", "")
    modbus_port = os.getenv("MODBUS_PORT", "")

    # Create a http session
    http_session = requests.Session()
    http_session.verify = verify_ssl

    # Create a Socket.IO client
    sio = socketio.Client(http_session=http_session)

    # Open a serial port to connect to the bus
    serial_port = Serial(trinamic_port)
    global bus
    bus = TMCL.connect(serial_port)
    global module
    module = bus.get_module(1)

    #init ModBus # alustus
    port = modbus_port
    global client
    client = ModbusSerialClient(
        method = 'rtu'
        ,port=port
        ,baudrate=9600
        ,parity = 'E'
        ,timeout=1
        )
    client.connect()

    return sio, server_address, bot_login_token, server_verify_token

def setup_motors(): 

    global motorl
    global motorf
    global motorr
    global motorhlr
    global motorhud
    global module

    motorl = module.get_motor(3)
    motorf = module.get_motor(4)
    motorr = module.get_motor(5)
    motorhlr = module.get_motor(0)
    motorhud = module.get_motor(1)

    motorl.axis.max_positioning_speed = 100000
    motorf.axis.max_positioning_speed = 100000
    motorr.axis.max_positioning_speed = 100000
    motorhlr.axis.max_positioning_speed = 51200
    motorhud.axis.max_positioning_speed = 512000

    motorl.axis.max_accelleration= 500000
    motorf.axis.max_accelleration= 500000
    motorr.axis.max_accelleration= 500000
    motorhlr.axis.max_accelleration= 500000
    motorhud.axis.max_accelleration= 500000

    motorl.axis.max_current=200
    motorf.axis.max_current=200
    motorr.axis.max_current=200
    motorhlr.axis.max_current=200
    motorhud.axis.max_current=200

    motorl.axis.standby_current=88
    motorf.axis.standby_current=88
    motorr.axis.standby_current=88
    motorhlr.axis.standby_current=88
    motorhud.axis.standby_current=88

    global m0HomePos
    global m1HomePos
    global m2HomePos
    m0HomePos = homeRotatingMotor(3)
    m1HomePos = homeRotatingMotor(4)
    m2HomePos = homeRotatingMotor(5)

    return


def homeRotatingMotor(motorCode):
    global bus
    #print("motorCode is: ", motorCode)
    changes = 0
    replySen = bus.send(1,15,(motorCode + 1),0,0)
    lastvalue = replySen.value

    pos0 = None
    pos1 = None

    bus.send(1,2,0,motorCode,30000)

    #print("last value is: ",lastvalue)

    while(changes < 2):
        replySen = bus.send(1,15,(motorCode -2),0,0)
        #commands["forward"] == 0
        if replySen.value == 1 and  lastvalue == 0:
            changes = 1
            #print(replySen.valuemotorCode + 1)
            replyPos = bus.send(1,6,1,motorCode,0)
            pos0 = replyPos.value
            print(pos0)
           
        if replySen.value == 0 and  lastvalue == 1 and changes == 1:
            changes = 2
            replyPos = bus.send(1,6,1,motorCode,0)
            pos1 = replyPos.value
            print(pos1)

        lastvalue = replySen.value

    bus.send(1,3,0,motorCode,0)
    home = int((pos0 + pos1)/ 2)
    bus.send(1,4,0,motorCode,home)

    return home

def inCommandedPosition():
    global bus
    
    m0CurPos = bus.send(1,6,1,3,0) #get cyrrent position of motor
    m1CurPos = bus.send(1,6,1,4,0)
    m2CurPos = bus.send(1,6,1,5,0)

    m0ComPos = bus.send(1,6,0,3,0) #get commanded/target position of motor
    m1ComPos = bus.send(1,6,0,4,0)
    m2ComPos = bus.send(1,6,0,5,0)

    if m0ComPos.value == m0CurPos.value and m1ComPos.value == m1CurPos.value and m2ComPos.value == m2CurPos.value:
        return True
    else:
        return False

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
            if (data.get("time") < current_time - 1000):
                sio.emit("botErrorMessage", {"errorMessage": "The message was received too late. The delay is too much."})
                return
            elif (data.get("time") > current_time + 1000):
                sio.emit("botErrorMessage", {"errorMessage": "Invalid message time"})
                return
            
            # Message is ok
            message_received = True
            sio.emit("clearBot", {}) # Clear old error messages

            global motorl
            global motorf
            global motorr
            global motorhlr
            global motorhud
            global client
            global prevCommand
            global notInPos

            # Check the control message and do something accordingly
            if prevCommand != data["controlMessage"]:
                notInPos = True

            if notInPos:
                if (len(data["controlMessage"]) == 0):
                    print("no command")
                    motorl.move_absolute(m0HomePos)
                    motorf.move_absolute(m1HomePos)
                    motorr.move_absolute(m2HomePos)
                    client.write_register(1,0,1)
                    client.write_register(1,0,2)
                    client.write_register(1,0,3)
                
                #Head up down movement
                if ("controlMessage" in data and "arrowup" in data["controlMessage"]):
                    if (data["controlMessage"]["arrowup"] and not data["controlMessage"]["arrowdown"]):
                        motorhud.rotate_left(500000)
                elif ("controlMessage" in data and "arrowdown" in data["controlMessage"]):
                    if (data["controlMessage"]["arrowdown"] and not data["controlMessage"]["arrowup"]):
                        motorhud.rotate_left(500000)
                else:
                    motorhud.stop()

                # Go forward
                if ("controlMessage" in data and "w" in data["controlMessage"]):
                    if data["controlMessage"]["w"] == True:
                        print("forward")
                        #home wheels
                        motorl.move_absolute(m0HomePos) 
                        motorf.move_absolute(m1HomePos)
                        motorr.move_absolute(m2HomePos)
                        if inCommandedPosition():
                            notInPos = False
                            client.write_register(3,1,1) #change direction forwards
                            client.write_register(1,250,1) # 
                            client.write_register(3,0,2) #change direction forwards (Fron wheel motor is mounted 180 degrees from the rest)
                            client.write_register(1,250,2) # speed
                            client.write_register(3,1,3) #change direction forwards
                            client.write_register(1,250,3) # speed

                # Go left
                if "controlMessage" in data and "a" in data["controlMessage"]:
                    if data["controlMessage"]["a"] == True:
                        print("left")
                        print(m2HomePos)
                        motorl.move_absolute(m0HomePos - 45*142*6) #rotate 45 degrees left #45 degrees * 51200/360 microsteps * 6 (because of 72:12 gearing )
                        motorf.move_absolute(m1HomePos- 90*142*6)#rotate 90 degrees left
                        motorr.move_absolute(m2HomePos + 45*142*6)#rotate 45 degrees right
                        if inCommandedPosition():
                            notInPos = False
                            client.write_register(3,0,1) #change direction backwards
                            client.write_register(1,250,1) # 
                            client.write_register(3,0,2) #change direction forwards
                            client.write_register(1,250,2) # speed
                            client.write_register(3,1,3) #change direction backwards 
                            client.write_register(1,250,3) # speed

                # Go back
                if "controlMessage" in data and "s" in data["controlMessage"]:
                    if data["controlMessage"]["s"] == True:
                        print("backwards")
                        #home wheels
                        motorl.move_absolute(m0HomePos) 
                        motorf.move_absolute(m1HomePos)
                        motorr.move_absolute(m2HomePos)
                        if inCommandedPosition():
                            notInPos = False
                            client.write_register(3,0,1) #change direction backwards
                            client.write_register(1,250,1) # 
                            client.write_register(3,1,2) #change direction backwards (Fron wheel motor is mounted 180 degrees from the rest)
                            client.write_register(1,250,2) # speed
                            client.write_register(3,0,3) #change direction backwards
                            client.write_register(1,250,3) # speed

                # Go right
                if "controlMessage" in data and "d" in data["controlMessage"]:
                    if data["controlMessage"]["d"] == True:
                        print("right")
                        motorl.move_absolute(m0HomePos - 45*142*6) #motor5rotate 45 degrees left #45 degrees * 51200/360 microsteps * 6 (because of 72:12 gearing )
                        motorf.move_absolute(m1HomePos- 90*142*6)#rotate 90 degrees left
                        motorr.move_absolute(m2HomePos + 45*142*6)#rotate 45 degrees right
                        if inCommandedPosition():
                            notInPos = False
                            client.write_register(3,1,1) #change direction forwards
                            client.write_register(1,250,1) #
                            client.write_register(3,1,2) #change direction
                            client.write_register(1,250,2) # speed
                            client.write_register(3,0,3) #change direction
                            client.write_register(1,250,3) # speed

                #Turn left while driving
                if ("controlMessage" in data and "w" in data["controlMessage"] and "a" in data["controlMessage"]):
                    #home wheels
                    if data["controlMessage"]["w"] and data["controlMessage"]["a"]:
                        print("Turn right while driving")
                        notInPos = False
                        motorl.move_absolute(m0HomePos)
                        motorf.move_absolute(m1HomePos- 45*142*6)#rotate 90 degrees left 
                        motorr.move_absolute(m2HomePos)
                        client.write_register(3,1,1) #change direction forwards            
                        client.write_register(1,250,1) # 
                        client.write_register(3,0,2) #change direction forwards (Fron wheel motor is mounted 180 degrees from the rest)
                        client.write_register(1,250,2) # speed
                        client.write_register(3,1,3) #change direction forwards
                        client.write_register(1,250,3) # speed

                #Turn right while driving
                if ("controlMessage" in data and "w" in data["controlMessage"] and "d" in data["controlMessage"]):
                    if data["controlMessage"]["w"] and data["controlMessage"]["d"]:
                        print("Turn right while driving")
                        notInPos = False
                        #home wheels
                        motorl.move_absolute(m0HomePos)
                        motorf.move_absolute(m1HomePos + 45*142*6)#rotate 90 degrees right 
                        motorr.move_absolute(m2HomePos)
                        client.write_register(3,1,1) #change direction forwards            
                        client.write_register(1,250,1) # 
                        client.write_register(3,0,2) #change direction forwards (Fron wheel motor is mounted 180 degrees from the rest)
                        client.write_register(1,250,2) # speed
                        client.write_register(3,1,3) #change direction forwards
                        client.write_register(1,250,3) # speed

                if "controlMessage" in data and "q" in data["controlMessage"]:
                    if data["controlMessage"]["q"] == True:
                        print("q")
                if "controlMessage" in data and "e" in data["controlMessage"]:
                    if data["controlMessage"]["e"] == True:
                        print("e")
            
                prevCommand = data["controlMessage"]
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

            global motorl
            global motorf
            global motorr
            global motorhlr
            global motorhud
            global client

            motorl.stop()
            motorf.stop()
            motorr.stop()
            motorhlr.stop()
            motorhud.stop()
            client.write_register(1,0,1)
            client.write_register(1,0,2)
            client.write_register(1,0,3)
        else:
            message_received = False  # Reset the flag after checking


def connect_to_server():
    try:
        # Load the necessary variables from the .env file 
        sio, server_address, bot_login_token, server_verify_token = initialize_connection()

        setup_motors()
        # Register event handlers
        register_events(sio, server_verify_token)

        # Connect to the server
        sio.connect(server_address, headers={"Authorization": f"Bearer {bot_login_token}"})

        # Clean old error messages
        sio.emit("clearBot")

        # Start the message checking thread
        thread = threading.Thread(target=check_for_messages)
        thread.daemon = True  # Allow thread to exit when the main program exits
        thread.start()

        # TODO Send sensor data
        # Example...
        data = {"Sensor1": "1.123", "Sensor2": "3567123323211328", "Sensor3": "0.23"}
        sensorTime = int(time.time() * 1000)
        sio.emit("sensorData", {"time": sensorTime, "sensorData": data})
        
        # Wait for new messages
        sio.wait()
    except Exception as e:
        print(f"Failed to connect: {e}")

# Global variables
message_received = False # For stopping the bot if there are no new control messages (check_for_messages)

prevCommand = None

m0HomePos = None
m1HomePos = None
m2HomePos = None

notInPos = True

client = None
bus = None
module = None

motorl = None
motorf = None
motorr = None
motorhlr = None
motorhud = None


if __name__ == "__main__":
    connect_to_server()