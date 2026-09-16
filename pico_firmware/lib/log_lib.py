from machine import Pin
from crash_lib import *
import os
class Logger:
    def __init__(self,temp=True) -> None:
        self.count_in = 0
        self.count_out = 0
        self.name = "unknown"
        self.version = {"version":"unknown"}
        self.wdt = FakeWDT()
        self.led = StatusLight()
        self.config = {}
    def prepare_log(self):
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
        return {"flags":{"value":flags},
                "version":{"value":self.version["version"]},
                "in":{"value":self.count_in,"unit":"msgs"},
                "out":{"value":self.count_out,"unit":"msgs"},
                "crashes":{"value":read_crash_count(),"unit":"crashes"}
                }
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
        print(*args, end=end)

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