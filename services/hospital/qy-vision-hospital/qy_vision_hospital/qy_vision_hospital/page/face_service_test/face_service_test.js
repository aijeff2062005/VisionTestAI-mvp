frappe.pages["face-service-test"].on_page_load = async function (wrapper) {

    /*
    ========================================
    PAGE
    ========================================
    */

    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Face Service Test",
        single_column: true,
    });


    /*
    ========================================
    HTML + CSS
    ========================================
    */

    $(wrapper).find(".layout-main-section").html(`

        <style>

            /*
            ========================================
            MAIN
            ========================================
            */

            .face-service-test {
                max-width: 900px;
                margin: 0 auto;
                padding: 20px;
            }


            /*
            ========================================
            CAMERA CONTAINER
            ========================================
            */

            .face-camera-container {

                display: flex;

                flex-direction: column;

                align-items: center;

                margin-top: 25px;

            }


            /*
            ========================================
            CAMERA
            ========================================
            */

            .face-camera-wrapper {

                position: relative;

                width: 420px;

                height: 420px;

                overflow: hidden;

                background: #111;

                border-radius: 12px;

                border: 8px solid #e5e7eb;

                box-shadow:
                    0 0 0 4px #ffffff,
                    0 10px 40px rgba(0, 0, 0, 0.2);

            }


            #face-camera {

                width: 100%;

                height: 100%;

                object-fit: cover;

                transform: scaleX(-1);

            }

            .face-guide {
                position: absolute;

                top: 50%;
                left: 50%;

                width: 230px;
                height: 300px;

                transform:
                    translate(-50%, -50%)
                    rotate(45deg);

                border: 2px solid
                    rgba(255, 255, 255, 0.35);

                border-radius: 12px;

                pointer-events: none;

                z-index: 5;

                box-shadow:
                    0 0 8px
                    rgba(255, 255, 255, 0.15);
            }

            .face-guide::after {
                content: "";

                position: absolute;

                inset: 8px;

                border: 1px solid
                    rgba(255, 255, 255, 0.15);

                border-radius: 8px;
            }

            .face-dark-overlay {

                position: absolute;

                inset: 0;

                pointer-events: none;

                z-index: 2;

                background: rgba(
                    0,
                    0,
                    0,
                    0.55
                );


                clip-path: polygon(

                    0 0,
                    100% 0,
                    100% 100%,
                    0 100%,

                    0 0,

                    50% 17%,
                    83% 50%,
                    50% 83%,
                    17% 50%,

                    50% 17%

                );

            }
            /*
            ========================================
            SCAN OVERLAY
            ========================================
            */

            .face-scan-overlay {

                position: absolute;

                inset: 0;

                pointer-events: none;

                overflow: hidden;

                border-radius: 50%;

            }


            .scan-line {

                position: absolute;

                left: 15%;

                right: 15%;

                height: 2px;

                background: rgba(
                    34,
                    173,
                    197,
                    0.75
                );

                box-shadow:
                    0 0 8px #22adc5,
                    rgba(34, 173, 197, 0.8);


                opacity: 0;

            }


            /*
            Chỉ chạy scan khi đang recording
            */

            .face-camera-wrapper.scanning
            .scan-line {

                opacity: 1;

            }


            @keyframes scanAnimation {

                0% {

                    top: 10%;

                    opacity: 0;

                }

                10% {

                    opacity: 1;

                }

                50% {

                    top: 90%;

                }

                90% {

                    opacity: 1;

                }

                100% {

                    top: 10%;

                    opacity: 0;

                }

            }


            /*
            ========================================
            PROGRESS RING
            ========================================
            */

            .face-progress-ring {

                position: absolute;

                inset: 0;

                pointer-events: none;

            }


            .face-progress-ring svg {

                width: 100%;

                height: 100%;

            }


            /*
            Background ring
            */

            .progress-bg {

                fill: none;

                stroke:
                    rgba(255, 255, 255, 0.35);

                stroke-width: 8;

            }


            /*
            Progress ring
            */

            .progress-bar {

                fill: none;

                stroke: #22adc5;

                stroke-width: 8;

                stroke-linecap: round;

                /*
                Chuẩn hóa chu vi
                */

                stroke-dasharray: 100;

                stroke-dashoffset: 100;

                transition:
                    stroke-dashoffset
                    0.5s ease;

                filter:
                    drop-shadow(
                        0 0 5px
                        rgba(34, 170, 197, 0.8)
                    );

            }


            /*
            ========================================
            CHALLENGE
            ========================================
            */

            #face-challenge {

                margin-top: 20px;

                font-size: 20px;

                font-weight: 600;

                text-align: center;

                color: var(--heading-color, var(--text-color));

                min-height: 30px;

            }


            /*
            ========================================
            PROGRESS TEXT
            ========================================
            */

            #face-progress-text {

                margin-top: 8px;

                font-size: 16px;

                font-weight: 600;

                text-align: center;

                color: var(--text-muted, var(--text-light));

            }


            /*
            ========================================
            POSE STATUS
            ========================================
            */

            #face-pose-status {

                margin-top: 10px;

                text-align: center;

                font-size: 14px;

                color: var(--text-muted, var(--text-light));

                min-height: 24px;

            }


            /*
            ========================================
            STATUS
            ========================================
            */

            .face-status-box {

                margin-top: 15px;

                text-align: center;

            }


            /*
            ========================================
            AVATAR PREVIEW (frame from video)
            ========================================
            */

            #face-avatar-preview {
                display: none;
                margin-top: 28px;
                padding: 20px;
                text-align: center;
                background: var(--subtle-fg-color, var(--fg-color));
                border: 1px solid var(--border-color, #e2e8f0);
                border-radius: 12px;
            }

            #face-avatar-preview.is-visible {
                display: block;
            }

            #face-avatar-preview h4 {
                margin: 0 0 8px;
                font-size: 16px;
                font-weight: 600;
                color: var(--heading-color, var(--text-color));
            }

            #face-avatar-preview .avatar-hint {
                margin: 0 0 16px;
                font-size: 13px;
                color: var(--text-muted, var(--text-light));
            }

            #face-avatar-img {
                width: 220px;
                height: 220px;
                object-fit: cover;
                border-radius: 12px;
                border: 4px solid #e5e7eb;
                background: #111;
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
            }

            #face-avatar-preview .avatar-actions {
                margin-top: 16px;
                display: flex;
                gap: 10px;
                justify-content: center;
                flex-wrap: wrap;
            }

        </style>


        <div class="face-service-test">


            <!--
            ========================================
            USER INFO
            ========================================
            -->







            <!--
            ========================================
            CAMERA
            ========================================
            -->


            <div class="face-camera-container">


                <div
                    class="face-camera-wrapper"
                    id="face-camera-wrapper"
                >


                    <video
                        id="face-camera"
                        autoplay
                        muted
                        playsinline
                    ></video>

                    <!--
                    SCAN LINE
                    -->


                    <div
                        class="face-scan-overlay"
                    >

                        <div
                            class="scan-line"
                        ></div>

                    </div>


                    <!--
                    PROGRESS RING
                    -->


                    <div
                        class="face-progress-ring"
                    >

                        <svg
                            viewBox="0 0 360 460"
                        >


                            <!--
                            Background
                            -->


                            <ellipse
                                cx="180"
                                cy="230"
                                rx="170"
                                ry="220"
                                class="progress-bg"
                                pathLength="100"
                            />


                            <!--
                            Progress
                            -->


                            <ellipse
                                id="face-progress"
                                cx="180"
                                cy="230"
                                rx="170"
                                ry="220"
                                class="progress-bar"
                                pathLength="100"
                            />


                        </svg>

                    </div>


                </div>


                <!--
                CHALLENGE
                -->


                <div
                    id="face-challenge"
                >

                    Nhấn Start Camera

                </div>


                <!--
                PROGRESS
                -->


                <div
                    id="face-progress-text"
                >

                    0%

                </div>


                <!--
                POSE STATUS
                -->


                <div
                    id="face-pose-status"
                >

                    Chưa bắt đầu quét

                </div>


            </div>


            <!--
            ========================================
            AVATAR PREVIEW
            Frame from recorded video → patient confirms
            ========================================
            -->

            <div id="face-avatar-preview">

                <h4>Ảnh đại diện sẽ dùng</h4>

                <p class="avatar-hint">
                    Khung hình lấy từ video quét (khoảng 1 giây đầu).
                    Xác nhận để lưu vào hồ sơ bệnh nhân.
                </p>

                <img
                    id="face-avatar-img"
                    alt="Avatar preview"
                >

                <div class="avatar-actions">

                    <button
                        type="button"
                        class="btn btn-success"
                        id="confirm-avatar"
                    >
                        Xác nhận lưu avatar
                    </button>

                    <button
                        type="button"
                        class="btn btn-default"
                        id="retake-avatar"
                    >
                        Quay lại ghi hình
                    </button>

                </div>

            </div>


            </div>


            <!--
            ========================================
            BUTTONS
            ========================================
            -->
            <div class="form-group">

                <label>
                    Username
                </label>

                <input
                    type="text"
                    class="form-control"
                    id="face-username"
                    placeholder="Enter username"
                >

            </div>
            <div class="form-group">

                <label>
                    Full Name
                </label>

                <input
                    type="text"
                    class="form-control"
                    id="face-full-name"
                    placeholder="Enter full name"
                >

            </div>

            <div
                style="margin-top: 25px;"
            >


                <button
                    class="btn btn-primary"
                    id="start-camera"
                >

                    Start Camera

                </button>


                <button
                    class="btn btn-secondary"
                    id="start-recording"
                    disabled
                >

                    Start Recording

                </button>



                <button
                    class="btn btn-success"
                    id="register-face"
                    disabled
                >

                    Xem trước avatar

                </button>


                <button
                    class="btn btn-warning"
                    id="verify-face"
                    disabled
                >

                    Verify Face

                </button>


            </div>


            <!--
            ========================================
            STATUS
            ========================================
            -->



            <div
                id="face-status"
                style="margin-top: 20px;"
            ></div>


        </div>

    `);


    /*
    ========================================
    VARIABLES
    ========================================
    */

    let stream = null;

    let mediaRecorder = null;

    let recordedChunks = [];

    let recordedBlob = null;

    // JPEG data URL extracted from video for avatar preview / DB save
    let pendingAvatarB64 = null;

    // Patient from /desk/patient-registration → sessionStorage
    let facePatient = null;

    try {
        facePatient = JSON.parse(
            sessionStorage.getItem("face_registration_patient") || "null"
        );
    } catch (e) {
        facePatient = null;
    }


    /*
    Face Landmarker
    */

    let faceLandmarker = null;


    /*
    Progress
    */

    let currentProgress = 0;


    /*
    Recording state
    */

    let isRecording = false;


    function formatFrappeError(error) {
        if (error == null) {
            return "Unknown error";
        }
        if (typeof error === "string") {
            return error;
        }
        const serverMsgs = error._server_messages;
        if (serverMsgs) {
            try {
                const parsed = typeof serverMsgs === "string"
                    ? JSON.parse(serverMsgs)
                    : serverMsgs;
                const parts = (Array.isArray(parsed) ? parsed : [parsed]).map(function (item) {
                    if (typeof item === "string") {
                        try {
                            const obj = JSON.parse(item);
                            return obj.message || obj.title || item;
                        } catch (e) {
                            return item;
                        }
                    }
                    if (item && typeof item === "object") {
                        return item.message || item.title || JSON.stringify(item);
                    }
                    return String(item);
                });
                const text = parts.filter(Boolean).join("\n");
                if (text) {
                    return text;
                }
            } catch (e) {
                /* fall through */
            }
        }
        if (typeof error.message === "string" && error.message && error.message !== "[object Object]") {
            return error.message;
        }
        if (error.message && typeof error.message === "object") {
            return formatFrappeError(error.message);
        }
        if (error.exc) {
            const lines = String(error.exc).split("\n").filter(Boolean);
            if (lines.length) {
                return lines[lines.length - 1].replace(/^["'\s\[]+|["'\s\]]+$/g, "").slice(0, 400);
            }
        }
        try {
            return JSON.stringify(error);
        } catch (e) {
            return String(error);
        }
    }


    /*
    Current pose
    */

    let currentPoseIndex = 0;


    /*
    Pose stable timer
    */

    let poseStableStartTime = null;
    let isTransitioning = false;
    let pitchBaseline = null;
    let calibrationSamples = [];
    const CALIBRATION_SAMPLES_NEEDED = 15;
    /*
    Pose completion
    */

    let completedPoses = {

        center: false,

        left: false,

        right: false,

        up: false,

        down: false,

    };
    let registrationPatient = null;

    try {

        const patientData =
            sessionStorage.getItem(
                "face_registration_patient"
            );

        if (patientData) {

            registrationPatient =
                JSON.parse(patientData);

            console.log(
                "Patient đăng ký Face ID:",
                registrationPatient
            );

            $("#face-username").val(
                registrationPatient.patient || ""
            );

            $("#face-full-name").val(
                registrationPatient.patient_name || registrationPatient.patient || ""
            );

        }

    } catch (error) {

        console.error(
            "Không đọc được Patient data:",
            error
        );

    }

    /*
    ========================================
    POSE CONFIGURATION
    ========================================
    */

    const poses = [

        {
            key: "center",

            text:
                "Nhìn thẳng vào camera",

        },

        {
            key: "right",

            text:
                "Quay mặt sang phải",

        },

        {
            key: "left",

            text:
                "Quay mặt sang trái",

        },

        {
            key: "up",

            text:
                "Ngẩng mặt lên",

        },

        {

            key: "down",

            text:
                "Cúi mặt xuống",

        },

    ];


    /*
    ========================================
    DOM
    ========================================
    */

    const video =
        document.getElementById(
            "face-camera"
        );


    const cameraWrapper =
        document.getElementById(
            "face-camera-wrapper"
        );


    /*
    ========================================
    STATUS
    ========================================
    */

    function setStatus(
        message,
        type = "info"
    ) {

        let className =
            "alert alert-info";


        if (
            type === "success"
        ) {

            className =
                "alert alert-success";

        }


        if (
            type === "warning"
        ) {

            className =
                "alert alert-warning";

        }


        if (
            type === "danger"
        ) {

            className =
                "alert alert-danger";

        }


        $("#face-status").html(`

            <div class="${className}">

                ${message}

            </div>

        `);

    }


    /*
    ========================================
    EXTRACT 1 FRAME FROM RECORDED VIDEO (0–2s)
    Ideal still for AiFace / patient face id.
    ========================================
    */

    function extractFaceFrameJpeg(blob, preferSec) {
        preferSec = preferSec == null ? 1.0 : preferSec;

        return new Promise(function (resolve, reject) {
            if (!blob) {
                reject(new Error("No recorded video"));
                return;
            }

            const url = URL.createObjectURL(blob);
            const v = document.createElement("video");
            v.muted = true;
            v.playsInline = true;
            v.preload = "auto";
            v.src = url;

            function cleanup() {
                try {
                    URL.revokeObjectURL(url);
                } catch (e) {
                    /* ignore */
                }
            }

            function grab() {
                const w = v.videoWidth || 640;
                const h = v.videoHeight || 480;
                if (!w || !h) {
                    cleanup();
                    reject(new Error("Video has no dimensions"));
                    return;
                }
                const canvas = document.createElement("canvas");
                canvas.width = w;
                canvas.height = h;
                canvas.getContext("2d").drawImage(v, 0, 0, w, h);

                let quality = 0.82;
                let dataUrl = canvas.toDataURL("image/jpeg", quality);
                while (dataUrl.length > 480000 && quality > 0.4) {
                    quality -= 0.08;
                    dataUrl = canvas.toDataURL("image/jpeg", quality);
                }
                cleanup();
                v.pause();
                v.removeAttribute("src");
                v.load();
                resolve(dataUrl);
            }

            v.onloadedmetadata = function () {
                const dur = Number(v.duration);
                let t = preferSec;
                if (Number.isFinite(dur) && dur > 0) {
                    // Stay inside first 0–2s of the recording.
                    const maxT = Math.min(2.0, Math.max(0, dur - 0.05));
                    t = Math.min(Math.max(preferSec, 0), maxT);
                } else {
                    t = Math.min(Math.max(preferSec, 0), 2.0);
                }

                const onSeeked = function () {
                    v.removeEventListener("seeked", onSeeked);
                    grab();
                };
                v.addEventListener("seeked", onSeeked);

                try {
                    v.currentTime = t;
                } catch (seekErr) {
                    // Some browsers block seek on short webm — grab current frame.
                    grab();
                }
            };

            v.onerror = function () {
                cleanup();
                reject(new Error("Failed to load recorded video"));
            };
        });
    }


    function hideAvatarPreview() {
        pendingAvatarB64 = null;
        $("#face-avatar-preview").removeClass("is-visible");
        $("#face-avatar-img").attr("src", "");
        $("#confirm-avatar").prop("disabled", false);
    }

    function showAvatarPreview(dataUrl) {
        pendingAvatarB64 = dataUrl;
        $("#face-avatar-img").attr("src", dataUrl);
        $("#face-avatar-preview").addClass("is-visible");
        try {
            document
                .getElementById("face-avatar-preview")
                .scrollIntoView({ behavior: "smooth", block: "nearest" });
        } catch (e) {
            /* ignore */
        }
    }

    async function prepareAvatarPreviewFromVideo() {
        if (!recordedBlob) {
            throw new Error("Chưa có video ghi hình.");
        }
        const imageB64 = await extractFaceFrameJpeg(recordedBlob, 1.0);
        showAvatarPreview(imageB64);
        return imageB64;
    }

    // Prefill username / full name from patient registration hand-off.
    // Patient may be null when face is scanned before "Tạo hồ sơ".
    if (facePatient) {
        if (facePatient.patient && !$("#face-username").val()) {
            $("#face-username").val(facePatient.patient);
        }
        if (facePatient.patient_name && !$("#face-full-name").val()) {
            $("#face-full-name").val(facePatient.patient_name);
        }
    }


    /*
    ========================================
    UPDATE PROGRESS
    ========================================
    */

    function updateProgress(
        progress
    ) {

        progress =
            Math.max(
                0,
                Math.min(
                    100,
                    progress
                )
            );


        currentProgress =
            progress;


        /*
        100 -> 0
        0 -> 100
        */

        const offset =
            100 - progress;


        $("#face-progress").css(

            "stroke-dashoffset",

            offset

        );


        $("#face-progress-text").text(

            Math.round(
                progress
            ) + "%"

        );

    }


    /*
    ========================================
    RESET PROGRESS
    ========================================
    */

    function resetProgress() {
        isTransitioning = false; 
        pitchBaseline = null;
        calibrationSamples = [];
        currentProgress =
            0;


        currentPoseIndex =
            0;


        poseStableStartTime =
            null;


        completedPoses = {

            center: false,

            left: false,

            right: false,

            up: false,

            down: false,

        };


        /*
        Quan trọng:
        reset ring về 0%
        */

        $("#face-progress").css(

            "stroke-dashoffset",

            100

        );


        $("#face-progress-text").text(

            "0%"

        );


        $("#face-challenge").text(

            "Nhấn Start Camera"

        );


        $("#face-pose-status").text(

            "Chưa bắt đầu quét"

        );

    }


    /*
    ========================================
    GET CURRENT POSE
    ========================================
    */

    function getCurrentPose() {

        if (
            currentPoseIndex >=
            poses.length
        ) {

            return null;

        }


        return poses[
            currentPoseIndex
        ];

    }


    /*
    ========================================
    CHECK POSE
    ========================================
    */

    function isPoseCorrect(
        result,
        pose
    ) {

        if (
            !result ||
            !result.faceDetected
        ) {

            return false;

        }


        const yaw =
            result.yaw || 0;


        const pitch =
            result.pitch || 0;


        /*
        ========================================
        CENTER
        ========================================
        */

        if (
            pose === "center"
        ) {

            return (

                Math.abs(yaw) <
                0.15 &&

                pitch >
                -0.08 &&

                pitch <
                0.08

            );

        }


        /*
        ========================================
        LEFT
        ========================================
        */

        if (
            pose === "left"
        ) {

            return (

                yaw <
                -0.15

            );

        }


        /*
        ========================================
        RIGHT
        ========================================
        */

        if (
            pose === "right"
        ) {

            return (

                yaw >
                0.15

            );

        }


        /*
        ========================================
        UP
        ========================================
        */

        if (
            pose === "up"
        ) {

            return (

                pitch <
                -0.08

            );

        }


        /*
        ========================================
        DOWN
        ========================================
        */

        if (
            pose === "down"
        ) {

            return (

                pitch >
                0.02

            );

        }


        return false;

    }


    /*
    ========================================
    HANDLE FACE RESULT
    ========================================
    */
    function handleFaceResult(result) {
 
        if (!isRecording) {
            return;
        }
 
        if (isTransitioning) {
            return;
        }
 
        if (!result || !result.faceDetected) {
 
            $("#face-challenge").text("Không tìm thấy khuôn mặt");
            $("#face-pose-status").text("Đưa khuôn mặt vào giữa camera");
 
            poseStableStartTime = null;
 
            return;
        }
        const rawPitch = result.pitch || 0;

        // ===== HIỆU CHỈNH PITCH (chỉ chạy 1 lần lúc mới bắt đầu) =====
        if (pitchBaseline === null) {

            calibrationSamples.push(rawPitch);

            $("#face-challenge").text("Đang hiệu chỉnh...");
            $("#face-pose-status").text("Vui lòng giữ đầu thẳng, nhìn vào camera");

            if (calibrationSamples.length >= CALIBRATION_SAMPLES_NEEDED) {

                const sum = calibrationSamples.reduce(function (a, b) { return a + b; }, 0);

                pitchBaseline = sum / calibrationSamples.length;

                console.log("[Face Service Test] Pitch baseline:", pitchBaseline);
            }

            return;
        }
        if (currentPoseIndex >= poses.length) {
            return;
        }
 
        const currentPose = getCurrentPose();
 
        $("#face-challenge").text(currentPose.text);
 
        const adjustedResult = {
            faceDetected: result.faceDetected,
            yaw: result.yaw,
            pitch: rawPitch - pitchBaseline,
        };
        const correct = isPoseCorrect(adjustedResult, currentPose.key);
 
        if (correct) {
 
            if (!poseStableStartTime) {
                poseStableStartTime = Date.now();
            }
 
            const elapsed = Date.now() - poseStableStartTime;
 
            const requiredTime = 700;
 
            const poseProgress = Math.min(1, elapsed / requiredTime);
 
            const totalProgress =
                (currentPoseIndex + poseProgress) / poses.length * 100;
 
            updateProgress(totalProgress);
 
            $("#face-pose-status").text("Đang xác nhận tư thế...");
 
            if (elapsed >= requiredTime) {
 
                completedPoses[currentPose.key] = true;
 
                currentPoseIndex++;
 
                poseStableStartTime = null;
 
                updateProgress((currentPoseIndex / poses.length) * 100);
 
                if (currentPoseIndex < poses.length) {
 

                    const finishedPose = currentPose;
 
                    $("#face-challenge").text(
                        "✓ Hoàn thành: " + finishedPose.text
                    );
 
                    $("#face-pose-status").text(
                        "Tư thế đã xác nhận ✓ — chuẩn bị tư thế tiếp theo..."
                    );
 
                    isTransitioning = true;
 
                    setTimeout(function () {
 
                        isTransitioning = false;
 
                        // Nếu người dùng đã dừng recording trong lúc chờ thì thôi
                        if (!isRecording) {
                            return;
                        }
 
                        const nextPose = getCurrentPose();
 
                        $("#face-challenge").text(nextPose.text);
 
                        $("#face-pose-status").text(
                            "Vui lòng thực hiện tư thế trên"
                        );
 
                    }, 1000);
 
                }
 
                else {
 
                    updateProgress(100);
 
                    $("#face-challenge").text(
                        "Đã hoàn thành quét khuôn mặt ✓"
                    );
 
                    $("#face-pose-status").text(
                        "Đã hoàn thành quét"
                    );
 
                    setStatus(
                        "Đã hoàn thành xác thực chuyển động khuôn mặt.",
                        "success"
                    );
                    stopRecording(true);

                }
            }
        }
 
        else {
 
            poseStableStartTime = null;
 
            $("#face-pose-status").text(
                "Vui lòng điều chỉnh khuôn mặt theo hướng dẫn"
            );
        }
    }


    /*
    ========================================
    INIT FACE LANDMARKER
    ========================================
    */

    async function initFaceLandmarker() {

        /*
        Kiểm tra service
        */

        if (
            !window.FaceLandmarkerService
        ) {

            throw new Error(

                "Không tìm thấy FaceLandmarkerService."

            );

        }


        /*
        Init MediaPipe
        */

        faceLandmarker =
            await window
                .FaceLandmarkerService
                .init();


        if (
            !faceLandmarker
        ) {

            throw new Error(

                "Không thể khởi tạo Face Landmarker."

            );

        }


        console.log(

            "[Face Service Test] FaceLandmarker ready"

        );

    }


    /*
    ========================================
    START CAMERA
    ========================================
    */

    $("#start-camera").on(

        "click",

        async function () {

            try {

                /*
                Reset
                */

                resetProgress();


                /*
                Camera
                */

                stream =
                    await navigator
                        .mediaDevices
                        .getUserMedia({

                            video: {

                                facingMode:
                                    "user",

                            },

                            audio:
                                true,

                        });


                /*
                Attach video
                */

                video.srcObject =
                    stream;


                await video.play();


                /*
                Init Face Landmarker
                */

                setStatus(

                    "Đang khởi tạo Face Landmarker..."

                );


                await initFaceLandmarker();


                /*
                Camera ready
                */

                $("#start-recording")
                    .prop(
                        "disabled",
                        false
                    );


                $("#face-challenge").text(

                    "Nhấn Start Recording để bắt đầu"

                );


                $("#face-pose-status").text(

                    "Camera sẵn sàng"

                );


                setStatus(

                    "Camera đã sẵn sàng.",

                    "success"

                );

            }

            catch (
                error
            ) {

                console.error(
                    error
                );


                setStatus(

                    "Không thể khởi tạo camera hoặc Face Landmarker.",

                    "danger"

                );


                frappe.msgprint({

                    title:
                        "Face Landmarker Error",

                    message:
                        error.message,

                    indicator:
                        "red",

                });

            }

        }

    );

/*
========================================
STOP RECORDING FUNCTION
========================================
*/

        function stopRecording(isCompleted = false) {

            isRecording = false;


            /*
            Stop Face Landmarker
            */

            if (
                window.FaceLandmarkerService
            ) {

                window
                    .FaceLandmarkerService
                    .stop();

            }


            /*
            Stop scan animation
            */

            cameraWrapper.classList.remove(
                "scanning"
            );


            /*
            Stop recorder
            */

            if (

                mediaRecorder &&

                mediaRecorder.state !==
                "inactive"

            ) {

                mediaRecorder.stop();

            }


            /*
            Buttons
            */

            $("#start-recording")
                .prop(
                    "disabled",
                    false
                );


            /*
            Status
            */

            if (
                isCompleted
            ) {

                setStatus(
                    "Đã hoàn thành ghi hình.",
                    "success"
                );

            }

            else {

                setStatus(
                    "Đã dừng ghi hình. Chưa hoàn thành.",
                    "warning"
                );

            }

        }
    /*
    ========================================
    START RECORDING
    ========================================
    */

    $("#start-recording").on(

        "click",

        function () {

            /*
            Camera check
            */

            if (
                !stream
            ) {

                frappe.msgprint(

                    "Vui lòng Start Camera trước."

                );

                return;

            }


            /*
            MediaRecorder check
            */

            if (
                !window.MediaRecorder
            ) {

                frappe.msgprint(

                    "Trình duyệt không hỗ trợ MediaRecorder."

                );

                return;

            }


            /*
            Reset
            */

            recordedChunks =
                [];

            recordedBlob =
                null;

            hideAvatarPreview();


            resetProgress();


            /*
            Recording
            */

            try {

                mediaRecorder =
                    new MediaRecorder(

                        stream

                    );

            }

            catch (
                error
            ) {

                console.error(
                    error
                );

                frappe.msgprint(

                    error.message

                );

                return;

            }


            /*
            Data
            */

            mediaRecorder
                .ondataavailable =

                function (
                    event
                ) {

                    if (
                        event.data &&
                        event.data.size > 0
                    ) {

                        recordedChunks.push(

                            event.data

                        );

                    }

                };


            /*
            Stop
            */

            mediaRecorder
                .onstop =

                function () {

                    recordedBlob =
                        new Blob(

                            recordedChunks,

                            {

                                type:
                                    "video/webm",

                            }

                        );


                    $("#register-face")
                        .prop(

                            "disabled",

                            false

                        );


                    $("#verify-face")
                        .prop(

                            "disabled",

                            false

                        );


                    setStatus(

                        "Recording completed. Video size: " +

                        Math.round(

                            recordedBlob.size /
                            1024

                        ) +

                        " KB. Đang lấy khung hình avatar…",

                        "success"

                    );

                    prepareAvatarPreviewFromVideo()
                        .then(function () {
                            setStatus(
                                "Xem trước ảnh đại diện bên dưới. Xác nhận để lưu vào hồ sơ.",
                                "success"
                            );
                        })
                        .catch(function (err) {
                            console.error(err);
                            setStatus(
                                "Lấy khung hình thất bại: " +
                                (err.message || err) +
                                ". Có thể bấm «Xem trước avatar» để thử lại.",
                                "warning"
                            );
                        });

                };


            /*
            Start recording
            */

            mediaRecorder.start();


            isRecording =
                true;


            /*
            Start scan animation
            */

            cameraWrapper.classList.add(

                "scanning"

            );


            /*
            Buttons
            */

            $("#start-recording")
                .prop(

                    "disabled",

                    true

                );


            $("#stop-recording")
                .prop(

                    "disabled",

                    false

                );


            /*
            First challenge
            */

            $("#face-challenge").text(

                "Nhìn thẳng vào camera"

            );


            $("#face-pose-status").text(

                "Đang chờ xác nhận..."

            );


            setStatus(

                "Vui lòng điều chỉnh khuôn mặt theo hướng dẫn.",

                "info"

            );


            /*
            Start Face Landmarker
            */

            window
                .FaceLandmarkerService
                .start(

                    video,

                    function (
                        result
                    ) {

                        handleFaceResult(

                            result

                        );

                    }

                );

        }

    );



    /*
    ========================================
    REGISTER FACE
    Recorded video → grab 1 JPEG from 0–2s → AiFace avatar
    ========================================
    */

    $("#register-face").on(

        "click",

        async function () {

            const username =
                $("#face-username")
                    .val();


            const fullName =
                $("#face-full-name")
                    .val();


            if (
                !username
            ) {

                frappe.msgprint(

                    "Please enter username."

                );

                return;

            }


            if (
                !fullName
            ) {

                frappe.msgprint(

                    "Please enter full name."

                );

                return;

            }


            if (
                !recordedBlob
            ) {

                frappe.msgprint(

                    "Please record a video first."

                );

                return;

            }


            if (
                currentProgress <
                100
            ) {

                frappe.msgprint(

                    "Vui lòng hoàn thành ghi hình theo hướng dẫn."

                );

                return;

            }

            // Video scan stays as primitive; system uses 1 frame + preview.
            setStatus("Đang lấy khung hình từ video để xem trước avatar…");
            $("#register-face").prop("disabled", true);

            try {
                await prepareAvatarPreviewFromVideo();
                setStatus(
                    "Xem trước ảnh đại diện bên dưới. Bấm «Xác nhận lưu avatar» để ghi vào hồ sơ.",
                    "success"
                );
            } catch (error) {
                console.error(error);
                setStatus(
                    "Lấy khung hình thất bại: " + (error.message || error),
                    "danger"
                );
                frappe.msgprint({
                    title: "Preview Error",
                    message: String(error.message || error),
                    indicator: "red",
                });
            } finally {
                $("#register-face").prop("disabled", false);
            }

        }

    );


    /*
    ========================================
    CONFIRM AVATAR → DATABASE
    ========================================
    */

    $("#confirm-avatar").on(

        "click",

        async function () {

            const username =
                $("#face-username")
                    .val();

            const fullName =
                $("#face-full-name")
                    .val();

            if (!fullName) {
                frappe.msgprint("Please enter full name.");
                return;
            }

            if (!pendingAvatarB64) {
                frappe.msgprint(
                    "Chưa có ảnh xem trước. Hãy ghi hình video xong — ảnh sẽ hiện bên dưới để xác nhận."
                );
                return;
            }

            const patientId =
                (facePatient && facePatient.patient)
                || username
                || null;

            // Face scanned before patient exists: keep frame, attach on create.
            if (!patientId) {
                sessionStorage.setItem(
                    "pending_face_avatar",
                    JSON.stringify({
                        image_b64: pendingAvatarB64,
                        display_name: fullName,
                        uid: (facePatient && facePatient.uid) || "",
                    })
                );
                $("#confirm-avatar").prop("disabled", true);
                $("#retake-avatar").prop("disabled", true);
                setStatus(
                    "Đã giữ ảnh đại diện từ video. Quay lại «Tạo hồ sơ bệnh nhân» để gắn vào hồ sơ.",
                    "success"
                );
                frappe.msgprint({
                    title: "Đã lưu tạm ảnh đại diện",
                    message:
                        "Quét video xong. Hãy quay lại trang đăng ký và bấm «Tạo hồ sơ bệnh nhân» — ảnh này sẽ được gắn tự động.",
                    indicator: "green",
                });
                return;
            }

            setStatus("Đang lưu avatar + enroll_id vào hồ sơ…");
            $("#confirm-avatar").prop("disabled", true);
            $("#register-face").prop("disabled", true);

            try {
                const gduUser = String(username || patientId).trim();
                let gduNote = "";
                if (recordedBlob) {
                    try {
                        const gdu = await (
                            window.ClinicFaceEnroll && ClinicFaceEnroll.registerOnGdu
                                ? ClinicFaceEnroll.registerOnGdu(gduUser, fullName, recordedBlob)
                                : (async function () {
                                    const formData = new FormData();
                                    formData.append("username", gduUser);
                                    formData.append("full_name", fullName);
                                    formData.append("video", recordedBlob, "face_registration.webm");
                                    const response = await fetch(
                                        "/api/method/smart_hospital.api.face_service_api.register",
                                        {
                                            method: "POST",
                                            headers: {
                                                "X-Frappe-CSRF-Token": frappe.csrf_token,
                                            },
                                            body: formData,
                                        }
                                    );
                                    const result = await response.json();
                                    if (result.exc || result._server_messages) {
                                        throw new Error(formatFrappeError(result));
                                    }
                                    return result.message || result;
                                })()
                        );
                        console.log("GDU register:", gdu);
                        gduNote = " Video đã gửi GDU với username «" + gduUser + "».";
                    } catch (gduErr) {
                        console.warn("GDU Face Service skipped:", gduErr);
                    }
                }

                setStatus("Đang lưu avatar + enroll_id vào hồ sơ…");
                const res = await frappe.call({
                    method:
                        "smart_hospital.api.face_identity.register_patient_face_avatar",
                    args: {
                        patient: patientId,
                        image_b64: pendingAvatarB64,
                        display_name: fullName || patientId,
                        push_today: 1,
                    },
                });

                const msg = (res && res.message) || {};
                console.log("Confirm avatar → DB:", msg);

                if (!msg.success) {
                    throw new Error(
                        msg.error || "register_patient_face_avatar failed"
                    );
                }

                sessionStorage.removeItem("pending_face_avatar");

                const eid =
                    (msg.patient && msg.patient.aiface_enroll_id)
                    || "?";

                setStatus(
                    "Đã lưu ảnh đại diện (từ video) vào hồ sơ. Face ID #" + eid + "." + gduNote,
                    "success"
                );

                $("#confirm-avatar").prop("disabled", true);
                $("#retake-avatar").prop("disabled", true);

                frappe.msgprint({
                    title: "Đăng ký thành công",
                    message:
                        "Khung hình từ video đã được lưu làm avatar / Face ID #"
                        + eid
                        + " cho "
                        + patientId
                        + "."
                        + gduNote
                        + " Kiểm tra Milvus: project_id == \"smart-hospital\" và username == \""
                        + gduUser
                        + "\".",
                    indicator: "green",
                });

            } catch (error) {
                console.error(error);
                const detail = formatFrappeError(error);
                setStatus(
                    "Lưu avatar thất bại: " + detail,
                    "danger"
                );
                frappe.msgprint({
                    title: "Registration Error",
                    message: detail,
                    indicator: "red",
                });
                $("#confirm-avatar").prop("disabled", false);
            } finally {
                $("#register-face").prop("disabled", false);
            }

        }

    );


    /*
    ========================================
    RETAKE — clear preview, allow re-record
    ========================================
    */

    $("#retake-avatar").on(

        "click",

        function () {

            hideAvatarPreview();
            recordedBlob = null;
            recordedChunks = [];
            resetProgress();

            $("#confirm-avatar").prop("disabled", false);
            $("#retake-avatar").prop("disabled", false);

            if (stream) {
                $("#start-recording").prop("disabled", false);
            }

            $("#register-face").prop("disabled", true);
            $("#verify-face").prop("disabled", true);

            setStatus(
                "Đã hủy ảnh xem trước. Bấm Start Recording để quét lại.",
                "warning"
            );

        }

    );


    /*
    ========================================
    VERIFY FACE
    ========================================
    */

    $("#verify-face").on(

        "click",

        async function () {

            const username =
                $("#face-username")
                    .val();


            if (
                !username
            ) {

                frappe.msgprint(

                    "Please enter username."

                );

                return;

            }


            if (
                !recordedBlob
            ) {

                frappe.msgprint(

                    "Please record a video first."

                );

                return;

            }


            if (
                currentProgress <
                100
            ) {

                frappe.msgprint(

                    "Không thành công."

                );

                return;

            }


            const formData =
                new FormData();


            formData.append(

                "username",

                username

            );


            formData.append(

                "video",

                recordedBlob,

                "face_verification.webm"

            );


            setStatus(

                "Đang xác thực khuôn mặt..."

            );


            try {

                const response =
                    await fetch(

                        "/api/method/smart_hospital.api.face_service_api.verify",

                        {

                            method:
                                "POST",

                            headers: {

                                "X-Frappe-CSRF-Token":
                                    frappe.csrf_token,

                            },

                            body:
                                formData,

                        }

                    );


                const result =
                    await response.json();


                console.log(

                    "Verify response:",

                    result

                );


                if (
                    result.message
                ) {

                    const verification =
                        result.message;


                    /*
                    MASK
                    */

                    if (
                        verification.has_mask ===
                        true
                    ) {

                        setStatus(

                            "Phát hiện đeo mặt nạ.",

                            "warning"

                        );


                        frappe.msgprint({

                            title:
                                "Phát hiện đeo mặt nạ",

                            message:
                                "Vui lòng tháo mặt nạ và thực hiện xác thực lại.",

                            indicator:
                                "orange",

                        });

                    }


                    /*
                    RECOGNIZED
                    */

                    else if (

                        verification.is_face_recognized ===
                        true &&

                        verification.is_spoofing ===
                        false

                    ) {

                        setStatus(

                            "xác thực khuôn mặt thành công.",

                            "success"

                        );


                        frappe.msgprint({

                            title:
                                "Xác thực thành công",

                            message:
                                "Khuôn mặt đã được xác thực thành công.",

                            indicator:
                                "green",

                        });

                    }


                    /*
                    SPOOFING
                    */

                    else if (

                        verification.is_spoofing ===
                        true

                    ) {

                        setStatus(

                            "Phát hiện dấu hiệu giả mạo.",

                            "danger"

                        );


                        frappe.msgprint({

                            title:
                                "Cảnh báo",

                            message:
                                "Phát hiện dấu hiệu giả mạo khuôn mặt.",

                            indicator:
                                "red",

                        });

                    }


                    /*
                    FAILED
                    */

                    else {

                        setStatus(

                            "Nhận diện khuôn mặt thất bại.",

                            "danger"

                        );


                        frappe.msgprint({

                            title:
                                "Nhận diện thất bại",

                            message:
                                "Không thể xác thực khuôn mặt.",

                            indicator:
                                "red",

                        });

                    }

                }

                else {

                    setStatus(

                        "Verification failed.",

                        "danger"

                    );


                    frappe.msgprint({

                        title:
                            "Verification Error",

                        message:
                            "Không nhận được kết quả từ Face Service.",

                        indicator:
                            "red",

                    });

                }

            }

            catch (
                error
            ) {

                console.error(
                    error
                );


                frappe.msgprint({

                    title:
                        "Verification Error",

                    message:
                        error.message,

                    indicator:
                        "red",

                });

            }

        }

    );


    /*
    ========================================
    INITIAL STATE
    ========================================
    */

    resetProgress();


    console.log(

        "[Face Service Test] Page loaded"

    );

};