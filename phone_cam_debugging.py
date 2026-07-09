bl_info = {
    "name": "Phone Camera Controller",
    "author": "Moaaz Salama",
    "version": (0,0,2),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > Phone Cam",
    "description": "Control Blender camera via mobile phone sensors",
    "category": "Camera",
}

import bpy
import math
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from mathutils import Vector

# Global dictionary to hold phone data
# q_x/y/z/w: quaternion from AbsoluteOrientationSensor
# joy_x/y: virtual joystick
phone_data = {
    "q_x": 0.0,
    "q_y": 0.0,
    "q_z": 0.0,
    "q_w": 1.0,
    "joy_x": 0.0,
    "joy_y": 0.0,
    "sensor_ready": False,
}

server_thread = None
httpd = None

# ==========================================
# 1. THE WEB APP (HTML/JS sent to the phone)
# ==========================================
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>CAM</title>
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            background: #111;
            color: #ccc;
            font-family: 'Courier New', monospace;
            height: 100vh;
            width: 100vw;
            overflow: hidden;
            touch-action: none;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        /* ---------- LAYOUT ---------- */
        #app {
            display: none; /* shown after sensor init */
            width: 100%;
            height: 100%;
            flex-direction: row;
        }

        /* LEFT: joystick */
        #leftPanel {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }

        /* RIGHT: debug */
        #rightPanel {
            width: 160px;
            border-left: 1px solid #222;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            padding: 18px 14px;
            gap: 12px;
        }

        /* ---------- INIT SCREEN ---------- */
        #initScreen {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 20px;
        }

        #initScreen p {
            font-size: 13px;
            color: #555;
            letter-spacing: 0.05em;
        }

        .btn {
            background: none;
            border: 1px solid #444;
            color: #aaa;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            letter-spacing: 0.1em;
            padding: 10px 24px;
            border-radius: 2px;
            cursor: pointer;
            transition: border-color 0.2s, color 0.2s;
        }
        .btn:active { background: #1e1e1e; }
        .btn.danger { border-color: #5a1f1f; color: #c0392b; }
        .btn.danger:active { background: #1e1010; }

        /* ---------- JOYSTICK ---------- */
        #joyBase {
            width: 180px;
            height: 180px;
            border-radius: 50%;
            border: 1px solid #2a2a2a;
            background: radial-gradient(circle at center, #1c1c1c 0%, #141414 100%);
            position: relative;
            touch-action: none;
        }

        #joyKnob {
            width: 72px;
            height: 72px;
            border-radius: 50%;
            background: radial-gradient(circle at 38% 35%, #3a3a3a, #1a1a1a);
            border: 1px solid #333;
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            pointer-events: none;
            transition: transform 0.08s ease-out;
            box-shadow: 0 2px 12px rgba(0,0,0,0.6);
        }

        /* crosshair lines on base */
        #joyBase::before, #joyBase::after {
            content: '';
            position: absolute;
            background: #222;
        }
        #joyBase::before { width: 1px; height: 60%; top: 20%; left: 50%; }
        #joyBase::after  { width: 60%; height: 1px; left: 20%; top: 50%; }

        /* ---------- DEBUG PANEL ---------- */
        .debugSection {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .debugLabel {
            font-size: 9px;
            letter-spacing: 0.15em;
            color: #333;
            text-transform: uppercase;
        }

        /* WiFi band pill */
        #wifiBand {
            font-size: 12px;
            letter-spacing: 0.08em;
            padding: 3px 0;
            color: #555;
        }
        #wifiBand.ghz5  { color: #2ecc71; }
        #wifiBand.ghz24 { color: #f1c40f; }

        /* Quaternion rows */
        .qRow {
            display: flex;
            justify-content: space-between;
            font-size: 11px;
            color: #444;
        }
        .qRow span.axis { color: #333; }
        .qRow span.val  { color: #666; font-variant-numeric: tabular-nums; }

        /* Status dot */
        #statusDot {
            width: 6px; height: 6px;
            border-radius: 50%;
            background: #333;
            display: inline-block;
            margin-right: 6px;
            vertical-align: middle;
        }
        #statusDot.active { background: #2ecc71; box-shadow: 0 0 6px #2ecc71; }

        #statusText {
            font-size: 10px;
            color: #444;
            letter-spacing: 0.05em;
            vertical-align: middle;
        }
    </style>
</head>
<body>

<!-- INIT SCREEN -->
<div id="initScreen">
    <p>BLENDER CAM</p>
    <button class="btn" id="connectBtn">ENABLE SENSORS</button>
</div>

<!-- MAIN APP (landscape) -->
<div id="app" style="display:none; width:100%; height:100%; flex-direction:row;">

    <!-- LEFT: joystick -->
    <div id="leftPanel" style="flex:1; display:flex; align-items:center; justify-content:center; position:relative;">
        <div id="joyBase">
            <div id="joyKnob"></div>
        </div>
    </div>

    <!-- RIGHT: debug -->
    <div id="rightPanel" style="width:160px; border-left:1px solid #1e1e1e; display:flex; flex-direction:column; justify-content:space-between; padding:18px 14px;">

        <div style="display:flex; flex-direction:column; gap:18px;">

            <div class="debugSection">
                <div class="debugLabel">status</div>
                <div>
                    <span id="statusDot"></span>
                    <span id="statusText">waiting</span>
                </div>
            </div>

            <div class="debugSection">
                <div class="debugLabel">wifi band</div>
                <div id="wifiBand">—</div>
            </div>

            <div class="debugSection">
                <div class="debugLabel">orientation</div>
                <div class="qRow"><span class="axis">w</span><span class="val" id="qw">—</span></div>
                <div class="qRow"><span class="axis">x</span><span class="val" id="qx">—</span></div>
                <div class="qRow"><span class="axis">y</span><span class="val" id="qy">—</span></div>
                <div class="qRow"><span class="axis">z</span><span class="val" id="qz">—</span></div>
            </div>

        </div>

        <button class="btn danger" id="stopBtn">STOP</button>

    </div>
</div>

<script>
    const connectBtn  = document.getElementById('connectBtn');
    const initScreen  = document.getElementById('initScreen');
    const appDiv      = document.getElementById('app');
    const statusDot   = document.getElementById('statusDot');
    const statusText  = document.getElementById('statusText');
    const wifiBandEl  = document.getElementById('wifiBand');
    const joyBase     = document.getElementById('joyBase');
    const joyKnob     = document.getElementById('joyKnob');
    const stopBtn     = document.getElementById('stopBtn');

    let phoneData = { q_x: 0, q_y: 0, q_z: 0, q_w: 1, joy_x: 0, joy_y: 0, sensor_ready: false };
    let joyActive = false;
    let joyOrigin = { x: 0, y: 0 };
    const JOY_RADIUS = 54; // max knob travel in px

    // --- WiFi band detection via timing (RTT heuristic) ---
    function detectWifiBand() {
        const t0 = performance.now();
        fetch('/ping?' + Date.now()).then(() => {
            const rtt = performance.now() - t0;
            // 5 GHz typically <10ms RTT on LAN, 2.4 GHz >15ms
            if (rtt < 14) {
                wifiBandEl.textContent = '5 GHz';
                wifiBandEl.className = 'ghz5';
            } else {
                wifiBandEl.textContent = '2.4 GHz';
                wifiBandEl.className = 'ghz24';
            }
        }).catch(() => {
            wifiBandEl.textContent = 'unknown';
            wifiBandEl.className = '';
        });
    }

    // --- Sensor init ---
    connectBtn.addEventListener('click', async () => {
        if (typeof AbsoluteOrientationSensor !== 'undefined') {
            try {
                await Promise.all([
                    navigator.permissions.query({ name: 'accelerometer' }),
                    navigator.permissions.query({ name: 'gyroscope' }),
                    navigator.permissions.query({ name: 'magnetometer' }),
                ]);
                const sensor = new AbsoluteOrientationSensor({ frequency: 60 });
                sensor.addEventListener('error', (e) => {
                    statusText.textContent = 'error';
                });
                sensor.addEventListener('reading', () => {
                    phoneData.q_x = sensor.quaternion[0];
                    phoneData.q_y = sensor.quaternion[1];
                    phoneData.q_z = sensor.quaternion[2];
                    phoneData.q_w = sensor.quaternion[3];
                    phoneData.sensor_ready = true;
                    updateDebug();
                });
                sensor.start();
                onSensorReady();
            } catch(e) {
                startDeviceOrientation();
            }
        } else {
            startDeviceOrientation();
        }
        setInterval(sendData, 16);
        detectWifiBand();
        setInterval(detectWifiBand, 5000);
    });

    function onSensorReady() {
        initScreen.style.display = 'none';
        appDiv.style.display = 'flex';
        statusDot.className = 'active';
        statusText.textContent = 'live';
    }

    function startDeviceOrientation() {
        function listen() {
            window.addEventListener('deviceorientation', (e) => {
                const a = (e.alpha||0)*Math.PI/180;
                const b = (e.beta ||0)*Math.PI/180;
                const g = (e.gamma||0)*Math.PI/180;
                const cy=Math.cos(a*.5),sy=Math.sin(a*.5);
                const cp=Math.cos(b*.5),sp=Math.sin(b*.5);
                const cr=Math.cos(g*.5),sr=Math.sin(g*.5);
                phoneData.q_w = cy*cp*cr+sy*sp*sr;
                phoneData.q_x = cy*sp*cr+sy*cp*sr;
                phoneData.q_y = sy*cp*cr-cy*sp*sr;
                phoneData.q_z = cy*cp*sr-sy*sp*cr;
                phoneData.sensor_ready = true;
                updateDebug();
            }, true);
        }
        if (typeof DeviceOrientationEvent !== 'undefined' &&
            typeof DeviceOrientationEvent.requestPermission === 'function') {
            DeviceOrientationEvent.requestPermission()
                .then(p => { if (p==='granted') { listen(); onSensorReady(); } })
                .catch(() => {});
        } else {
            listen();
            onSensorReady();
        }
    }

    // --- Debug update ---
    function updateDebug() {
        document.getElementById('qw').textContent = phoneData.q_w.toFixed(3);
        document.getElementById('qx').textContent = phoneData.q_x.toFixed(3);
        document.getElementById('qy').textContent = phoneData.q_y.toFixed(3);
        document.getElementById('qz').textContent = phoneData.q_z.toFixed(3);
    }

    // --- Joystick ---
    joyBase.addEventListener('touchstart', (e) => {
        e.preventDefault();
        const t = e.touches[0];
        const r = joyBase.getBoundingClientRect();
        joyOrigin = { x: r.left + r.width/2, y: r.top + r.height/2 };
        joyActive = true;
        moveKnob(t.clientX, t.clientY);
    }, { passive: false });

    joyBase.addEventListener('touchmove', (e) => {
        e.preventDefault();
        if (!joyActive) return;
        moveKnob(e.touches[0].clientX, e.touches[0].clientY);
    }, { passive: false });

    joyBase.addEventListener('touchend', () => {
        joyActive = false;
        phoneData.joy_x = 0;
        phoneData.joy_y = 0;
        joyKnob.style.transform = 'translate(-50%, -50%)';
    });

    function moveKnob(cx, cy) {
        let dx = cx - joyOrigin.x;
        let dy = cy - joyOrigin.y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        if (dist > JOY_RADIUS) {
            dx = dx / dist * JOY_RADIUS;
            dy = dy / dist * JOY_RADIUS;
        }
        joyKnob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
        phoneData.joy_x =  dx / JOY_RADIUS;
        phoneData.joy_y = -dy / JOY_RADIUS;
    }

    // --- Stop button ---
    stopBtn.addEventListener('click', () => {
        fetch('/stop', { method: 'POST' }).catch(() => {});
        statusDot.className = '';
        statusText.textContent = 'stopped';
        appDiv.style.display = 'none';
        initScreen.style.display = 'flex';
    });

    // --- Send loop ---
    function sendData() {
        fetch('/data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(phoneData)
        }).catch(() => {});
    }
</script>
</body>
</html>
"""

# ==========================================
# 2. THE HTTP SERVER (Background Thread)
# ==========================================
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif self.path.startswith('/ping'):
            # Used by the client to measure RTT for WiFi band detection
            self.send_response(200)
            self.end_headers()

    def do_POST(self):
        if self.path == '/stop':
            # Phone tapped Stop — signal Blender to stop streaming
            def stop_streaming():
                import bpy
                bpy.context.scene.phone_cam_props.is_streaming = False
                return None  # don't repeat
            import bpy
            bpy.app.timers.register(stop_streaming, first_interval=0.0)
            self.send_response(200)
            self.end_headers()
            return

        if self.path == '/data':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            global phone_data
            try:
                data = json.loads(post_data.decode('utf-8'))
                phone_data["q_x"] = data.get("q_x", 0.0)
                phone_data["q_y"] = data.get("q_y", 0.0)
                phone_data["q_z"] = data.get("q_z", 0.0)
                phone_data["q_w"] = data.get("q_w", 1.0)
                phone_data["joy_x"] = data.get("joy_x", 0.0)
                phone_data["joy_y"] = data.get("joy_y", 0.0)
                phone_data["sensor_ready"] = data.get("sensor_ready", False)
            except Exception:
                pass
            self.send_response(200)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress server logs in Blender console

def run_server():
    global httpd
    httpd = HTTPServer(('0.0.0.0', 8000), RequestHandler)
    httpd.serve_forever()

# ==========================================
# 3. PROPERTIES & UI (Blender Interface)
# ==========================================
class PhoneCamSettings(bpy.types.PropertyGroup):
    is_streaming: bpy.props.BoolProperty(name="Streaming", default=False)
    is_recording: bpy.props.BoolProperty(name="Recording", default=False)
    smoothing:    bpy.props.FloatProperty(name="Smoothing",   default=0.2, min=0.0, max=0.95)
    move_speed:   bpy.props.FloatProperty(name="Move Speed",  default=0.5, min=0.0, max=10.0)

class PHONECAM_OT_start_stream(bpy.types.Operator):
    bl_idname = "phonecam.start_stream"
    bl_label = "Start Streaming"
    bl_description = "Start listening for phone data and moving the camera"

    def execute(self, context):
        global server_thread
        props = context.scene.phone_cam_props
        if not context.scene.camera:
            self.report({'ERROR'}, "No active camera in the scene!")
            return {'CANCELLED'}
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        bpy.ops.phonecam.modal('INVOKE_DEFAULT')
        props.is_streaming = True
        self.report({'INFO'}, "Server started! Open http://[your-ip]:8000 on your phone.")
        return {'FINISHED'}

class PHONECAM_OT_stop_stream(bpy.types.Operator):
    bl_idname = "phonecam.stop_stream"
    bl_label = "Stop Streaming"
    bl_description = "Stop listening for phone data"

    def execute(self, context):
        global httpd
        props = context.scene.phone_cam_props
        props.is_streaming = False
        if httpd:
            httpd.shutdown()
            httpd = None
        return {'FINISHED'}

class PHONECAM_OT_toggle_record(bpy.types.Operator):
    bl_idname = "phonecam.toggle_record"
    bl_label = "Toggle Recording"
    bl_description = "Start/Stop inserting keyframes for the camera"

    def execute(self, context):
        props = context.scene.phone_cam_props
        props.is_recording = not props.is_recording
        if props.is_recording:
            if not context.screen.is_animation_playing:
                bpy.ops.screen.animation_play()
            self.report({'INFO'}, "Recording started! Move your phone.")
        else:
            if context.screen.is_animation_playing:
                bpy.ops.screen.animation_play()
            self.report({'INFO'}, "Recording stopped.")
        return {'FINISHED'}

# ==========================================
# 4. THE MODAL OPERATOR (The Engine)
# ==========================================
class PHONECAM_OT_modal(bpy.types.Operator):
    bl_idname = "phonecam.modal"
    bl_label = "Phone Cam Modal"

    _timer = None
    _current_frame = 0
    _debug_tick = 0  # throttle counter for temporary debug logging

    def modal(self, context, event):
        from mathutils import Quaternion

        props = context.scene.phone_cam_props
        if not props.is_streaming:
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            cam = context.scene.camera
            if not cam or not phone_data["sensor_ready"]:
                return {'PASS_THROUGH'}

            # --- Coordinate frame transformation (constant, computed once) ---
            # Phone's raw quaternion axes don't share the same labeling as
            # Blender's camera axes (empirically: phone z<->pitch, phone x<->roll,
            # phone y<->yaw). Q_FRAME is the proper rotation quaternion encoding
            # that correspondence. Applying it via conjugation (not component
            # swizzling) is mathematically exact at every rotation magnitude.
            Q_FRAME = Quaternion((0.5, 0.5, -0.5, -0.5))

            def phone_to_blender(q):
                return Q_FRAME @ q @ Q_FRAME.inverted()

            # --- CALIBRATION ---
            # Runs once when real sensor data first arrives.
            # We snapshot the phone's quaternion and the camera's quaternion at
            # that moment, then compute a fixed world-space mount offset.
            if not hasattr(self, '_is_calibrated'):
                self._is_calibrated = False

            if not self._is_calibrated:
                cam.rotation_mode = 'QUATERNION'
                self._start_cam_q = cam.rotation_quaternion.copy()

                start_phone_q = Quaternion((
                    phone_data["q_w"],
                    phone_data["q_x"],
                    phone_data["q_y"],
                    phone_data["q_z"],
                ))
                start_phone_q.normalize()

                # Transform phone's start orientation into Blender's axis frame,
                # then compute the fixed mount offset in that (now-shared) frame:
                # Q_cam = Q_phone_b @ Q_mount  =>  Q_mount = Q_phone_b^-1 @ Q_cam
                start_phone_q_b = phone_to_blender(start_phone_q)
                self._mount_q = start_phone_q_b.inverted() @ self._start_cam_q
                self._is_calibrated = True

            # --- APPLY ROTATION ---
            # Build current phone quaternion (raw sensor components)
            curr_phone_q = Quaternion((
                phone_data["q_w"],
                phone_data["q_x"],
                phone_data["q_y"],
                phone_data["q_z"],
            ))
            curr_phone_q.normalize()

            # Transform to Blender's axis frame, then apply the fixed mount
            # offset. This is the phone's true world-space rotation (not a
            # delta relative to the tilted calibration pose), re-labeled into
            # Blender axes and composed in world space -- exact at all angles.
            curr_phone_q_b = phone_to_blender(curr_phone_q)
            target_q = curr_phone_q_b @ self._mount_q

            # Dot-product check: ensure slerp always takes the short path
            if cam.rotation_quaternion.dot(target_q) < 0:
                target_q.negate()

            # --- TEMPORARY DEBUG LOGGING (remove after diagnosis) ---
            self._debug_tick += 1
            target_euler = target_q.to_euler()
            pitch_deg = math.degrees(target_euler.x)

            # Continuity check: how close is this frame's target_q to the last one?
            # Should stay near 1.0. A sudden drop means a real discontinuity.
            if not hasattr(self, '_prev_target_q'):
                self._prev_target_q = target_q.copy()
            continuity = self._prev_target_q.dot(target_q)
            flag = "  <<< FLAG: DISCONTINUITY" if abs(continuity) < 0.9 else ""

            # Dense logging once we're near-vertical (>55 deg), sparse otherwise
            near_vertical = abs(pitch_deg) > 55
            should_print = near_vertical or (self._debug_tick % 10 == 0)

            if should_print:
                cam_euler_before = cam.rotation_quaternion.to_euler()
                print(
                    "\n--- PhoneCam Debug ---\n"
                    f"curr_phone_q   : w={curr_phone_q.w: .3f} x={curr_phone_q.x: .3f} y={curr_phone_q.y: .3f} z={curr_phone_q.z: .3f}\n"
                    f"curr_phone_q_b : w={curr_phone_q_b.w: .3f} x={curr_phone_q_b.x: .3f} y={curr_phone_q_b.y: .3f} z={curr_phone_q_b.z: .3f}\n"
                    f"mount_q        : w={self._mount_q.w: .3f} x={self._mount_q.x: .3f} y={self._mount_q.y: .3f} z={self._mount_q.z: .3f}\n"
                    f"target_q       : w={target_q.w: .3f} x={target_q.x: .3f} y={target_q.y: .3f} z={target_q.z: .3f}\n"
                    f"target_euler(deg): x={math.degrees(target_euler.x): .1f} y={math.degrees(target_euler.y): .1f} z={math.degrees(target_euler.z): .1f}\n"
                    f"cam_euler_before(deg): x={math.degrees(cam_euler_before.x): .1f} y={math.degrees(cam_euler_before.y): .1f} z={math.degrees(cam_euler_before.z): .1f}\n"
                    f"continuity_dot : {continuity: .4f}{flag}"
                )

            self._prev_target_q = target_q.copy()

            factor = 1.0 - props.smoothing
            cam.rotation_quaternion = cam.rotation_quaternion.slerp(target_q, factor)

            # --- APPLY MOVEMENT ---
            forward_vec = cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))
            right_vec   = cam.matrix_world.to_quaternion() @ Vector((1, 0, 0))
            # Lock Z so movement stays on the ground plane (found-footage style)
            forward_vec.z = 0
            right_vec.z   = 0
            if forward_vec.length > 0: forward_vec.normalize()
            if right_vec.length   > 0: right_vec.normalize()

            cam.location += forward_vec * (phone_data["joy_y"] * props.move_speed * 0.1)
            cam.location += right_vec   * (phone_data["joy_x"] * props.move_speed * 0.1)

            # --- RECORDING ---
            if props.is_recording and context.scene.frame_current != self._current_frame:
                self._current_frame = context.scene.frame_current
                cam.keyframe_insert(data_path="location",            frame=self._current_frame)
                cam.keyframe_insert(data_path="rotation_quaternion", frame=self._current_frame)

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.016, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)

# ==========================================
# 5. UI PANEL
# ==========================================
class VIEW3D_PT_phone_camera(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Phone Cam'
    bl_label       = "Phone Camera Controller"

    def draw(self, context):
        layout = self.layout
        props  = context.scene.phone_cam_props

        if not context.scene.camera:
            box = layout.box()
            box.label(text="No Active Camera!", icon='ERROR')
            return

        row = layout.row(align=True)
        if not props.is_streaming:
            row.operator("phonecam.start_stream", icon='PLAY')
        else:
            row.operator("phonecam.stop_stream", icon='PAUSE')

        row = layout.row(align=True)
        if props.is_recording:
            row.operator("phonecam.toggle_record", text="Stop Recording",  icon='REC')
        else:
            row.operator("phonecam.toggle_record", text="Start Recording", icon='REC')

        layout.separator()
        box = layout.box()
        box.label(text="Settings", icon='MODIFIER')
        box.prop(props, "smoothing",  slider=True)
        box.prop(props, "move_speed", slider=True)

# ==========================================
# 6. REGISTRATION
# ==========================================
classes = (
    PhoneCamSettings,
    PHONECAM_OT_start_stream,
    PHONECAM_OT_stop_stream,
    PHONECAM_OT_toggle_record,
    PHONECAM_OT_modal,
    VIEW3D_PT_phone_camera,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.phone_cam_props = bpy.props.PointerProperty(type=PhoneCamSettings)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.phone_cam_props

if __name__ == "__main__":
    register()
