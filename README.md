# ELMO TRV-35G Slide Digitizer

This project converts an **ELMO TRV-35G slide projector/viewer** into a slide-digitizing station by mounting a Raspberry Pi camera inside the projector and using a Raspberry Pi to capture images. The original slide-handling mechanism remains the means of presenting slides to the camera.

The photos below show the outside of the projector, the interior camera and Raspberry Pi, and the labeled external connections. They document this particular build; component placement and wiring may differ in other units.

![ELMO TRV-35G projector/viewer](trv35.png)
*ELMO TRV-35G exterior.*

![Internal Raspberry Pi and camera](rpi_camera.jpg)
*Camera mounted inside the projector (left) and Raspberry Pi board (right). The camera connects to the Pi through a ribbon cable.*

![Labeled connections](output_connections.jpg)
*Overall interior view with labels identifying the HDMI, USB output, and power areas. Verify the exact connector and voltage before connecting or changing wiring.*

## Equipment and software

- ELMO TRV-35G projector/viewer, modified to accommodate the camera and computer.
- Raspberry Pi with an attached **Raspberry Pi HQ (IMX477) camera**, supported lens, and CSI ribbon connection.
- Display connected to the Raspberry Pi to view the live camera image (HDMI is labeled in the photo).
- Keyboard for controlling capture and exposure.
- Power supplies and cables appropriate to the projector and Raspberry Pi. The photographs do **not** establish the Pi's power supply voltage, source, or complete pinout; check these independently.
- Raspberry Pi OS with Python 3, **Picamera2** and **OpenCV (`cv2`)**, plus the Raspberry Pi camera stack. The script also uses standard-library modules and can use `xrandr` or `tkinter` to detect screen dimensions.

The current capture program is **`capture_image_fullscreen_exposure_1sec.py`**. It uses Picamera2 for camera access and OpenCV for the full-screen window. It deliberately does **not** use a Qt camera-preview widget.

## Connections and setup

1. **Power off and unplug the projector and Raspberry Pi** before inspecting or changing any internal components. Keep clear of internal AC wiring, moving parts, and hot components.
2. Confirm that the camera is securely positioned in the projector's slide optical path, as shown in the internal photograph. Adjust focus and physical alignment as required for the slide to appear sharp and properly centered.
3. Ensure that the camera ribbon cable is seated correctly at the camera and the Raspberry Pi. Avoid sharp bends and interference with moving parts.
4. Connect the Raspberry Pi to the display through the **HDMI connection** indicated in the overall interior photo.
5. Connect the keyboard to the Pi using an available USB port. The photo labels a **USB out** connection, but the image alone does not establish its internal wiring or USB role; verify it before use.
6. Connect the Raspberry Pi's proper power source. The photo labels the **Power** area but is not a wiring schematic. **Do not assume that projector power can be fed directly to the Pi.**
7. Start the Pi, and confirm that the camera is detected and operational before launching the capture application.

## Start the capture application

Place the script in a working directory, open a terminal in that directory, and run:

```bash
python3 capture_image_fullscreen_exposure_1sec.py
```

If you are using a virtual environment, ensure that it provides access to your installed Picamera2 and OpenCV packages. The program creates an OpenCV window and requires a working graphical desktop session; it is not a terminal-only application.

**Images are saved to the process's current working directory** (the directory from which you launch the command), *not necessarily the directory containing the script*. The program prints the selected output location when it starts.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| **Space** | Capture and save the current slide as the next numbered JPEG. |
| **M** | Toggle between automatic exposure and manual exposure. |
| **U** | In manual mode, increase exposure time by 10% (typically brighter). |
| **D** | In manual mode, reduce exposure time by dividing by 1.1 (typically darker). |
| **Q** or **Esc** | Quit the program cleanly. |

In **auto exposure**, the camera continuously adjusts exposure. Pressing **M** to enter manual mode reads the most recent camera exposure time and analogue gain, then holds both values. **U/D** change exposure time while keeping that captured analogue gain fixed. Pressing **M** again re-enables automatic exposure. U/D have no effect while auto exposure is active.

The exposure status appears in the upper-left corner of the **preview for approximately one second after pressing M, U, or D**, then disappears. The status overlay is not added to the saved JPEGs. Exposure status is also printed in the terminal.

### Typical slide capture workflow

1. Put a slide in the projector/viewer and illuminate it as required by the original device.
2. Start the capture script and ensure the **OpenCV window has keyboard focus** (click it once if needed).
3. Check slide positioning and focus in the live preview.
4. Leave exposure in **AUTO**, or press **M** to lock exposure and press **U/D** to adjust it for the slide.
5. Press **Space** once to save the image. The terminal prints the filename when saved.
6. Advance to the next slide and repeat.
7. Press **Q** or **Esc** when finished.

### Saved images and display behavior

- Saved image size: **4056 × 3040 pixels**, JPEG, from Picamera2's **main** stream.
- Live preview stream: **960 × 720 pixels**, YUV420, converted for OpenCV display.
- The preview is resized and **center-cropped as needed to fill the display without stretching**. For a wide monitor, some of the live preview is cropped; the saved JPEG retains the complete camera frame.
- Filenames start at **`slide1.jpg`**, then **`slide2.jpg`**, **`slide3.jpg`**, etc.
- At startup, the program scans existing files matching `slide<number>.jpg` in the output directory and continues with **one more than the largest existing number**. This avoids reusing the earlier sequence numbers for an ordinary single running instance.

Example terminal messages:

```text
Preview display size: 1920 x 1080
Full-size JPEGs saved in: /path/to/working-directory
Next file: slide1.jpg | SPACE capture | M auto/manual | U/D exposure | Q/ESC quit
Saved slide1.jpg
MANUAL: 10.00 ms, gain 1.00x
```

*The numerical exposure, screen dimensions, and paths above are illustrative; actual values depend on the camera, monitor, and environment.*

## Camera configuration details

The current script explicitly loads the **`imx477.json`** tuning file and changes the `rpi.alsc` algorithm's `n_iter` setting to `0` if that tuning algorithm is present. This is a build-specific tuning choice: do not assume it is appropriate for a different sensor or camera tuning file.

Automatic screen-size detection uses `xrandr` when available, falls back to `tkinter`, and otherwise assumes 1920 × 1080. If automatic detection is wrong, edit the line near the beginning of the script:

```python
SCREEN_SIZE = (1920, 1080)  # Replace with the monitor's actual resolution
```

The configured capture resolution is the full-size **main** stream. Preview text is drawn *only* onto the resized preview frame; full-resolution JPEGs are captured directly from `main`.

## Troubleshooting

| Issue | Check |
| --- | --- |
| **Nothing happens when pressing keys** | Click once in the OpenCV full-screen window to give it focus; verify that the desktop is receiving keyboard input. |
| **White border or tiny image** | Check the `Preview display size` printed in the terminal; set `SCREEN_SIZE` explicitly to your display's resolution if needed. Do not derive screen dimensions from the preview image rectangle. |
| **Preview cuts off the edges** | This is expected when filling a monitor with a different aspect ratio. It does **not** crop the saved JPEG. |
| **Image too bright or too dark** | Use **M** to lock exposure, then **U/D** to change exposure time. Return to auto with **M** if desired. |
| **U/D don't change exposure** | Manual mode must be enabled first with **M**. |
| **Camera does not start** | Confirm the CSI ribbon orientation and seating, IMX477 camera support, required Picamera2/camera software, and availability of `imx477.json`. |
| **Pictures saved to an unexpected folder** | Check the `Full-size JPEGs saved in:` message. Launch the program from the desired folder. |
| **Capture takes a moment** | Full-resolution JPEG saving is synchronous in the current script; wait for `Saved slideN.jpg` before advancing the slide. |

## Project files

Keep these files in the same directory as this README so the relative photo links display correctly:

```text
README.md
capture_image_fullscreen_exposure_1sec.py
trv35.png
rpi_camera.jpg
output_connections.jpg
```

**Hardware documentation note:** The photos identify component locations and handwritten connector labels, but they do not provide a complete circuit diagram, cable pinout, power specifications, or the procedure for mechanically modifying the projector. Do not use the photographs alone as electrical wiring instructions.
