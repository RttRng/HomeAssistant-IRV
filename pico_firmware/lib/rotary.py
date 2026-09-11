from machine import Pin
class Rotary:
    def _none_handler(*arg):
        pass
    def __init__(self,
                pinA,
                pinB,
                pinButton,
                press=_none_handler,
                release=_none_handler,
                clockwise=_none_handler,
                counterclockwise=_none_handler,
                invertRotation=False,
                snapRotation=False):
        self.a = Pin(pinA,Pin.IN)
        self.b = Pin(pinB,Pin.IN)
        self.button = Pin(pinButton,Pin.IN,Pin.PULL_UP)
        self.counter = 0
        self.invertRotation = invertRotation
        self.press = press
        self.release = release
        self.clockwise = clockwise
        self.counterclockwise = counterclockwise
        self.a.irq(handler=self.pinIRQ,trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING)
        self.b.irq(handler=self.pinIRQ,trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING)
        self.button.irq(handler=self._btn_changed,trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING)
        self.counter = 0
        self.snapRotation = snapRotation
        self.last_state = (self.a.value(), self.b.value())
    def get_value(self):
        return self.counter
    def button_value(self):
        return not self.button.value()
    def _btn_changed(self,_):
        if not self.button.value():                    
            self.press()
        else:
            self.release()
    def pinIRQ(self,_):
        state = (self.a.value(), self.b.value())
        delta = self._evaluate_rotation(state)
        if self.invertRotation:
            delta = -delta
        if delta == 1:
            self.counter += 1
            self.clockwise()
        elif delta == -1:
            self.counter -= 1
            self.counterclockwise()
        self.last_state = state
    def _evaluate_rotation(self, state):
        if self.snapRotation:
            if self.last_state == (0,1) and state == (1,1):
                return 1
            elif self.last_state == (1,0) and state == (1,1):
                return -1
            else:
                return 0

        if self.last_state == (0,0):
            if state == (0,1):
                return 1
            elif state == (1,0):
                return -1
        elif self.last_state == (0,1):
            if state == (1,1):
                return 1
            elif state == (0,0):
                return -1
        elif self.last_state == (1,1):
            if state == (1,0):
                return 1
            elif state == (0,1):
                return -1
        elif self.last_state == (1,0):
            if state == (0,0):
                return 1
            elif state == (1,1):
                return -1
        return 0