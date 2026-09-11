
from machine import Pin
import time

# LCD command constants
LCD_CLEARDISPLAY = 0x01
LCD_RETURNHOME = 0x02
LCD_ENTRYMODESET = 0x04
LCD_DISPLAYCONTROL = 0x08
LCD_CURSORSHIFT = 0x10
LCD_FUNCTIONSET = 0x20
LCD_SETCGRAMADDR = 0x40
LCD_SETDDRAMADDR = 0x80

# Flags for display entry mode
LCD_ENTRYRIGHT = 0x00
LCD_ENTRYLEFT = 0x02
LCD_ENTRYSHIFTINCREMENT = 0x01
LCD_ENTRYSHIFTDECREMENT = 0x00

# Flags for display on/off control
LCD_DISPLAYON = 0x04
LCD_DISPLAYOFF = 0x00
LCD_CURSORON = 0x02
LCD_CURSOROFF = 0x00
LCD_BLINKON = 0x01
LCD_BLINKOFF = 0x00

# Flags for display/cursor shift
LCD_DISPLAYMOVE = 0x08
LCD_CURSORMOVE = 0x00
LCD_MOVERIGHT = 0x04
LCD_MOVELEFT = 0x00

# Flags for function set
LCD_8BITMODE = 0x10
LCD_4BITMODE = 0x00
LCD_2LINE = 0x08
LCD_1LINE = 0x00
LCD_5x10DOTS = 0x04
LCD_5x8DOTS = 0x00


class LiquidCrystal:
    def __init__(self, rs, enable, d4, d5, d6, d7):
        self.rs = Pin(rs, Pin.OUT)
        self.enable = Pin(enable, Pin.OUT)
        self.data_pins = [Pin(d4, Pin.OUT), Pin(d5, Pin.OUT), Pin(d6, Pin.OUT), Pin(d7, Pin.OUT)]

        self.displayfunction = LCD_4BITMODE | LCD_2LINE | LCD_5x8DOTS
        self.displaycontrol = LCD_DISPLAYON | LCD_CURSOROFF | LCD_BLINKOFF
        self.displaymode = LCD_ENTRYLEFT | LCD_ENTRYSHIFTDECREMENT

        self.begin(16, 2)

    def pulse_enable(self):
        self.enable.off()
        time.sleep_us(1)
        self.enable.on()
        time.sleep_us(1)
        self.enable.off()
        time.sleep_us(100)

    def write4bits(self, value):
        for i in range(4):
            self.data_pins[i].value((value >> i) & 0x01)
        self.pulse_enable()

    def send(self, value, mode):
        self.rs.value(mode)
        self.write4bits(value >> 4)
        self.write4bits(value)

    def command(self, value):
        self.send(value, 0)

    def write_char(self, value):
        self.send(value, 1)

    def clear(self):
        self.command(LCD_CLEARDISPLAY)
        time.sleep_ms(2)

    def home(self):
        self.command(LCD_RETURNHOME)
        time.sleep_ms(2)

    def setCursor(self, row, col):
        row_offsets = [0x00, 0x40, 0x14, 0x54]
        self.command(LCD_SETDDRAMADDR | (col + row_offsets[row]))

    def display(self):
        self.displaycontrol |= LCD_DISPLAYON
        self.command(LCD_DISPLAYCONTROL | self.displaycontrol)

    def noDisplay(self):
        self.displaycontrol &= ~LCD_DISPLAYON
        self.command(LCD_DISPLAYCONTROL | self.displaycontrol)

    def cursor(self):
        self.displaycontrol |= LCD_CURSORON
        self.command(LCD_DISPLAYCONTROL | self.displaycontrol)

    def noCursor(self):
        self.displaycontrol &= ~LCD_CURSORON
        self.command(LCD_DISPLAYCONTROL | self.displaycontrol)

    def blink(self):
        self.displaycontrol |= LCD_BLINKON
        self.command(LCD_DISPLAYCONTROL | self.displaycontrol)

    def noBlink(self):
        self.displaycontrol &= ~LCD_BLINKON
        self.command(LCD_DISPLAYCONTROL | self.displaycontrol)

    def scrollDisplayLeft(self):
        self.command(LCD_CURSORSHIFT | LCD_DISPLAYMOVE | LCD_MOVELEFT)

    def scrollDisplayRight(self):
        self.command(LCD_CURSORSHIFT | LCD_DISPLAYMOVE | LCD_MOVERIGHT)

    def leftToRight(self):
        self.displaymode |= LCD_ENTRYLEFT
        self.command(LCD_ENTRYMODESET | self.displaymode)

    def rightToLeft(self):
        self.displaymode &= ~LCD_ENTRYLEFT
        self.command(LCD_ENTRYMODESET | self.displaymode)

    def autoscroll(self):
        self.displaymode |= LCD_ENTRYSHIFTINCREMENT
        self.command(LCD_ENTRYMODESET | self.displaymode)

    def noAutoscroll(self):
        self.displaymode &= ~LCD_ENTRYSHIFTINCREMENT
        self.command(LCD_ENTRYMODESET | self.displaymode)

    def begin(self, cols, rows):
        time.sleep_ms(50)
        self.rs.off()
        self.enable.off()

        # Initialization sequence
        self.write4bits(0x03)
        time.sleep_ms(5)
        self.write4bits(0x03)
        time.sleep_us(150)
        self.write4bits(0x02)

        self.command(LCD_FUNCTIONSET | self.displayfunction)
        self.command(LCD_DISPLAYCONTROL | self.displaycontrol)
        self.clear()
        self.command(LCD_ENTRYMODESET | self.displaymode)
        self.cols = cols
        self.rows = rows

    def print(self, text):
        for char in text:
            self.write_char(ord(char))

    def printClean(self, text):
        t = text+" "*self.cols
        self.print(t[:self.cols])
        