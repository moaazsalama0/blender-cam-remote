bl_info = {
    "name": "Phone Camera Controller",
    "author": "Moaaz Salama",
    "version": (0,1),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > Phone Cam",
    "description": "Control Blender camera via mobile phone sensors",
    "category": "Camera",
}

import bpy
import math
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from mathutils import Vector

# HTML/CSS/JS for the phone page now live in web/ as static files rather
# than being embedded as a giant string in this module.
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ADDON_DIR, "web")
STATIC_FILES = {
    "/": ("index.html", "text/html"),
    "/style.css": ("style.css", "text/css"),
    "/app.js": ("app.js", "application/javascript"),
}

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

# Set by the HTTP server thread when the phone taps "Recalibrate".
# Plain bool read/write is fine across threads (no bpy calls involved);
# the modal operator consumes and clears it on the main thread each tick.
recalibrate_requested = False

# Mirrors is_streaming/is_recording for the phone to poll via GET /status.
# Written by the modal operator (main thread) each tick, read by the HTTP
# server thread. Avoids touching bpy.context from off the main thread.
server_status = {
    "is_streaming": False,
    "is_recording": False,
}

# ==========================================
# 1. THE WEB APP (static files in web/, served below)
# ==========================================

# ==========================================
# 2. THE HTTP SERVER (Background Thread)
# ==========================================
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in STATIC_FILES:
            filename, content_type = STATIC_FILES[self.path]
            filepath = os.path.join(WEB_DIR, filename)
            try:
                with open(filepath, 'rb') as f:
                    content = f.read()
            except (FileNotFoundError, OSError):
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.end_headers()
            self.wfile.write(content)
        elif self.path.startswith('/ping'):
            # Used by the client to measure RTT for WiFi band detection
            self.send_response(200)
            self.end_headers()
        elif self.path.startswith('/status'):
            # Used by the client to poll recording state and confirm the
            # connection is still alive. Reads the plain-dict mirror kept
            # up to date by the modal operator -- no bpy access here, so
            # it's safe to call from this (non-main) server thread.
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(server_status).encode('utf-8'))

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

        if self.path == '/record':
            # Phone tapped Record — toggle recording on the main thread
            import bpy
            bpy.app.timers.register(_toggle_recording, first_interval=0.0)
            self.send_response(200)
            self.end_headers()
            return

        if self.path == '/recalibrate':
            # Phone tapped Recalibrate — flag the modal operator to
            # re-snapshot the phone's current pose as the new neutral
            # on its next tick. Plain bool, no bpy call needed here.
            global recalibrate_requested
            recalibrate_requested = True
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

def _toggle_recording():
    """Flip is_recording and start/stop timeline playback to match.
    Must run on Blender's main thread (calls bpy.ops). Shared by the
    Blender panel operator and the phone's HTTP /record endpoint so
    both paths behave identically.
    """
    props = bpy.context.scene.phone_cam_props
    props.is_recording = not props.is_recording
    if props.is_recording:
        if not bpy.context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()
    else:
        if bpy.context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()
    return None  # don't repeat (one-shot timer)


class PHONECAM_OT_toggle_record(bpy.types.Operator):
    bl_idname = "phonecam.toggle_record"
    bl_label = "Toggle Recording"
    bl_description = "Start/Stop inserting keyframes for the camera"

    def execute(self, context):
        was_recording = context.scene.phone_cam_props.is_recording
        _toggle_recording()
        if not was_recording:
            self.report({'INFO'}, "Recording started! Move your phone.")
        else:
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
        from mathutils import Quaternion

        props = context.scene.phone_cam_props
        if not props.is_streaming:
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            global recalibrate_requested
            server_status["is_streaming"] = props.is_streaming
            server_status["is_recording"] = props.is_recording

            cam = context.scene.camera
            if not cam or not phone_data["sensor_ready"]:
                return {'PASS_THROUGH'}

            if recalibrate_requested:
                self._is_calibrated = False
                recalibrate_requested = False

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
