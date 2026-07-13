# 📱 Phone Camera Controller for Blender

> 🚧 **STATUS: WORK IN PROGRESS (WIP)** 🚧
> Core camera tracking is stable and verified across full range of motion. A known limitation remains near-vertical orientations (see below).

**Phone Camera Controller** is a Blender addon that turns your phone into a physical camera rig for Blender. Move, pan, and tilt your phone in real life, and your Blender camera follows in real time — great for backrooms-style found-footage shots, virtual cinematography, and handheld animation.

---

## ⚙️ How It Works

This addon turns your Blender instance into a local web server:

1. Click **Start Streaming** in Blender — a background thread spins up an HTTP server on port `8000`.
2. Your phone connects over your local Wi-Fi network and loads a lightweight web page (served from the addon's `web/` folder).
3. The page reads your phone's rotation via the `AbsoluteOrientationSensor` API (falling back to `DeviceOrientationEvent` where needed) and captures virtual joystick input.
4. The phone continuously POSTs this data back to Blender.
5. A Blender Modal Operator applies it to the active camera: a fixed axis-frame transform (`Q_FRAME` conjugation) maps the phone's rotation into Blender's camera space, and a one-time calibration offset locks in your starting pose as neutral. Recording inserts real keyframes as the timeline plays.

---

> [!IMPORTANT]
> ### ⚠️ Usage Instructions
> Follow these steps **exactly** to get a clean connection:
>
> 1. **Calibrate your phone:** hold it level in **landscape** orientation *before* connecting. This becomes your "forward."
> 2. **Start the server:** in Blender's 3D Viewport Sidebar (`N` key), under the **Phone Cam** tab, hit **Start Streaming**.
> 3. **Connect your phone:** open your phone's browser and go to `http://[your-ip]:8000`.
>    *(Find your IP in your computer's network settings — your local **IPv4 Address**, e.g. `192.168.100.x`.)*
> 4. **Use Firefox, not Chrome:** Chrome blocks sensor access over plain HTTP on a local network; Firefox for Android does not have this restriction. This addon runs over HTTP, so Firefox is currently required.
> 5. **Enable sensors:** tap **ENABLE SENSORS** on the phone page. You're now controlling the camera.
> 6. **Recalibrate anytime:** if you bump the phone or want a new neutral pose mid-session, tap **RECALIBRATE** — no need to restart the stream.
> 7. **Record:** tap **START RECORDING** on the phone (or press Play in Blender) to insert keyframes as you move. Tap it again to stop.
> 8. **End the session:** tap **CLOSE STREAM** on the phone, or **Stop Streaming** in Blender.

---

## ✨ Features

- Real-time phone rotation → Blender camera rotation, calibrated to your starting pose
- Virtual joystick → ground-locked camera movement
- **Record** button (phone) — start/stop inserting keyframes without touching the keyboard
- **Recalibrate** button (phone) — reset "forward" mid-session without restarting the stream
- Live connection status + recording indicator on the phone screen, so you know it's actually tracking before you start walking
- Optional smoothing & sensitivity, adjustable from the Blender sidebar

---

## 🐛 Known Limitations

* **Near-vertical "inversion":** when the phone swings through roughly ±90° from level (pointing straight down/up), yaw and roll become mathematically ambiguous — a textbook gimbal-style singularity, not a code bug. Wrist imprecision near this pole can look like a sudden flip. Workaround: avoid holding shots dead-vertical; treat it the way you would a real gimbal's limits. A more robust pole-handling approach is on the roadmap.

*(Earlier versions had inverted tilt, calibration sensitivity, and axis-bleed/roll-drift issues — these were root-caused to an incorrect axis-remapping approach and are fixed as of the current `Q_FRAME`-based rotation pipeline.)*

---

## 📥 Installation

1. Download `phone_cam_controller.zip` from the [Releases](../../releases) page (don't use GitHub's "Download ZIP" on the repo itself — see note below).
2. Open Blender (**Blender 5.1+** required).
3. Go to `Edit > Preferences > Add-ons`.
4. Click **Install...** (top right) and select `phone_cam_controller.zip`.
5. Enable the addon by checking the box next to **Camera: Phone Camera Controller**.
6. Open the Sidebar in the 3D Viewport (press `N`) and go to the **Phone Cam** tab.

> **Why not "Download ZIP" from GitHub?** That downloads the whole repo (README, loose files, no proper folder layout) and Blender can't install it directly. The Releases page ships a zip pre-packaged as `phone_cam_controller/__init__.py`, which is what Blender's installer expects.

---

## 📋 Requirements

* **Blender:** 5.1.0 or newer
* **Network:** PC and phone on the **same local Wi-Fi network**
* **Mobile Browser:** **Firefox for Android** (Chrome currently blocks sensor access over local HTTP — see Usage Instructions above)
* **Hardware:** a smartphone with a working gyroscope/accelerometer

---

## 🗂 Project Structure

```
phone_cam_controller/
├── __init__.py        # Blender addon: HTTP server, modal operator, rotation math
└── web/
    ├── index.html      # phone UI structure
    ├── style.css        # phone UI styling
    └── app.js           # sensor capture, joystick, buttons, networking
```

---
*Author: Moaaz Salama | Version: 0.0.4*
