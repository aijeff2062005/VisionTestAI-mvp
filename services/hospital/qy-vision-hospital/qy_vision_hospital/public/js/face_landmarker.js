(function () {
    "use strict";

    console.log("[FaceLandmarker] Script loaded");

    let faceLandmarker = null;
    let lastVideoTime = -1;
    let animationFrameId = null;

    /*
    ========================================
    LOAD MEDIAPIPE 
    ========================================
    */

    const MEDIAPIPE_BASE_URL = "/assets/qy_vision_hospital/js/lib/mediapipe";
    const MEDIAPIPE_CDN_BASE =
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";

    // Resolved wasm/fileset base after a successful module import.
    let mediapipeFilesetBase = MEDIAPIPE_BASE_URL;

    let visionModulePromise = null;

    function loadMediaPipeViaScriptTag(moduleUrl) {
        /*
        Fallback when dynamic import() is blocked (Desk CSP / odd MIME /
        classic-script context). Loads as real type=module script.
        */
        return new Promise(function (resolve, reject) {
            const abs = new URL(moduleUrl, window.location.origin).href;
            const existing = document.querySelector(
                'script[data-mediapipe-vision="' + abs + '"]'
            );
            if (existing && window.MediaPipeVision) {
                resolve(window.MediaPipeVision);
                return;
            }

            const readyFlag = "__mediapipeVisionReady";
            const prev = window[readyFlag];
            window[readyFlag] = function (vision) {
                window[readyFlag] = prev;
                if (!vision) {
                    reject(new Error("module script returned empty vision"));
                    return;
                }
                resolve(vision);
            };

            const s = document.createElement("script");
            s.type = "module";
            s.dataset.mediapipeVision = abs;
            s.textContent =
                'import * as vision from "' + abs + '";\n' +
                'window.MediaPipeVision = vision;\n' +
                'if (typeof window.' + readyFlag + ' === "function") {\n' +
                '  window.' + readyFlag + '(vision);\n' +
                '}\n';
            s.onerror = function () {
                window[readyFlag] = prev;
                reject(new Error("module script failed: " + abs));
            };
            document.head.appendChild(s);
        });
    }

    async function importVisionModule(url) {
        try {
            return await import(
                /* webpackIgnore: true */
                url
            );
        } catch (err) {
            console.warn("[FaceLandmarker] import() failed for", url, err);
            return await loadMediaPipeViaScriptTag(url);
        }
    }

    function loadMediaPipe() {
        if (window.MediaPipeVision) {
            console.log("[FaceLandmarker] MediaPipe already loaded");
            return Promise.resolve(window.MediaPipeVision);
        }

        if (visionModulePromise) {
            return visionModulePromise;
        }

        console.log("[FaceLandmarker] Loading MediaPipe...");

        visionModulePromise = (async () => {
            const bust = "v=20260810";
            const candidates = [
                {
                    url: MEDIAPIPE_BASE_URL + "/vision_bundle.js?" + bust,
                    fileset: MEDIAPIPE_BASE_URL,
                },
                {
                    url: MEDIAPIPE_BASE_URL + "/vision_bundle.mjs?" + bust,
                    fileset: MEDIAPIPE_BASE_URL,
                },
                {
                    url: MEDIAPIPE_CDN_BASE + "/vision_bundle.mjs",
                    fileset: MEDIAPIPE_CDN_BASE,
                },
            ];

            let lastError = null;

            for (let i = 0; i < candidates.length; i++) {
                const c = candidates[i];
                try {
                    console.log("[FaceLandmarker] trying", c.url);
                    const vision = await importVisionModule(c.url);

                    if (!vision || !vision.FilesetResolver || !vision.FaceLandmarker) {
                        throw new Error(
                            "Module đã tải nhưng thiếu FilesetResolver/FaceLandmarker"
                        );
                    }

                    mediapipeFilesetBase = c.fileset;
                    window.MediaPipeVision = vision;
                    console.log(
                        "[FaceLandmarker] MediaPipe loaded from",
                        c.url
                    );
                    return vision;
                } catch (error) {
                    lastError = error;
                    console.warn("[FaceLandmarker] candidate failed", c.url, error);
                }
            }

            visionModulePromise = null;
            throw new Error(
                "Không thể tải MediaPipe Tasks Vision: " +
                (lastError && lastError.message
                    ? lastError.message
                    : String(lastError))
            );
        })();

        return visionModulePromise;
    }


    /*
    ========================================
    INIT FACE LANDMARKER
    ========================================
    */

    async function init() {

        if (faceLandmarker) {
            return faceLandmarker;
        }

        console.log("[FaceLandmarker] Initializing...");

        const vision = await loadMediaPipe();

        const FilesetResolver = vision.FilesetResolver;
        const FaceLandmarker = vision.FaceLandmarker;

        if (!FilesetResolver || !FaceLandmarker) {
            throw new Error("Không tìm thấy FilesetResolver hoặc FaceLandmarker.");
        }

        const filesetResolver = await FilesetResolver.forVisionTasks(
            `${mediapipeFilesetBase}/wasm`
        );

        faceLandmarker = await FaceLandmarker.createFromOptions(
            filesetResolver,
            {
                baseOptions: {
                    modelAssetPath:
                        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
                    delegate: "GPU",
                },
                runningMode: "VIDEO",
                numFaces: 1,
                minFaceDetectionConfidence: 0.5,
                minFacePresenceConfidence: 0.5,
                minTrackingConfidence: 0.5,
                outputFaceBlendshapes: true,
                outputFacialTransformationMatrixes: true,
            }
        );

        console.log("[FaceLandmarker] Ready!");

        return faceLandmarker;
    }


    /*
    ========================================
    DETECT FACE
    ========================================
    */

    function detect(videoElement) {

        if (!faceLandmarker) {
            console.warn("[FaceLandmarker] Not initialized");
            return null;
        }

        if (!videoElement || videoElement.readyState < 2) {
            return null;
        }

        if (videoElement.currentTime === lastVideoTime) {
            return null;
        }

        lastVideoTime = videoElement.currentTime;

        let result;

        try {
            result = faceLandmarker.detectForVideo(videoElement, performance.now());
        } catch (error) {
            console.error("[FaceLandmarker] Detection error:", error);
            return null;
        }

        if (!result.faceLandmarks || result.faceLandmarks.length === 0) {
            return {
                faceDetected: false,
                direction: "none",
                yaw: 0,
                pitch: 0,
                landmarks: null,
            };
        }

        const landmarks = result.faceLandmarks[0];

        const nose = landmarks[1];
        const leftEye = landmarks[33];
        const rightEye = landmarks[263];
        const forehead = landmarks[10];
        const chin = landmarks[152];


        const eyeCenterX = (leftEye.x + rightEye.x) / 2;
        const eyeDistance = Math.abs(rightEye.x - leftEye.x);
        const noseOffset = eyeDistance > 0 ? (nose.x - eyeCenterX) / eyeDistance : 0;
        // Camera preview is CSS-mirrored. Positive yaw = user turned to their right.
        const yaw = -noseOffset;

        let direction = "center";
        if (yaw < -0.15) {
            direction = "right";
        } else if (yaw > 0.15) {
            direction = "left";
        }



        const faceHeight = Math.abs(chin.y - forehead.y);
        const faceCenterY = (forehead.y + chin.y) / 2;
        const pitch = faceHeight > 0 ? (nose.y - faceCenterY) / faceHeight : 0;

        return {
            faceDetected: true,
            direction: direction,
            yaw: yaw,
            pitch: pitch,
            landmarks: landmarks,
            rawResult: result,
        };
    }


    /*
    ========================================
    START DETECTION LOOP
    ========================================
    */

    function start(videoElement, callback) {
        stop();

        function loop() {
            if (!videoElement) {
                return;
            }

            const result = detect(videoElement);

            if (result && callback) {
                callback(result);
            }

            animationFrameId = requestAnimationFrame(loop);
        }

        loop();
    }


    /*
    ========================================
    STOP
    ========================================
    */

    function stop() {
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
        }
        lastVideoTime = -1;
    }


    /*
    ========================================
    PUBLIC API
    ========================================
    */

    window.FaceLandmarkerService = {
        init: init,
        detect: detect,
        start: start,
        stop: stop,
    };

    console.log("[FaceLandmarker] Service registered");

})();