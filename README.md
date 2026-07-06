# 📱 Phone Camera Controller for Blender

> 🚧 **STATUS: WORK IN PROGRESS (WIP)** 🚧
> This addon is currently in active development. Expect bugs, rough edges, and axis-mapping quirks!

**Phone Camera Controller** is a Blender addon that allows you to use your mobile phone's physical sensors and touchscreen as a virtual camera controller. Move, pan, and tilt your Blender camera in real-time by physically moving your phone and using on-screen virtual joysticks.

---

## ⚙️ How It Works

Under the hood, this addon turns your Blender instance into a **local web server**. 
1. When you click "Start Streaming", a background Python thread spins up an HTTP server on port `8000`.
2. Your phone connects to this server over your local Wi-Fi network and loads a lightweight HTML/JS web page.
3. The web page utilizes the browser's `AbsoluteOrientationSensor` (DeviceOrientation API) and touch events to capture your phone's physical rotation (as quaternions) and virtual joystick inputs.
4. The phone continuously POSTs this sensor data back to Blender.
5. A Blender Modal Operator intercepts this incoming data, calculates the rotational delta based on an initial calibration snapshot, remaps the phone's coordinate space to Blender's camera space, and applies the transformations to the active 3D camera in real-time. It can also record keyframes for animation!

---

> [!IMPORTANT]
> ### ⚠️ VERY IMPORTANT: Usage Instructions
> Please follow these steps **exactly** to ensure the sensors connect and function correctly:
> 
> 1. **Calibrate your phone:** Make sure the phone is calibrated by holding it perfectly level in a **landscape** orientation *before* you do anything else.
> 2. **Start the server:** In Blender's 3D Viewport Sidebar (`N` key) under the **Phone Cam** tab, hit **Start Streaming**.
> 3. **Connect your phone:** Open your phone's browser and navigate to `http://[your-ip]:8000`. 
>    *(To find your IP, check your computer's network settings for your local **IPv4 Address**, example: `192.168.100.x`)*.
> 4. **Use the right browser:** Make sure to use **FIREFOX**, **NOT CHROME**. 
>    *(Reason: Chrome's strict security policies block HTTP sensor requests and the AbsoluteOrientationSensor API on insecure local networks without SSL/HTTPS).*
> 5. **Control the camera:** Tap "ENABLE SENSORS" on the web page. You are done! Control the camera!
> 6. **Stop streaming:** To stop the connection, click **Stop Streaming** in Blender.

---

## 🐛 Known Bugs

Since this is a WIP, there are a few known issues with the sensor math and axis remapping that are being actively worked on:

* **Inverted Tilt:** Tilting the phone makes the camera go in the opposite direction.
* **Calibration Sensitivity:** Holding the phone in an uncalibrated position when starting the stream will make the camera rotation go completely haywire.
* **Axis Bleed/Drift:** The camera slightly tilts (rolls) when rotating the phone (yawing).

---

## 📥 Installation

1. Download the `phone_cam.py` file to your computer (`phone_cam_debugging.py` is for advanced users).
2. Open Blender (Requires **Blender 5.1+**).
3. Go to `Edit > Preferences > Add-ons`.
4. Click the **Install...** button in the top right and select `phone_cam.py`.
5. Enable the addon by checking the box next to **Camera: Phone Camera Controller**.
6. Open the Sidebar in the 3D Viewport (press `N`) and navigate to the **Phone Cam** tab.

---

## 📋 Requirements

* **Blender:** 5.1.0 or newer.
* **Network:** Your PC and mobile phone must be connected to the **same local Wi-Fi network**.
* **Mobile Browser:** **Mozilla Firefox** (Chrome/Safari currently have restrictions with local HTTP sensor APIs).
* **Hardware:** A smartphone with a functioning gyroscope/accelerometer.

---
*Author: Moaaz Salama | Version: 0.0.2*