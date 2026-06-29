bl_info = {
    "name": "Phone Camera Controller",
    "author": "Moaaz Salama",
    "version": (0,0,1),
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
from mathutils import Euler, Vector

# Global dictionary to hold phone data
phone_data = {
    "yaw": 0.0,
    "pitch": 0.0,
    "roll": 0.0,
    "joy_x": 0.0,
    "joy_y": 0.0
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
    <title>Blender Cam Controller</title>
    <style>
        * { box-sizing: border-box; }
        body { margin: 0; background: #1a1a1a; color: white; font-family: sans-serif; height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; touch-action: none; }
        #status { margin-bottom: 10px; font-size: 16px; text-align: center; padding: 0 20px; }
        #connectBtn { padding: 15px 30px; font-size: 20px; background: #4d7a4d; color: white; border: none; border-radius: 10px; cursor: pointer; margin-bottom: 10px; }
        #debug { font-size: 12px; color: #aaa; text-align: center; padding: 8px; background: #2a2a2a; border-radius: 6px; width: 90%; margin-bottom: 10px; min-height: 60px; }
        #joystickArea { position: absolute; bottom: 0; left: 0; width: 50%; height: 45%; background: rgba(255,255,255,0.05); border-top: 1px solid rgba(255,255,255,0.1); border-right: 1px solid rgba(255,255,255,0.1); }
        #joystickLabel { position: absolute; top: 8px; left: 50%; transform: translateX(-50%); font-size: 11px; color: #666; pointer-events: none; }
        #joystick { position: absolute; width: 80px; height: 80px; background: rgba(255,255,255,0.3); border-radius: 50%; transform: translate(-50%, -50%); display: none; pointer-events: none; }
    </style>
</head>
<body>
    <div id="status">Tap the button to enable motion sensors</div>
    <button id="connectBtn">&#x1F4F1; Enable Motion Sensors</button>
    <div id="debug">Sensor data will appear here...</div>

    <div id="joystickArea">
        <div id="joystickLabel">MOVE (drag here)</div>
    </div>
    <div id="joystick"></div>

    <script>
        let joyActive = false;
        let sensorFired = false;
        const connectBtn = document.getElementById('connectBtn');
        const statusDiv = document.getElementById('status');
        const debugDiv = document.getElementById('debug');
        const joystick = document.getElementById('joystick');
        const joystickArea = document.getElementById('joystickArea');

        let phoneData = { yaw: 0, pitch: 0, roll: 0, joy_x: 0, joy_y: 0 };

        connectBtn.addEventListener('click', async () => {
            debugDiv.innerText = 'Button clicked...';

            // iOS Safari needs an explicit permission prompt
            if (typeof DeviceOrientationEvent !== 'undefined' &&
                typeof DeviceOrientationEvent.requestPermission === 'function') {
                try {
                    const permission = await DeviceOrientationEvent.requestPermission();
                    if (permission === 'granted') {
                        startSensors();
                    } else {
                        statusDiv.innerText = 'Permission denied.';
                        debugDiv.innerText = 'iOS sensor permission was denied by user.';
                    }
                } catch(e) {
                    statusDiv.innerText = 'Permission error.';
                    debugDiv.innerText = 'Error requesting permission: ' + e;
                }
            } else if (typeof DeviceOrientationEvent !== 'undefined') {
                // Android (Chrome, Firefox) — no JS permission needed, just start
                startSensors();
            } else {
                statusDiv.innerText = 'Sensors not supported on this browser.';
                debugDiv.innerText = 'DeviceOrientationEvent is undefined on this device/browser.';
            }
        });

        function startSensors() {
            connectBtn.style.display = 'none';
            statusDiv.innerText = 'Waiting for first sensor event...';
            debugDiv.innerHTML = 'Registered listener. Move your phone to trigger...<br><br>' +
                '<small>If nothing appears: Android Settings \u2192 Apps \u2192 Firefox \u2192 Permissions \u2192 enable <b>Motion sensors</b></small>';

            window.addEventListener('deviceorientation', (event) => {
                if (!sensorFired) {
                    sensorFired = true;
                    statusDiv.innerText = '\u2705 Sensors Active! Streaming to Blender...';
                }
                phoneData.yaw   = event.alpha != null ? event.alpha : 0;
                phoneData.pitch = event.beta  != null ? event.beta  : 0;
                phoneData.roll  = event.gamma != null ? event.gamma : 0;

                debugDiv.innerHTML =
                    'YAW &nbsp;(alpha): <b>' + phoneData.yaw.toFixed(1)   + '&deg;</b><br>' +
                    'PITCH (beta):&nbsp; <b>' + phoneData.pitch.toFixed(1) + '&deg;</b><br>' +
                    'ROLL &nbsp;(gamma): <b>' + phoneData.roll.toFixed(1)  + '&deg;</b>';
            }, true);

            // Also try deviceorientationabsolute as a fallback (some Android devices)
            window.addEventListener('deviceorientationabsolute', (event) => {
                if (sensorFired) return; // already working
                sensorFired = true;
                statusDiv.innerText = '\u2705 Sensors Active (absolute)! Streaming...';
                phoneData.yaw   = event.alpha != null ? event.alpha : 0;
                phoneData.pitch = event.beta  != null ? event.beta  : 0;
                phoneData.roll  = event.gamma != null ? event.gamma : 0;
            }, true);

            setInterval(sendData, 33);
        }

        // ---- Joystick ----
        joystickArea.addEventListener('touchstart', (e) => {
            e.preventDefault();
            joyActive = true;
            joystick.style.display = 'block';
            updateJoystick(e);
        }, { passive: false });

        joystickArea.addEventListener('touchmove', (e) => {
            e.preventDefault();
            if (joyActive) updateJoystick(e);
        }, { passive: false });

        joystickArea.addEventListener('touchend', () => {
            joyActive = false;
            joystick.style.display = 'none';
            phoneData.joy_x = 0;
            phoneData.joy_y = 0;
        });

        function updateJoystick(e) {
            const touch = e.touches[0];
            const rect = joystickArea.getBoundingClientRect();
            let x = touch.clientX - rect.left;
            let y = touch.clientY - rect.top;

            joystick.style.left = x + 'px';
            joystick.style.top  = y + 'px';

            phoneData.joy_x =  (x / rect.width)  * 2 - 1;
            phoneData.joy_y = -((y / rect.height) * 2 - 1);
        }

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

    def do_POST(self):
        if self.path == '/data':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            global phone_data
            try:
                data = json.loads(post_data.decode('utf-8'))
                phone_data["yaw"] = data.get("yaw", 0.0)
                phone_data["pitch"] = data.get("pitch", 0.0)
                phone_data["roll"] = data.get("roll", 0.0)
                phone_data["joy_x"] = data.get("joy_x", 0.0)
                phone_data["joy_y"] = data.get("joy_y", 0.0)
            except Exception as e:
                pass
            
            self.send_response(200)
            self.end_headers()

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
    smoothing: bpy.props.FloatProperty(name="Smoothing", default=0.2, min=0.0, max=0.95)
    move_speed: bpy.props.FloatProperty(name="Move Speed", default=0.5, min=0.0, max=10.0)

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
        
        # Automatically play/pause the timeline when recording is toggled!
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

    def modal(self, context, event):
        props = context.scene.phone_cam_props
        if not props.is_streaming:
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            cam = context.scene.camera
            if cam:
                # --- CALIBRATION (Prevents snapping to a fixed position) ---
                # We only calibrate once when streaming starts
                if not hasattr(self, '_is_calibrated'):
                    self._is_calibrated = False
                
                # Wait until the phone actually sends real data (not zeros)
                # CALOBRATION
                if not self._is_calibrated and (phone_data["yaw"] != 0.0 or phone_data["pitch"] != 0.0):
                    cam.rotation_mode = 'QUATERNION'
                    self._start_cam_q = cam.rotation_quaternion.copy()

                    self._start_phone_pitch = math.radians(phone_data["roll"])
                    self._start_phone_yaw   = math.radians(phone_data["yaw"])

                    self._is_calibrated = True

                # --- APPLY ROTATION (Quaternion) ---
                if self._is_calibrated:
                    curr_phone_pitch = math.radians(phone_data["roll"])
                    curr_phone_yaw   = math.radians(phone_data["yaw"])

                    delta_pitch = -(curr_phone_pitch - self._start_phone_pitch)
                    delta_yaw   =   (curr_phone_yaw   - self._start_phone_yaw)   # FIX: removed negation to fix inverted left/right

                    if delta_yaw >  math.pi: delta_yaw -= 2 * math.pi
                    if delta_yaw < -math.pi: delta_yaw += 2 * math.pi

                    # FIX: Shift pitch window upward by 20° so the "straight ahead" pose
                    # is higher, and clamp to ±60° to prevent gimbal-flip zone.
                    PITCH_SHIFT = math.radians(20.0)   # positive = raises the view
                    PITCH_LIMIT = math.radians(60.0)   # half-window before flip zone
                    delta_pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, delta_pitch + PITCH_SHIFT))

                    from mathutils import Quaternion

                    # Build delta quaternions for each axis independently
                    q_pitch = Quaternion((1, 0, 0), delta_pitch)
                    q_yaw   = Quaternion((0, 0, 1), delta_yaw)

                    # Compose: start rotation → apply yaw globally → apply pitch locally
                    target_q = q_yaw @ self._start_cam_q @ q_pitch

                    factor = 1.0 - props.smoothing
                    cam.rotation_quaternion = cam.rotation_quaternion.slerp(target_q, factor)
                
                # --- APPLY MOVEMENT ---
                forward_vec = cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))
                right_vec = cam.matrix_world.to_quaternion() @ Vector((1, 0, 0))
                
                cam.location += forward_vec * (phone_data["joy_y"] * props.move_speed * 0.1)
                cam.location += right_vec * (phone_data["joy_x"] * props.move_speed * 0.1)

                # --- RECORDING ---
                if props.is_recording and context.scene.frame_current != self._current_frame:
                    self._current_frame = context.scene.frame_current
                    cam.keyframe_insert(data_path="location", frame=self._current_frame)
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

class VIEW3D_PT_phone_camera(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Phone Cam'
    bl_label = "Phone Camera Controller"

    def draw(self, context):
        layout = self.layout
        props = context.scene.phone_cam_props

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
            # Changed icon to 'REC'
            row.operator("phonecam.toggle_record", text="Stop Recording", icon='REC')
        else:
            # Changed icon to 'REC'
            row.operator("phonecam.toggle_record", text="Start Recording", icon='REC')

        layout.separator()
        box = layout.box()
        box.label(text="Settings", icon='MODIFIER')
        box.prop(props, "smoothing", slider=True)
        box.prop(props, "move_speed", slider=True)

# ==========================================
# 5. REGISTRATION
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