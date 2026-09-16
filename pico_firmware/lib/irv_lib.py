import os
import ssl
import gc
from machine import Pin, Timer, reset, WDT, SoftI2C, deepsleep, lightsleep
from umqtt.robust import MQTTClient
from bme280_float import BME280
from ds18x20 import DS18X20
from onewire import OneWire
import json
import network
from time import sleep
from log_lib import * 

def read_json(file:str):
    with open(file,"r") as f:
        return json.load(f)
def write_json(file:str,data):
    with open(file,"w") as f:
        json.dump(data,f)
def get_id():
    with open("identity.txt","r") as f:
        return f.read().strip()

class DHT:
    def __init__(self, pin,name,logger):
        self.logger = logger
        self.name = name
        self.pin = Pin(pin)
        self.sensor = DS18X20(OneWire(self.pin))
        self.roms = self.sensor.scan()
        if len(self.roms)!=1:
            raise Exception("Expected 1 sensor on pin "+str(pin)+", got "+str(len(self.roms)))
    def get_temp(self):
        from time import sleep_ms
        self.sensor.convert_temp()
        sleep_ms(750)
        temp = round(self.sensor.read_temp(self.roms[0]),2)
        return temp
    def report(self):
        self.logger.print("Reporting temperature for",self.name)
        return {self.name:{"value":str(self.get_temp()),"unit":"C"}}
    def command(self,topic,msg):
        pass
class Bme280:
    def __init__(self, sda, scl,name,logger):
        self.logger = logger
        self.name = name
        self.sda = Pin(sda)
        self.scl = Pin(scl)
        self.sensor = BME280(i2c=SoftI2C(sda=sda, scl=scl))
    def get_data(self):
        temp,press,hum = self.sensor.read_compensated_data()
        dew = self.sensor.dew_point
        return temp,press,hum,dew
    def report(self):
        data = self.get_data()
        self.logger.print("Reporting BME280 data for",self.name,": Temperature")
        self.logger.print("Reporting BME280 data for",self.name,": Pressure")
        self.logger.print("Reporting BME280 data for",self.name,": Humidity")
        self.logger.print("Reporting BME280 data for",self.name,": Dew Point")
        return {self.name+"/teplota":{"value":str(data[0]),"unit":"C"},
                self.name+"/tlak":{"value":str(data[1]/1000),"unit":"kPa"},
                self.name+"/vlhkost":{"value":str(data[2]),"unit":"%"},
                self.name+"/rosny_bod":{"value":str(data[3]),"unit":"C"}}
    def command(self, topic, msg):
        pass
class Switch:
    def __init__(self, pin,name,logger,inverted=False,valueOn="1",valueOff="0"):
        self.logger = logger
        self.pin = Pin(pin,mode=Pin.OUT,pull=Pin.PULL_DOWN,value=0)
        self.name = name
        self.state = 0
        self.inverted = inverted
        self.valueOn = valueOn
        self.valueOff = valueOff
    def get_topic(self):
        return 'control/'+self.logger.name+"/"+self.name
    def get(self):
        return self.state
    def set(self,state):
        self.logger.print("Switching "+self.name+" to "+str(state))
        if not self.inverted:
            self.pin.value(bool(state))
        else:
            self.pin.value(not state)
        self.state = state
    def report(self):
        self.logger.print("Reporting state for",self.name)
        label = self.valueOn if self.get() else self.valueOff
        return {self.name:{"value":str(self.get()),"label":label}}
    def command(self, topic, msg):
        if topic == 'control/'+self.logger.name+"/"+self.name:
            self.logger.print("RELE:"+topic+":"+msg)
            if "false" in msg:
                self.set(0)
            if "true" in msg:
                self.set(1)
class BinarySensor:
    def __init__(self, pin,name,logger,inverted=False,valueOn="1",valueOff="0"):
        self.logger = logger
        self.pin = Pin(pin,mode=Pin.IN)
        self.name = name
        self.inverted = inverted
        self.valueOn = valueOn
        self.valueOff = valueOff
    def get(self):
        if self.inverted:
            return not self.pin.value()
        return bool(self.pin.value())
    def report(self):
        label = self.valueOn if self.get() else self.valueOff
        self.logger.print("Reporting state for",self.name)
        return {self.name:{"value":str(self.get()),"label":label}}
    def command(self, topic, msg):
        pass
class KIT:
    def __init__(self,pins,name,logger):
        from machine import reset_cause
        from lcd import LiquidCrystal
        self.name = name
        self.logger = logger
        self.lcd = LiquidCrystal(*pins[0:6])
        self.lcd.begin(20,4)
        self.lcd.setCursor(0,0)
        self.data = []
        last_time = read_json("last_time.json")
        self.report()
    def update_lcd(self):
        for i in range(4):
            self.lcd.setCursor(i,0)
            self.lcd.printClean(self.strings[i])
    def report(self):
        flags = ""
        try:
            os.stat("checksum_disabled.flag")
            flags = flags + "[CHECKSUM DISABLED]"
        except:
            pass
        try:
            os.stat("debug.flag")
            flags = flags + "[IN DEBUG MODE]"
        except:
            pass
        self.strings =  [f"Version: {self.logger.version["version"]}",
                            f"In: {self.logger.count_in} Out: {self.logger.count_out}",
                            f"Crashes: {read_crash_count()}",
                            f"{flags}"
                            ]
        self.update_lcd()
        return {}
    def command(self, topic, msg):
        pass
class SGReady:
    def __init__(self, pin1, pin2,name,logger,inverted1=False, inverted2=False,value11="11",value00="00",value10="10",value01="01"):
        self.logger = logger
        self.pin1 = Pin(pin1,mode=Pin.OUT,pull=Pin.PULL_DOWN,value=0)
        self.pin2 = Pin(pin2,mode=Pin.OUT,pull=Pin.PULL_DOWN,value=0)
        self.name = name
        self.state1 = 0
        self.state2 = 0
        self.inverted1 = inverted1
        self.inverted2 = inverted2
        self.value00 = value00
        self.value01 = value01
        self.value11 = value11
        self.value10 = value10
    def get_topic(self):
        return 'control/'+self.logger.name+"/"+self.name
    def get(self):
        return (self.state1,self.state2)
    def set(self,state1,state2):
        self.logger.print(f"Switching {self.name} to {str(state1)}:{str(state2)}")
        if not self.inverted1:
            self.pin1.value(bool(state1))
        else:
            self.pin1.value(not state1)
        if not self.inverted2:
            self.pin2.value(bool(state2))
        else:
            self.pin2.value(not state2)
        self.state1 = state1
        self.state2 = state2
    def report(self):
        self.logger.print("Reporting state for",self.name)
        if self.get() == (0,0):
            label = self.value00
        if self.get() == (0,1):
            label = self.value01    
        if self.get() == (1,1):
            label = self.value11
        if self.get() == (1,0):
            label = self.value10

        return {self.name:{"value":str(self.get()),"label":label}}
    def command(self, topic, msg):
        if topic == 'control/'+self.logger.name+"/"+self.name:
            self.logger.print("SGREADY:"+topic+":"+msg)
            if self.value00 in msg:
                self.set(0,0) 
            if self.value01 in msg:
                self.set(0,1)
            if self.value11 in msg:
                self.set(1,1)
            if self.value10 in msg:
                self.set(1,0)


def connect_best_wifi(logger,credentials,max_attempts=5):
    logger.wdt.feed()
    wlan = network.WLAN(network.STA_IF)
    try:
        wlan.deinit()
    except:
        logger.print("Wi-Fi deinit failed")
    wlan.active(True)
    for attempt in range(max_attempts):
        logger.wdt.feed()
        logger.print(f"Wi-Fi scan attempt {attempt + 1}")
        nets = wlan.scan()
        best_net = None
        best_rssi = -999
        for ssid_bytes, _, _, rssi, _, _ in nets:
            ssid = ssid_bytes.decode()
            if ssid in credentials and rssi > best_rssi:
                best_net = ssid
                best_rssi = rssi
        if best_net:
            logger.print(f"Connecting to: {best_net} (RSSI: {best_rssi})")
            wlan.connect(best_net, credentials[best_net])
            timeout = 15
            while not wlan.isconnected() and timeout > 0:
                logger.print(".", end="")
                logger.wdt.feed()
                sleep(1)
                timeout -= 1
            if wlan.isconnected():
                logger.print("\nConnected to Wi-Fi!")
                logger.print("IP:"+str(wlan.ifconfig()[0]))
                return True
            else:
                logger.print("Wi-Fi connection timed out")
        else:
            logger.print("No known networks found")
        sleep(1)
    raise Exception("Failed to connect to Wi-Fi after multiple attempts")


class MQTT:
    # MQTT connection with retry
    def __init__(self,logger,credentials,callback,peripherals,config,topics_i,topics_o,max_attempts=5) -> None:
        self.logger = logger
        self.topics_i = topics_i
        self.topics_o = topics_o
        self.peripherals = peripherals
        self.credentials = credentials
        self.config = config
        self.logger.wdt.feed()
        for attempt in range(max_attempts):
            self.logger.wdt.feed()
            try:
                self.client = MQTTClient(
                    credentials["ID"],
                    credentials["BROKER"],
                    port=credentials["PORT"],
                    user=credentials["USERNAME"],
                    password=credentials["PASSWORD"],
                    ssl=ssl
                )
                self.client.set_callback(callback)
                self.client.connect()
                self.logger.wdt.feed()
                self.logger.print("Connected to broker")
                return
            except Exception as e:
                self.logger.print(f"MQTT connection failed (attempt {attempt + 1}):", e)
                sleep(2)

        raise Exception("Failed to connect to MQTT after multiple attempts")

    def subscribe_list(self,subscribe): 
                for topic in subscribe:
                    self.client.subscribe(topic)
                    self.logger.print("Subscribed to",topic)
                self.logger.wdt.feed()
                topic = "subscribing/"+self.logger.name
                payload = str(subscribe)
                self.client.publish(topic.encode(),payload.encode())
                sleep(2)
                return
        
    def respond_status(self):
        msg = str(self.credentials["ID"]).encode()
        try:
            self.logger.increment_out()
            self.client.publish(self.topics_o["CHECK"], msg)
            self.logger.print(f"Responded to CHECK with: {msg}")
        except Exception as e:
            self.logger.print("Failed to publish CHECK response:", e)
    def report_state(self):
        self.logger.wdt.feed()
        self.logger.print("Reporting state...")
        report = {}
        try:
            for p in self.peripherals:
                self.logger.wdt.feed()
                report.update(p.report())
            report.update(self.logger.prepare_log())
            self.logger.print(json.dumps(report))
            self.logger.increment_out()
            self.client.publish(self.topics_o["REPORT"],json.dumps(report))
            self.logger.print("Reported state")
            sleep(3)
        except Exception as e:
            self.logger.print("Failed to publish state:", e)
        self.logger.wdt.feed()
  
    
    def discover(self):
        payload = {}
        payload.update({"PERIPHERALS":self.config["PERIPHERALS"]})
        payload.update({"SETTINGS":self.config["SETTINGS"]})
        payload.update({"VERSION":self.logger.version["version"]})
        payload.update({"TOPICS":{"IN":self.topics_i,"OUT":self.topics_o}})
        self.client.publish(self.topics_o["DISCOVER"], json.dumps(payload),retain=True,qos=1)