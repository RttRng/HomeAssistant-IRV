from irv_lib import *


identity = get_id()
config = read_json(f"/branches/{identity}/config.json")

settings_config = read_json("settings_config.json")
wifi_config = read_json("wifi.json")
mqtt_config = read_json("mqtt.json")
version = read_json("version.json")
logger.print("Version:",version["version"],"" if version["tested"] else "untested","" if version["stable"] else "unstable")
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



name_base = config["MQTT"]["ID"]
TOPIC_I = {"CHECK":b'check',
           "CONTROL":b'control',
           "DATA":b'give',
           "RESET":b'reset',
           "PONG":b'pong',
           "UNDEBUG":b'undebug'
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
    if p["TYPE"]=="RELE":
        rele = Rele(pin=p["PIN"],name=p["NAME"],logger=logger,inverted=p["INVERTED"],valueOn=p["VALUEON"],valueOff=p["VALUEOFF"])
        peripherals.append(rele)
        TOPIC_I_LIST.append(bytes(rele.get_topic(),"utf-8"))
    if p["TYPE"]=="BME":
        peripherals.append(Bme280(sda=p["SDA_PIN"],scl=p["SCL_PIN"],logger=logger,name=p["NAME"]))
    if p["TYPE"]=="DHT":
        peripherals.append(Sonda(pin=p["PIN"],name=p["NAME"],logger=logger))
    if p["TYPE"]=="VENTIL":
        peripherals.append(Ventil(pin=p["PIN"], name=p["NAME"], logger=logger, inverted=p["INVERTED"], valueOn=p["VALUEON"],valueOff=p["VALUEOFF"]))
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
        elif topic == TOPIC_I["DATA"] and msg_me:
            mqtt.report_state(None)
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
        elif topic == TOPIC_I["UNDEBUG"] and msg_me:
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
                pass

        else:
            for p in peripherals:
                p.command(topic.decode(),msg.decode())


def cb_reset(timer):
    global mqtt
    mqtt.client.publish(b"reseting/timer",logger.name.encode())
    sleep(3)

def cb_sub(timer):
    global mqtt
    mqtt.subscribe_list(TOPIC_I_LIST)
    mqtt.client.publish(b"subscribing/timer",logger.name.encode())
    sleep(3)
    
got_ping = True
def ping(timer):
    global mqtt, got_ping
    logger.print("Ping: ",str(got_ping))
    if not got_ping:
        mqtt.subscribe_list(TOPIC_I_LIST)
        mqtt.client.publish(b"subscribing/no_pong",logger.name.encode())
        sleep(3)    
    mqtt.client.publish(TOPIC_O["PING"],logger.name.encode())
    got_ping = False
    sleep(2)


# Main loop
def main_loop():
    try:
        global mqtt
        logger.wdt.feed()
        logger.led.on()
        connect_best_wifi(logger=logger,credentials=config["WIFI"],max_attempts=5)
        mqtt = MQTT(logger=logger,credentials=config["MQTT"],callback=mqtt_callback,peripherals=peripherals,config=config,topics_o=TOPIC_O,topics_i=TOPIC_I,max_attempts=5)
        mqtt.subscribe_list(TOPIC_I_LIST)
        mqtt.discover()
        try:
            with open("crash_count.json", "w") as f:
                json.dump({"count": 0}, f)
        except OSError:
            pass
    except Exception as e:
        logger.print("Startup error:", e)

    try:
        global mqtt, got_ping
        timer_send = Timer()
        timer_send.init(period=config["SETTINGS"]["PERIODIC_SEND_MS"], mode=Timer.PERIODIC, callback=mqtt.report_state)
        timer_reset = Timer()
        timer_reset.init(period=config["SETTINGS"]["PERIODIC_RESET_MS"], mode=Timer.PERIODIC, callback=cb_reset)
        timer_sub = Timer()
        timer_sub.init(period=config["SETTINGS"]["PERIODIC_SUBSCRIBE_MS"], mode=Timer.PERIODIC, callback=cb_sub)
        timer_ping = Timer()
        timer_ping.init(period=60000,mode=Timer.PERIODIC,callback=ping)
        mqtt.report_state(timer_send)
        logger.wdt.feed()
        logger.led.off()
        logger.print("Entering main loop")
        while True:
            try:
                logger.wdt.feed()
                logger.print("Checking for MQTT message...")
                mqtt.client.check_msg()
                gc.collect()
                logger.wdt.feed()
                sleep(3)
            except Exception as e:
                logger.print("Error during loop:", e)
                sleep(5)
    except Exception as e:
        logger.print("Loop error:", e)
    

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
if not logger.debug:
    sleep(5)
    reset()