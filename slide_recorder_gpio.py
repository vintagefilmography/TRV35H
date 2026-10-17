"""Full-screen Raspberry Pi HQ slide capture with manual exposure and color controls.

SPACE save; F/B pulse GPIO17/GPIO27; M toggle exposure; C color mode;
R/G select red/green; U/D adjust selected setting; Q or ESC quit.
"""
from pathlib import Path
import re
import subprocess
import time
import threading

import RPi.GPIO as GPIO

import cv2
from picamera2 import Picamera2

OUTPUT_DIR = Path.cwd()
WINDOW_NAME = 'Slide Camera'
SCREEN_SIZE = None  # Optionally override, e.g. (1920, 1080)
STEP = 1.10  # +/-10% multiplicative adjustments
STATUS_SECONDS = 1.0
RELAY_PULSE_SECONDS = 0.300
FORWARD_GPIO = 17  # BCM numbering; physical pin 11
REVERSE_GPIO = 27  # BCM numbering; physical pin 13


class OpenDrainPulses:
    """Emulate open-collector outputs: LOW when active, input/high-Z when idle.

    GPIO is NEVER driven HIGH. The external relay input must be pulled up
    ONLY to 3.3V, not 5V. Use with a separate 5V relay-coil supply.
    """

    def __init__(self, pins):
        self.pins = tuple(pins)
        self.lock = threading.Lock()
        self.timers = {pin: None for pin in self.pins}
        GPIO.setmode(GPIO.BCM)
        for pin in self.pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_OFF)

    def _release(self, pin):
        with self.lock:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_OFF)
            self.timers[pin] = None

    def pulse(self, pin):
        with self.lock:
            timer = self.timers[pin]
            if timer is not None:
                timer.cancel()
            # Setting LOW in the same operation as output mode avoids a HIGH glitch.
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
            timer = threading.Timer(RELAY_PULSE_SECONDS, self._release, args=(pin,))
            timer.daemon = True
            self.timers[pin] = timer
            timer.start()

    def close(self):
        with self.lock:
            for timer in self.timers.values():
                if timer is not None:
                    timer.cancel()
            for pin in self.pins:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_OFF)
            GPIO.cleanup(self.pins)


def screen_size():
    if SCREEN_SIZE is not None:
        return SCREEN_SIZE
    try:
        out = subprocess.check_output(['xrandr', '--current'], text=True,
                                      stderr=subprocess.DEVNULL, timeout=3)
        match = re.search(r'current\s+(\d+)\s+x\s+(\d+)', out)
        if match:
            return int(match.group(1)), int(match.group(2))
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        size = (root.winfo_screenwidth(), root.winfo_screenheight())
        root.destroy()
        return size
    except Exception:
        print('Screen detection failed; using 1920x1080. Set SCREEN_SIZE if needed.', flush=True)
        return 1920, 1080


def next_slide_number():
    numbers = (int(p.stem[5:]) for p in OUTPUT_DIR.glob('slide*.jpg')
               if p.stem[5:].isdigit())
    return max(numbers, default=0) + 1


def crop_to_fill(frame, target_w, target_h):
    h, w = frame.shape[:2]
    if w * target_h > h * target_w:
        new_w = max(1, h * target_w // target_h)
        x = (w - new_w) // 2
        frame = frame[:, x:x + new_w]
    else:
        new_h = max(1, w * target_h // target_w)
        y = (h - new_h) // 2
        frame = frame[y:y + new_h, :]
    return cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)


def main():
    relays = OpenDrainPulses((FORWARD_GPIO, REVERSE_GPIO))
    target_w, target_h = screen_size()
    number = next_slide_number()
    tuning = Picamera2.load_tuning_file('imx477.json')
    alsc = Picamera2.find_tuning_algo(tuning, 'rpi.alsc')
    if alsc is not None:
        alsc['n_iter'] = 0
    picam2 = Picamera2(tuning=tuning)
    config = picam2.create_preview_configuration(
        main={'size': (4056, 3040)},
        lores={'size': (960, 720), 'format': 'YUV420'},
        display='lores', buffer_count=3)
    picam2.configure(config)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_FREERATIO)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    picam2.start()

    manual = False
    mode = 'exposure'  # Either 'exposure' or 'color'; U/D act on this mode.
    channel = 'red'   # Selected color adjustment: 'red' or 'green'.
    exposure_us = None
    gain = None
    awb_locked = False
    original_auto_gains = None  # Snapshot of AWB gains before manual adjustment.
    red_gain = blue_gain = None
    status_text = ''
    status_until = 0.0
    exp_min, exp_max, _ = picam2.camera_controls['ExposureTime']
    # ColourGains is (red_gain, blue_gain); there is no separate green-gain control.
    # Make green stronger relative to BOTH red and blue by reducing both gains.
    gain_limits = picam2.camera_controls.get('ColourGains')
    if gain_limits:
        color_min, color_max, _ = gain_limits
        # Some camera stacks return a pair for each bound, others scalars.
        color_min = max(0.01, float(color_min[0] if isinstance(color_min, (tuple, list)) else color_min))
        color_max = float(color_max[0] if isinstance(color_max, (tuple, list)) else color_max)
    else:
        color_min, color_max = 0.01, 32.0

    def show_status(message):
        nonlocal status_text, status_until
        status_text = message
        status_until = time.monotonic() + STATUS_SECONDS
        print(message, flush=True)

    print(f'Preview: {target_w} x {target_h} | JPEG: 4056 x 3040', flush=True)
    print(f'Images directory: {OUTPUT_DIR} | next: slide{number}.jpg', flush=True)
    print('SPACE capture | M auto/manual exposure | C color/exposure mode | '
          'R/G select color | F/B relay pulses | U/D adjust | Q/ESC exit', flush=True)

    try:
        while True:
            yuv = picam2.capture_array('lores')
            frame = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)
            frame = crop_to_fill(frame, target_w, target_h)
            if time.monotonic() < status_until:
                # This text exists only in the display buffer; not in saved JPEGs.
                font_scale = min(1.0, max(0.45, target_w / 1500.0))
                text_width, text_height = cv2.getTextSize(
                    status_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)[0]
                cv2.rectangle(frame, (12, 12),
                              (min(target_w - 1, text_width + 48), text_height + 48),
                              (0, 0, 0), -1)
                cv2.putText(frame, status_text, (24, text_height + 28),
                            cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                            (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord('f'), ord('F')):
                relays.pulse(FORWARD_GPIO)
                show_status('FORWARD: GPIO17 LOW for 300 ms')

            elif key in (ord('b'), ord('B')):
                relays.pulse(REVERSE_GPIO)
                show_status('REVERSE: GPIO27 LOW for 300 ms')

            elif key == 32:
                path = OUTPUT_DIR / f'slide{number}.jpg'
                try:
                    picam2.capture_file(str(path), name='main')
                    print(f'Saved {path.name}', flush=True)
                    number += 1
                except Exception as err:
                    print(f'Capture failed: {err}', flush=True)

            elif key in (ord('m'), ord('M')):
                mode = 'exposure'
                if not manual:
                    metadata = picam2.capture_metadata()
                    exposure_us = int(metadata.get('ExposureTime', 10000))
                    gain = float(metadata.get('AnalogueGain', 1.0))
                    picam2.set_controls({'AeEnable': False, 'ExposureTime': exposure_us,
                                         'AnalogueGain': gain})
                    manual = True
                    show_status(f'EXPOSURE MANUAL  {exposure_us / 1000:.1f} ms  gain {gain:.2f}x')
                else:
                    picam2.set_controls({'AeEnable': True})
                    manual = False
                    show_status('EXPOSURE AUTO')

            elif key in (ord('c'), ord('C')):
                if mode == 'color':
                    # The original automatic color controller must be re-enabled.
                    # Restoring only the two saved gain numbers would leave AWB locked,
                    # so the camera would not adapt to later changes in slide lighting.
                    picam2.set_controls({'AwbEnable': True})
                    awb_locked = False
                    mode = 'exposure'
                    show_status('COLOR AUTO RESTORED  (automatic white balance on)')
                    if original_auto_gains is not None:
                        print(f'Original AWB gains at manual entry: '
                              f'R={original_auto_gains[0]:.2f}, '
                              f'B={original_auto_gains[1]:.2f}', flush=True)
                else:
                    mode = 'color'
                    if not awb_locked:
                        metadata = picam2.capture_metadata()
                        current_gains = metadata.get('ColourGains', (1.0, 1.0))
                        red_gain, blue_gain = map(float, current_gains)
                        original_auto_gains = (red_gain, blue_gain)
                        picam2.set_controls({'AwbEnable': False,
                                             'ColourGains': (red_gain, blue_gain)})
                        awb_locked = True
                    show_status(f'COLOR: {channel.upper()} selected  R/G choose, U/D adjust')

            elif key in (ord('r'), ord('R'), ord('g'), ord('G')):
                if mode != 'color':
                    show_status('Press C for COLOR mode first')
                else:
                    channel = 'red' if key in (ord('r'), ord('R')) else 'green'
                    show_status(f'COLOR: {channel.upper()} selected  U/D adjust')

            elif key in (ord('u'), ord('U'), ord('d'), ord('D')):
                upwards = key in (ord('u'), ord('U'))
                factor = STEP if upwards else 1 / STEP
                if mode == 'exposure':
                    if not manual:
                        show_status('Press M to enable MANUAL EXPOSURE')
                        continue
                    exposure_us = max(int(exp_min), min(int(exp_max),
                                                         int(round(exposure_us * factor))))
                    picam2.set_controls({'ExposureTime': exposure_us, 'AnalogueGain': gain})
                    show_status(f'EXPOSURE MANUAL  {exposure_us / 1000:.1f} ms  gain {gain:.2f}x')
                else:
                    if channel == 'red':
                        red_gain = min(color_max, max(color_min, red_gain * factor))
                    else:
                        # Green is the reference channel in libcamera; relative green
                        # adjustment changes RED and BLUE in the opposite direction.
                        red_gain = min(color_max, max(color_min, red_gain / factor))
                        blue_gain = min(color_max, max(color_min, blue_gain / factor))
                    picam2.set_controls({'ColourGains': (red_gain, blue_gain)})
                    show_status(f'COLOR {channel.upper()}  R gain {red_gain:.2f}  B gain {blue_gain:.2f}')

            elif key in (ord('q'), ord('Q'), 27):
                break
    finally:
        relays.close()
        picam2.stop()
        picam2.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
