    const connectBtn  = document.getElementById('connectBtn');
    const initScreen  = document.getElementById('initScreen');
    const appDiv      = document.getElementById('app');
    const statusDot   = document.getElementById('statusDot');
    const statusText  = document.getElementById('statusText');
    const wifiBandEl  = document.getElementById('wifiBand');
    const joyBase     = document.getElementById('joyBase');
    const joyKnob     = document.getElementById('joyKnob');
    const stopBtn     = document.getElementById('stopBtn');
    const recordBtn   = document.getElementById('recordBtn');
    const recalBtn    = document.getElementById('recalBtn');
    const recIndicator = document.getElementById('recIndicator');
    const recText     = document.getElementById('recText');

    let phoneData = { q_x: 0, q_y: 0, q_z: 0, q_w: 1, joy_x: 0, joy_y: 0, sensor_ready: false };
    let joyActive = false;
    let joyOrigin = { x: 0, y: 0 };
    const JOY_RADIUS = 54; // max knob travel in px

    // --- Connection health ---
    let consecutiveFailures = 0;
    const DISCONNECT_THRESHOLD = 3; // consecutive failed /data posts before flagging disconnected

    function markConnected() {
        consecutiveFailures = 0;
        if (statusDot.classList.contains('disconnected')) {
            statusDot.className = 'active';
            statusText.textContent = 'live';
        }
    }

    function markFailure() {
        consecutiveFailures++;
        if (consecutiveFailures >= DISCONNECT_THRESHOLD) {
            statusDot.className = 'disconnected';
            statusText.textContent = 'disconnected';
        }
    }

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
        pollStatus();
        setInterval(pollStatus, 500);
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
        }).then(() => markConnected()).catch(() => markFailure());
    }

    // --- Status poll (recording indicator + secondary connection check) ---
    function pollStatus() {
        fetch('/status').then(r => r.json()).then(s => {
            markConnected();
            if (s.is_recording) {
                recIndicator.classList.add('active');
                recText.textContent = 'recording';
                recordBtn.classList.add('active');
                recordBtn.textContent = 'STOP RECORDING';
            } else {
                recIndicator.classList.remove('active');
                recText.textContent = 'not recording';
                recordBtn.classList.remove('active');
                recordBtn.textContent = 'START RECORDING';
            }
        }).catch(() => markFailure());
    }

    // --- Record button ---
    recordBtn.addEventListener('click', () => {
        fetch('/record', { method: 'POST' }).catch(() => {});
    });

    // --- Recalibrate button ---
    let recalFlashTimeout = null;
    recalBtn.addEventListener('click', () => {
        fetch('/recalibrate', { method: 'POST' }).catch(() => {});
        recalBtn.textContent = 'RECALIBRATED';
        clearTimeout(recalFlashTimeout);
        recalFlashTimeout = setTimeout(() => { recalBtn.textContent = 'RECALIBRATE'; }, 800);
    });
