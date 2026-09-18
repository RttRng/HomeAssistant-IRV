from irv_lib import *
from log_lib import * 
from initialise import logger


identity = get_id()
config = read_json(f"/branches/{identity}/config.json")

settings_config = read_json("settings.json")
wifi_config = read_json("wifi.json")
mqtt_config = read_json("mqtt.json")
version = read_json("version.json")
logger.print("Version:",version["version"])
logger.print("Identity:",identity)
wifi_config.update(config["WIFI"])
mqtt_config.update(config["MQTT"])
settings_config.update(config["SETTINGS"])
# Should overwrite the general files with board specific settings if present
config["WIFI"].update(wifi_config)
config["MQTT"].update(mqtt_config)
config["SETTINGS"].update(settings_config)

logger.version = version
logger.name = config["MQTT"]["ID"]
logger.config = config

import pull
update_result = pull.update(version,config,logger)

crash_count_decrease_conditions = {
    "check":False,
    "report":False,
    "pong":False,
    "decreased":False
}

to_do_list = {
    "subscribe":False,
    "reset":False,
    "ping":False,
    "report":False
}



name_base = config["MQTT"]["ID"]
TOPIC_I = {"CHECK":b'check',
           "CONTROL":b'control',
           "DATA":b'give',
           "RESET":b'reset',
           "PONG":b'pong',
           "UNDEBUG":b'undebug',
           "UPDATE":b'update'
           }
TOPIC_I_LIST = [x for x in TOPIC_I.values()]
TOPIC_O = {"CHECK":b'status',
           "REPORT":name_base,
           "PING":b'ping',
           "DISCOVER":'discovery/'+name_base
           }

peripherals = []
name_base = config["MQTT"]["ID"]
for p in config["PERIPHERALS"]:
    if p["TYPE"]=="SWITCH":
        sw = Switch(pin=p["PIN"],name=p["NAME"],logger=logger,inverted=p["INVERTED"],valueOn=p["VALUEON"],valueOff=p["VALUEOFF"])
        peripherals.append(sw)
        TOPIC_I_LIST.append(bytes(sw.get_topic(),"utf-8"))
    if p["TYPE"]=="BME280":
        peripherals.append(Bme280(sda=p["SDA_PIN"],scl=p["SCL_PIN"],logger=logger,name=p["NAME"]))
    if p["TYPE"]=="DHT":
        peripherals.append(DHT(pin=p["PIN"],name=p["NAME"],logger=logger))
    if p["TYPE"]=="BINARYSENSOR":
        peripherals.append(BinarySensor(pin=p["PIN"], name=p["NAME"], logger=logger, inverted=p["INVERTED"], valueOn=p["VALUEON"],valueOff=p["VALUEOFF"]))
    if p["TYPE"]=="KIT":
        peripherals.append(KIT(pins=p["PINS"],name=p["NAME"],logger=logger))
    if p["TYPE"]=="SGREADY":
        sgready = SGReady(pin1=p["PIN1"], pin2=p["PIN2"], name=p["NAME"] ,logger=logger,
        inverted1=p["INVERTED1"], inverted2=p["INVERTED2"],value11=p["VALUE11"],value00=p["VALUE00"],value10=p["VALUE10"],value01=p["VALUE01"])
        peripherals.append(sgready)
        TOPIC_I_LIST.append(bytes(sgready.get_topic(),"utf-8"))

logger.print(f"Initialized {len(peripherals)} peripherals: {[p.name for p in peripherals]}")

def mqtt_callback(topic, msg):
        logger.increment_in()
        msg_me = msg == identity.encode() or msg == b'' or msg == b'ALL'
        logger.print("Message for me:",msg_me)
        logger.print(f"Received message on {topic}: {msg}")
        if topic == TOPIC_I["CHECK"] and msg_me:
            mqtt.respond_status()
            crash_count_decrease_conditions["check"] = True
        elif topic == TOPIC_I["DATA"] and msg_me:
            mqtt.report_state()
        elif topic == TOPIC_I["RESET"] and msg_me:
            logger.print("reset command")
            try:
                mqtt.client.publish(b"reseting/command",logger.name.encode())
                sleep(3)
            finally:
                reset()
        elif topic == TOPIC_I["PONG"] and msg_me:
            global got_ping
            got_ping = True
            crash_count_decrease_conditions["pong"] = True
        elif topic == TOPIC_I["UNDEBUG"] and msg_me:
            logger.print("removing debug flag")
            try:
                os.stat("debug.flag")
                os.remove("debug.flag")
                logger.print("reset command")
                try:
                    mqtt.client.publish(b"reseting/command",logger.name.encode())
                    sleep(3)
                finally:
                    reset()
            except OSError:
                logger.print("debug flag not present")
        elif topic == TOPIC_I["UPDATE"] and msg_me:
            try:
                mqtt.client.publish(b"updatubg/command",logger.name.encode())
                sleep(3)
            finally:
                try:
                    logger.wdt.feed()
                    import pull
                    result = pull.update(version,config,logger)
                    logger.print("rescue: pull result:", result)
                except Exception as e:
                    logger.print("rescue: pull.update() itself raised:", e)
                

        else:
            for p in peripherals:
                p.command(topic.decode(),msg.decode())


def to_do_reset():
    global mqtt
    mqtt.client.publish(b"reseting/timer",logger.name.encode())
    sleep(3)
    reset()

def to_do_sub():
    global mqtt
    mqtt.subscribe_list(TOPIC_I_LIST)
    mqtt.client.publish(b"subscribing/timer",logger.name.encode())
    sleep(3)
got_ping = True
def to_do_ping():
    global mqtt, got_ping
    logger.print("Ping: ",str(got_ping))
    if not got_ping:
        mqtt.subscribe_list(TOPIC_I_LIST)
        mqtt.client.publish(b"subscribing/no_pong",logger.name.encode())
        sleep(3)    
    mqtt.client.publish(TOPIC_O["PING"],logger.name.encode())
    got_ping = False
    sleep(2)

def cb_sub(timer):
    to_do_list["subscribe"] = True
def cb_reset(timer):
    to_do_list["reset"] = True
def cb_ping(timer):
    to_do_list["ping"] = True
def cb_report(timer):
    to_do_list["report"] = True
def to_do(to_do_list):
    if to_do_list["reset"]:
        to_do_list["reset"] = False
        to_do_reset()
    if to_do_list["subscribe"]:
        to_do_list["subscribe"] = False
        to_do_sub()
    if to_do_list["ping"]:
        to_do_list["ping"] = False
        to_do_ping()
    if to_do_list["report"]:
        to_do_list["report"] = False
        mqtt.report_state()
        crash_count_decrease_conditions["report"] = True

    if crash_count_decrease_conditions["report"] == True and crash_count_decrease_conditions["check"] == True and crash_count_decrease_conditions["pong"] == True and crash_count_decrease_conditions["decreased"] == False:
       crash_count_decrease_conditions["decreased"] = True
       from crash_lib import read_crash_count, write_crash_count
       n = read_crash_count()
       write_crash_count(max(0,n-1))
# Main loop
def main_loop():
    
    global mqtt
    logger.wdt.feed()
    logger.led.on()
    connect_best_wifi(logger=logger,credentials=config["WIFI"],max_attempts=5)
    mqtt = MQTT(logger=logger,credentials=config["MQTT"],callback=mqtt_callback,peripherals=peripherals,config=config,topics_o=TOPIC_O,topics_i=TOPIC_I,max_attempts=5)
    mqtt.subscribe_list(TOPIC_I_LIST)
    mqtt.discover()
    

    global mqtt, got_ping
    timer_report = Timer()
    timer_report.init(period=config["SETTINGS"]["PERIODIC_SEND_MS"], mode=Timer.PERIODIC, callback=cb_report)
    timer_reset = Timer()
    timer_reset.init(period=config["SETTINGS"]["PERIODIC_RESET_MS"], mode=Timer.PERIODIC, callback=cb_reset)
    timer_sub = Timer()
    timer_sub.init(period=config["SETTINGS"]["PERIODIC_SUBSCRIBE_MS"], mode=Timer.PERIODIC, callback=cb_sub)
    timer_ping = Timer()
    timer_ping.init(period=config["SETTINGS"]["PERIODIC_PING_MS"],mode=Timer.PERIODIC,callback=cb_ping)
    logger.print("Reporting state")
    mqtt.report_state()
    logger.wdt.feed()
    logger.led.off()
    logger.print("Entering main loop")
    while True:
        try:
            logger.wdt.feed()
            to_do(to_do_list)
            logger.print("Checking for MQTT message...")
            mqtt.client.check_msg()
            gc.collect()
            logger.wdt.feed()
            sleep(3)
        except Exception as e:
            logger.print("Error during loop:", e)
            sleep(5)

    

sleep(1)
logger.led.off()
mqtt = None
main_loop()
logger.print("reseting")
try:
    mqtt.client.publish(b"reseting/loop",logger.name.encode())
    sleep(3)
except:
    pass
