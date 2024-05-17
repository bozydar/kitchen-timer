from machine import Pin, SPI, PWM, ADC
import framebuf
import time
import _thread

C_WHITE = 0xffff
C_BLACK = 0x0000

# C_ONE = 0xE446
C_ONE = 0xE589
C_TWO = 0xE0D9
C_THREE = 0x1A3C
C_FOUR = 0x4CD6
C_FIVE = 0xDF55


class OLED(framebuf.FrameBuffer):
    def __init__(self):
        dc = 8
        rst = 12
        mosi = 11
        sck = 10
        cs = 9

        self.width = 128
        self.height = 64

        self.cs = Pin(cs, Pin.OUT)
        self.rst = Pin(rst, Pin.OUT)

        self.cs(1)
        self.spi = SPI(1)
        self.spi = SPI(1, 2000_000)
        self.spi = SPI(1, 20000_000, polarity=0, phase=0, sck=Pin(sck), mosi=Pin(mosi), miso=None)
        self.dc = Pin(dc, Pin.OUT)
        self.dc(1)
        self.buffer = bytearray(self.height * self.width // 8)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_HMSB)
        self.init_display()

        self.white = 0xffff
        self.black = 0x0000

    def write_cmd(self, cmd):
        self.cs(1)
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def write_data(self, buf):
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(bytearray([buf]))
        self.cs(1)

    def init_display(self):
        """Initialize display"""
        self.rst(1)
        time.sleep(0.001)
        self.rst(0)
        time.sleep(0.01)
        self.rst(1)

        self.write_cmd(0xAE)  # turn off OLED display

        self.write_cmd(0x00)  # set lower column address
        self.write_cmd(0x10)  # set higher column address

        self.write_cmd(0xB0)  # set page address

        self.write_cmd(0xdc)  # et display start line
        self.write_cmd(0x00)
        self.write_cmd(0x81)  # contract control
        self.write_cmd(0x6f)  # 128
        self.write_cmd(0x21)  # Set Memory addressing mode (0x20/0x21) #

        self.write_cmd(0xa0)  # set segment remap
        self.write_cmd(0xc0)  # Com scan direction
        self.write_cmd(0xa4)  # Disable Entire Display On (0xA4/0xA5)

        self.write_cmd(0xa6)  # normal / reverse
        self.write_cmd(0xa8)  # multiplex ratio
        self.write_cmd(0x3f)  # duty = 1/64

        self.write_cmd(0xd3)  # set display offset
        self.write_cmd(0x60)

        self.write_cmd(0xd5)  # set osc division
        self.write_cmd(0x41)

        self.write_cmd(0xd9)  # set pre-charge period
        self.write_cmd(0x22)

        self.write_cmd(0xdb)  # set vcomh
        self.write_cmd(0x35)

        self.write_cmd(0xad)  # set charge pump enable
        self.write_cmd(0x8a)  # Set DC-DC enable (a=0:disable; a=1:enable)
        self.write_cmd(0XAF)

    def show(self):
        self.write_cmd(0xb0)
        for page in range(0, 64):
            self.column = 63 - page
            self.write_cmd(0x00 + (self.column & 0x0f))
            self.write_cmd(0x10 + (self.column >> 4))
            for num in range(0, 16):
                self.write_data(self.buffer[page * 16 + num])


class Beep:
    def __init__(self):
        self._blinking = Blinking(500, 500)
        self._pwm = PWM(Pin(5))
        self._enabled = False

    def enabled(self, value):
        self._enabled = value

    def tick(self):
        if self._enabled and self._blinking.can_show():
            self._pwm.freq(800)
            self._pwm.duty_u16(32768)
        else:
            self._pwm.deinit()


class Timer:
    def __init__(self, on_alarm):
        self.clock = None
        self.alarm_in = 0
        self.last_measure = self._seconds()
        self.running = False
        self.on_alarm = on_alarm
        self._in_alarm = False

    def current(self):
        if self.running and self.last_measure != self._seconds():
            self.inc(self.last_measure - self._seconds())

        self.last_measure = self._seconds()

        minutes, seconds = divmod(self.alarm_in, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    def tick(self):
        self.current()

    def inc(self, seconds):
        self.alarm_in = max(0, self.alarm_in + seconds)
        print('alarm_in', self.alarm_in)
        if self.alarm_in == 0 and not self._in_alarm:
            self.running = False
            self._alarm()

    def inc_with_round(self, seconds):
        self.alarm_in = max(0, self.alarm_in + seconds - (self.alarm_in % 60))

    @property
    def in_alarm(self):
        return self._in_alarm

    @in_alarm.setter
    def in_alarm(self, value):
        self._in_alarm = value

    def _alarm(self):
        print('alarm')
        self._in_alarm = True
        if self.on_alarm is not None:
            self.on_alarm(self)

    def start(self):
        self.last_measure = self._seconds()
        self.running = True

    def pause(self):
        self.running = False

    def toggle(self):
        if self.running:
            self.pause()
        else:
            self.start()

    def _seconds(self) -> int:
        return time.mktime(time.gmtime())


class Blinking:
    def __init__(self, show_ms: int, hide_ms: int):
        self.show_ms = show_ms
        self.hide_ms = hide_ms
        self.is_showing = True
        self.state_changed_at = time.ticks_ms()

    def can_show(self):
        if self.is_showing:
            if time.ticks_diff(time.ticks_ms(), self.state_changed_at) >= self.show_ms:
                self.is_showing = False
                self.state_changed_at = time.ticks_ms()
        else:
            if time.ticks_diff(time.ticks_ms(), self.state_changed_at) >= self.hide_ms:
                self.is_showing = True
                self.state_changed_at = time.ticks_ms()

        return self.is_showing


class Icon(framebuf.FrameBuffer):
    def __init__(self, display: OLED, width: int, height: int, is_blinking: bool = False):
        bitmap = bytearray(height * width * 2)
        super().__init__(bitmap, width, height, framebuf.MONO_HMSB)
        self.display = display
        self.is_blinking = is_blinking

    def show(self, x, y):
        self.display.blit(self, x, y, 0)


class PauseIcon(Icon):
    def __init__(self, display: OLED):
        super().__init__(display, 8, 8)
        self.fill_rect(0, 0, 3, 8, C_FIVE)
        self.fill_rect(5, 0, 3, 8, C_FIVE)
        self.blinking = Blinking(500, 500)

    def show(self, x, y):
        if self.blinking.can_show():
            super().show(x, y)


class SegmentedText(framebuf.FrameBuffer):
    def __init__(self, display: OLED):
        super().__init__(display.buffer, display.width, display.height, framebuf.MONO_HMSB)
        self.display = display
        self.segments = {
            "0": [[0, 2], [0, 1, 2, 3]],
            "1": [[], [0, 1]],
            "2": [[0, 1, 2], [1, 2]],
            "3": [[0, 1, 2], [2, 3]],
            "4": [[1], [0, 2, 3]],
            "5": [[0, 1, 2], [0, 3]],
            "6": [[0, 1, 2], [0, 1, 3]],
            "7": [[0], [2, 3]],
            "8": [[0, 1, 2], [0, 1, 2, 3]],
            "9": [[0, 1, 2], [0, 2, 3]],
            " ": [[], []],
            "-": [[1], []]
        }
        self.seg_size = 15
        self.seg_space = 6

    def write(self, text: str, x: int, y: int, c: int):
        x_ = x
        for i in range(len(text)):
            s = text[i]
            if s in self.segments.keys():
                [hor, ver] = self.segments[s]
                self._hor_segments(x_, y, hor, c)
                self._ver_segments(x_, y, ver, c)
                x_ += self.seg_size + self.seg_space
            elif s == ':':
                third = self.seg_size // 3
                self.fill_rect(x_, y + 2 * third, 2, 2, c)
                self.fill_rect(x_, y + 4 * third, 2, 2, c)
                x_ += self.seg_size // 2

    def _hor_segments(self, x: int, y: int, segs: [int], c: int):
        for seg in segs:
            y_ = y + seg * self.seg_size
            self.hline(x + 2, y_ - 1, self.seg_size - 3, c)
            self.hline(x + 1, y_, self.seg_size - 1, c)
            self.hline(x + 2, y_ + 1, self.seg_size - 3, c)

    def _ver_segments(self, x: int, y: int, segs: [int], c: int):
        for seg in segs:
            seg_x, seg_y = divmod(seg, 2)
            x_ = x + seg_x * self.seg_size
            y_ = y + seg_y * self.seg_size
            self.vline(x_ - 1, y_ + 2, self.seg_size - 3, c)
            self.vline(x_, y_ + 1, self.seg_size - 1, c)
            self.vline(x_ + 1, y_ + 2, self.seg_size - 3, c)


class Keys:
    def __init__(self, on_key_pressed=None):
        self.keyA = Pin(15, Pin.IN, Pin.PULL_UP)
        self.keyB = Pin(17, Pin.IN, Pin.PULL_UP)

        self.keyAPressed = False
        self.keyBPressed = False

        self.on_key_pressed = on_key_pressed

    def tick(self):
        if self.keyA.value() == 0 and not self.keyAPressed:
            self.keyAPressed = True
            self._on_event('keyAPressed')
        elif self.keyB.value() == 0 and not self.keyBPressed:
            self.keyBPressed = True
            self._on_event('keyBPressed')
        elif self.keyAPressed or self.keyBPressed:
            self.keyAPressed = False
            self.keyBPressed = False

    def _on_event(self, event_name):
        if self.on_key_pressed:
            self.on_key_pressed(self, event_name)


class Screen:
    def __init__(self, *, display: OLED):
        self._display = display


class TimerScreen(Screen):
    def __init__(self, *, keys: Keys, color: int, timer: Timer, display: OLED):
        super().__init__(display=display)
        self._color = color
        self._timer = timer
        self._keys = keys
        self._pause_icon = PauseIcon(self._display)
        self._segmented_text = SegmentedText(self._display)

    def show(self):
        if self._keys.keyAPressed:
            self._timer.inc_with_round(60)
            self._timer.in_alarm = False
            self._timer.pause()
        if self._keys.keyBPressed:
            self._timer.in_alarm = False
            if self._timer.running:
                self._timer.inc_with_round(-60)
            else:
                self._timer.start()

        self._display.fill(self._color)
        self._segmented_text.write(self._timer.current(), 8, 25, 0xFF)

        if not self._timer.running:
            self._pause_icon.show(3, 3)


class State:
    def __init__(self, *, keys: Keys, pause_icon: PauseIcon, segmented_text: SegmentedText, display: OLED):
        self._display = display
        self._beep = Beep()
        self._timers = [
            Timer(on_alarm=lambda _: self._beep.enabled(True)),
        ]
        self.screens: [Screen] = [
            TimerScreen(timer=self._timers[0], color=0x00, keys=keys, display=display),
        ]
        self._current_screen_index = 0
        self._keys = keys
        self._keys.on_key_pressed = self._on_key_pressed
        self.pause_icon = pause_icon
        self.segmented_text = segmented_text

    def _show_screen(self, screen_index):
        this = self

        def show_screen(_initiator):
            this._current_screen_index = screen_index
            this._beep.enabled(True)

        return show_screen

    def _on_key_pressed(self, _keys, _keys_event):
        self._beep.enabled(False)

    def tick(self) -> None:
        for timer in self._timers:
            timer.tick()
        self._keys.tick()
        self._beep.tick()

        self.screens[0].show()


display = OLED()
display.show()
state = State(keys=Keys(), pause_icon=PauseIcon(display), segmented_text=SegmentedText(display), display=display)
while True:
    state.tick()

    display.show()
    time.sleep_ms(100)
