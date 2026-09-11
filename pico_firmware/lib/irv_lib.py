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

    
class Logger:
    def __init__(self,debug:bool) -> None:
        self.debug = debug
        self.count_in = 0
        self.count_out = 0
        self.name = "unknown"
        self.version = {"version":"unknown"}
        self.wdt = FakeWDT()
        self.led = StatusLight()
        self.config = {}
    def prepare_log(self):
        return {"version":self.version["version"],
                "in":self.count_in,
                "out":self.count_out}
    def set_wdt(self,wdt):
        self.wdt = wdt
    def feed(self):
        self.wdt.feed()
    def setDebug(self,state:bool):
        self.debug = state
    def increment_in(self):
        self.count_in += 1
    def increment_out(self):
        self.count_out += 1
    def print(self,*args, end="\n"):
        if self.debug:
            print(*args, end=end)
def read_json(file:str):
    with open(file,"r") as f:
        return json.load(f)
def write_json(file:str,data):
    with open(file,"w") as f:
        json.dump(data,f)
def get_id():
    with open("identity.txt","r") as f:
        return f.read().strip()
class FakeWDT:
    def __init__(self, timeout=8000):
        pass
    def feed(self):
        pass
class StatusLight:
    def __init__(self):
        self.led = Pin("LED", Pin.OUT)
    def on(self):
        self.led.on()
    def off(self):
        self.led.off()
    def toggle(self):
        self.led.value(not self.led.value())
class Sonda:
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
        return {self.name:str(self.get_temp())}
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
        return {self.name+"/teplota":str(data[0]),
                self.name+"/tlak":str(data[1]),
                self.name+"/vlhkost":str(data[2]),
                self.name+"/rosny_bod":str(data[3])}
    def command(self, topic, msg):
        pass
class Rele:
    def __init__(self, pin,name,logger,inverted=False):
        self.logger = logger
        self.pin = Pin(pin,mode=Pin.OUT,pull=Pin.PULL_DOWN,value=0)
        self.name = name
        self.state = 0
        self.inverted = inverted
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
        return {self.name:str(self.get())}
    def command(self, topic, msg):
        if topic == 'control/'+self.logger.name+"/"+self.name:
            self.logger.print("RELE:"+topic+":"+msg)
            if "false" in msg:
                self.set(0)
            if "true" in msg:
                self.set(1)
class Ventil:
    def __init__(self, pin,name,logger,inverted=False):
        self.logger = logger
        self.pin = Pin(pin,mode=Pin.IN)
        self.name = name
        self.inverted = inverted
    def get(self):
        if self.inverted:
            return not self.pin.value()
        return bool(self.pin.value())
    def report(self):
        self.logger.print("Reporting state for",self.name)
        return {self.name:str(self.get())}
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
        self.strings = [("Woke up!" if reset_cause() == 3 else ("Hello! ZZZ" if read_json("sleep.json")["sleep"] else "Hello!")),
                        "Running from batery" if self.logger.config["SETTINGS"]["BATTERY"] else "Running from cable",
                        f"{last_time[0][0]}h {last_time[0][1]}m ({last_time[1][0]}h {last_time[1][1]}m)",
                        str("Ver: "+self.logger.version["version"]+(" T" if self.logger.version["tested"] else " uT")+(" S" if self.logger.version["stable"] else " uS")+str(reset_cause()))]
        self.update_lcd()
    def update_lcd(self):
        for i in range(4):
            self.lcd.setCursor(i,0)
            self.lcd.printClean(self.strings[i])
    def report(self):
        import ntptime
        from time import localtime, time
        from machine import reset_cause
        self.strings[0] = ("Woke up! Report." if reset_cause() == 3 else "Hello! Report.")
        try:
            self.logger.print("Syncing time with NTP...")
            ntptime.settime()  # Sets Pico's RTC (UTC)
            self.logger.print("Time synced!")
            TIME_OFFSET = 3600*(2)
            now = time() + TIME_OFFSET
            local_time = localtime(now)
            last_time = read_json("last_time.json")
            write = [local_time[3:6],last_time[0][0:3]]
            write_json("last_time.json",write)
            self.strings[2] = f"{local_time[3]}h {local_time[4]}m ({last_time[0][0]}h {last_time[0][1]}m)"
        except:
            self.logger.print("NTP sync failed")

        self.update_lcd()
        return {}
    def command(self, topic, msg):
        pass
    



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
    def __init__(self,logger,credentials,callback,peripherals,topics_i,topics_o,max_attempts=5) -> None:
        self.logger = logger
        self.topics_i = topics_i
        self.topics_o = topics_o
        self.peripherals = peripherals
        self.credentials = credentials
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
    def report_state(self,timer):
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
    def wake(self):
        try:
            self.logger.increment_out()
            self.client.publish(self.topics_o["SLEEP"], json.dumps({"sleep":"0"}))
            self.logger.print(f"Sent waking state")
        except Exception as e:
            self.logger.print("Failed to publish waking:", e)
    def sleep(self):
        try:
            self.logger.increment_out()
            self.client.publish(self.topics_o["SLEEP"], json.dumps({"sleep":"1"}))
            self.logger.print(f"Sent sleeping state")
        except Exception as e:
            self.logger.print("Failed to publish sleeping:", e)
    
    
    