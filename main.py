"""
Example for a BLE 4.0 Server using a GATT dictionary of services and
characteristics
"""
import sys
import logging
import asyncio
import threading
import queue
import time
import paho.mqtt.client as mqtt
import typedef_pb2


from typing import Any, Dict, Union

from bless import (  # type: ignore
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)

server = BlessServer

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(name=__name__)

trigger: Union[asyncio.Event, threading.Event]
if sys.platform in ["darwin", "win32"]:
    trigger = threading.Event()
else:
    trigger = asyncio.Event()


def read_request(characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
    logger.debug(f"Reading {characteristic.value}")
    return characteristic.value


def write_request(characteristic: BlessGATTCharacteristic, value: Any, **kwargs):
    logger.debug(f"Writing {value} to {characteristic}")
    characteristic.value = value
    logger.debug(f"Char value set to {characteristic.value}")
    if characteristic.value == b"\x0f":
        logger.debug("Nice")
        trigger.set()

def get_characteristic_by_uuid(val: Any):
    print(val)
    if not isinstance(val, str):
        val = str(val)  # Convert non-string input to string
    characteristic = server.get_characteristic("51FF12BB-3ED8-46E5-B4F9-D64E2FEC021B")
    logger.debug(f"Char value set to {characteristic.value}")
    byte_val = bytearray(val, 'utf-8')  # Convert string to byte array
    write_request(characteristic, byte_val)


###### MQTT SETUP#########

data_queue = queue.Queue()
def on_connect(client, _, __, rc):
    print("Connected with return: ", rc)
    #Subscribe topic
    client.subscribe("hub/ble")

def on_message(_ , __, message):
    print("Recieved data from topic:", message.topic)
    _buff = typedef_pb2.Buffer()
    _buff.ParseFromString(message.payload)
    if _buff.receiver == typedef_pb2.User_t.Value("Ble"):
        print("<-- ", message.topic," : ",_buff)
        data_queue.put(_buff)

def mqtt_publish(topic, message):
    data = message.SerializeToString()
    client.publish(topic, data)
    print("--> ", topic," : ",message)

client = mqtt.Client(client_id="hub-ble") 
client.on_connect = on_connect
client.on_message = on_message

client.connect("127.0.0.1", 1883, 60)

def control_device(device_name, status):
    logger.debug(f"Controlling device: Name={device_name}, Status={status}")

def data_to_device(temp):
    global buffer
    for temp_led in temp.led:
        for buffer_led in buffer.led:
            if buffer_led.name == temp_led.name:
                logger.debug(f"Found matching LED: {temp_led.name}")
                control_device(buffer_led.name, temp_led.status)

def sync_device():
    global buffer  
    sync_buffer = typedef_pb2.Buffer()

    sync_buffer.sender = typedef_pb2.User_t.Ble
    sync_buffer.receiver = typedef_pb2.User_t.Hub
    sync_buffer.cotroller = typedef_pb2.User_t.Ble
    sync_buffer.mac_hub = "8xff"

    for led in buffer.led:
        sync_buffer.led.append(led)

    mqtt_publish("hub/ble", sync_buffer)



buffer = typedef_pb2.Buffer()

def initialize_buffer():
    led1 = typedef_pb2.Led_t()
    led1.mac = 123
    led1.ep = 1
    led1.status = False
    led1.name = "light 1"
    buffer.led.append(led1)

    led2 = typedef_pb2.Led_t()
    led2.mac = 123
    led2.ep = 2
    led2.status = False 
    led2.name = "light 2"
    buffer.led.append(led2)

    led3 = typedef_pb2.Led_t()
    led3.mac = 123
    led3.ep = 3
    led3.status = False  
    led3.name = "light 3"
    buffer.led.append(led3)

initialize_buffer()

def mqtt_thread():
    global buffer 
    while True:
        client.loop()
        if not data_queue.empty():
            temp = data_queue.get()

            if temp and isinstance(temp, typedef_pb2.Buffer):
                if temp.sender == typedef_pb2.User_t.Hub:
                    if not temp.led and not temp.sw:
                        sync_device()
                    data_to_device(temp)
                
        time.sleep(0.1) 

mqtt_thread = threading.Thread(target=mqtt_thread)
mqtt_thread.daemon = True 
mqtt_thread.start()


check_system = True
buff = typedef_pb2.Buffer()
buff.sender = typedef_pb2.User_t.Ble
buff.receiver = typedef_pb2.User_t.Hub
buff.mac_hub = "8xff"

async def run(loop):
    global server 
    trigger.clear()

    # Instantiate the server
    gatt: Dict = {
        "A07498CA-AD5B-474E-940D-16F1FBE7E8CD": {
            "51FF12BB-3ED8-46E5-B4F9-D64E2FEC021B": {
                "Properties": (
                    GATTCharacteristicProperties.read
                    | GATTCharacteristicProperties.write
                    | GATTCharacteristicProperties.indicate
                ),
                "Permissions": (
                    GATTAttributePermissions.readable
                    | GATTAttributePermissions.writeable
                ),
                "Value": None,
            }
        },
        "5c339364-c7be-4f23-b666-a8ff73a6a86a": {
            "bfc0c92f-317d-4ba9-976b-cc11ce77b4ca": {
                "Properties": GATTCharacteristicProperties.read,
                "Permissions": GATTAttributePermissions.readable,
                "Value": bytearray(b"\x69"),
            }
        },
    }
    my_service_name = "Pi Service"
    server = BlessServer(name=my_service_name, loop=loop)
    server.read_request_func = read_request
    server.write_request_func = write_request

    await server.add_gatt(gatt)
    await server.start()
    logger.debug(server.get_characteristic("51FF12BB-3ED8-46E5-B4F9-D64E2FEC021B"))
    logger.debug("Advertising")
    logger.info(
        "Write '0xF' to the advertised characteristic: "
        + "51FF12BB-3ED8-46E5-B4F9-D64E2FEC021B"
    )
    if trigger.__module__ == "threading":
        trigger.wait()
    else:
        await trigger.wait()
    await asyncio.sleep(2)
    logger.debug("Updating")
    server.get_characteristic("51FF12BB-3ED8-46E5-B4F9-D64E2FEC021B").value = bytearray(
        b"i"
    )
    server.update_value(
        "A07498CA-AD5B-474E-940D-16F1FBE7E8CD", "51FF12BB-3ED8-46E5-B4F9-D64E2FEC021B"
    )
    await asyncio.sleep(5)
    await server.stop()
    return server

#Initial bluetooth service
loop = asyncio.get_event_loop()
loop.run_until_complete(run(loop))
