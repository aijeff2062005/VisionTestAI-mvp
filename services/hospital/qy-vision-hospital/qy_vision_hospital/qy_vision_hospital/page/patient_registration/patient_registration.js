frappe.pages['patient-registration'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Đăng ký bệnh nhân'),
		single_column: true
	});
        $(wrapper)
            .find(".layout-main-section")
            .html(`
            <div class="pr-page">
            <style>
                .pr-page {
                    font-family: var(--font-stack, inherit);
                    color: var(--text-color);
                    background: transparent;
                    margin: 0;
                    padding: 8px 0 24px;
                }
                .pr-page .pr-card {
                    max-width: 900px;
                    margin: 0 auto;
                    background: var(--fg-color, var(--card-bg, transparent));
                    color: var(--text-color);
                    padding: 30px;
                    border-radius: var(--border-radius-md, 12px);
                    border: 1px solid var(--border-color, transparent);
                    box-shadow: var(--shadow-sm, none);
                    display: flex;
                    flex-direction: column;
                }
                .pr-page .pr-titlebar {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    flex-wrap: wrap;
                    gap: 12px;
                    margin-bottom: 8px;
                }
                .pr-page .pr-titlebar h1 {
                    font-size: 24px;
                    margin: 0;
                    color: var(--heading-color, var(--text-color));
                }
                .pr-page .pr-titlebar p,
                .pr-page .pr-section-label {
                    margin: 0;
                    color: var(--text-muted, var(--text-light));
                }
                .pr-page .pr-section-header {
                    margin-top: 16px;
                }
                .pr-page .pr-section-label {
                    font-weight: 600;
                }
                .pr-page .form-grid {
                    margin-top: 15px;
                    display: grid;
                    background: transparent;
                    grid-template-columns: 1fr 1fr;
                    border: none;
                    gap: 16px;
                }
                .pr-page .pr-titlebar {
                    order: 1;
                }
                .pr-page #cccd-scanner {
                    order: 2;
                }
                .pr-page .pr-section-header {
                    order: 3;
                }
                .pr-page .form-grid {
                    order: 4;
                }
                .pr-page .detail {
                    order: 5;
                }
                .pr-page .actions {
                    order: 6;
                }
                .pr-page #status {
                    order: 7;
                }
                .pr-page .form-group {
                    display: flex;
                    flex-direction: column;
                }
                .pr-page .form-group:has(#dob),
                .pr-page .form-group:has(#cccd-address),
                .pr-page .form-group:has(#register-face),
                .pr-page .pr-section-header,
                .pr-page .detail,
                .pr-page #scan-cccd {
                    display: none !important;
                }
                .pr-page label {
                    font-weight: 600;
                    margin-bottom: 6px;
                    color: var(--text-color);
                }
                .pr-page input,
                .pr-page select,
                .pr-page textarea {
                    padding: 10px;
                    border: 1px solid var(--border-color, #ddd);
                    border-radius: var(--border-radius, 6px);
                    background: var(--control-bg, var(--fg-color));
                    color: var(--text-color);
                    color-scheme: inherit;
                }
                .pr-page input::placeholder,
                .pr-page textarea::placeholder {
                    color: var(--text-muted, var(--text-light));
                }
                .pr-page .full {
                    grid-column: 1 / -1;
                }
                .pr-page .detail {
                    margin-top: 20px;
                    border: 1px solid var(--border-color, #ddd);
                    border-radius: 8px;
                    padding: 12px 16px;
                    background: var(--subtle-fg-color, var(--bg-color));
                }
                .pr-page .detail summary {
                    cursor: pointer;
                    font-weight: bold;
                    color: var(--heading-color, var(--text-color));
                    padding: 4px;
                }
                .pr-page .detail-content {
                    margin-top: 20px;
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 16px;
                }
                .pr-page .actions {
                    margin-top: 25px;
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                }
                .pr-page .actions button {
                    padding: 12px 20px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-weight: 600;
                }
                .pr-page .actions button:disabled {
                    opacity: 0.7;
                    cursor: not-allowed;
                }
                .pr-page #scan-cccd {
                    min-height: 42px;
                    padding: 10px 16px;
                    flex-shrink: 0;
                    border: 1px solid var(--primary, #2563eb);
                    border-radius: 6px;
                    background: var(--primary, #2563eb);
                    color: #fff;
                    cursor: pointer;
                    font-weight: 600;
                    white-space: nowrap;
                }
                .pr-page #scan-cccd:disabled {
                    opacity: 0.7;
                    cursor: not-allowed;
                }
                .pr-page #register-face {
                    padding: 12px 20px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-weight: 600;
                    background: #2563eb;
                    color: #fff;
                    border: 1px solid #2563eb;
                }
                .pr-page #register-face:disabled {
                    opacity: 0.7;
                    cursor: not-allowed;
                }
                .pr-page #create-patient {
                    background: var(--invert-neutral, #171717);
                    color: var(--bg-color, #fff);
                    border: 1px solid var(--invert-neutral, #171717);
                }
                .pr-page #close-cccd-scanner {
                    padding: 12px 20px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-weight: 600;
                    background: var(--control-bg, #f3f3f3);
                    color: var(--text-color);
                    border: 1px solid var(--border-color, #d1d5db);
                }
                .pr-page #status {
                    margin-top: 20px;
                    padding: 12px;
                    border-radius: 6px;
                    background: var(--subtle-fg-color, var(--control-bg));
                    color: var(--text-color);
                    white-space: pre-wrap;
                }
                .pr-page #status.success {
                    background: var(--bg-green, #dcfce7);
                    color: var(--text-on-green, #166534);
                }
                .pr-page #status.error {
                    background: var(--bg-red, #fee2e2);
                    color: var(--text-on-red, #991b1b);
                }
                .pr-page #status.warning {
                    background: var(--bg-yellow, #fef3c7);
                    color: var(--text-on-yellow, #92400e);
                }
                .pr-page .pr-face-field {
                    display: flex;
                    gap: 16px;
                    align-items: flex-start;
                    flex-wrap: wrap;
                }
                .pr-page .pr-face-thumb {
                    width: 112px;
                    height: 112px;
                    border-radius: 12px;
                    border: 1px solid var(--border-color, #d1d5db);
                    background: var(--control-bg, #f3f3f3);
                    overflow: hidden;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    flex-shrink: 0;
                }
                .pr-page .pr-face-thumb img {
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                }
                .pr-page .pr-face-placeholder {
                    font-size: 12px;
                    text-align: center;
                    padding: 8px;
                    color: var(--text-muted, var(--text-light));
                }
                .pr-page .pr-face-meta {
                    flex: 1;
                    min-width: 200px;
                }
                .pr-page .pr-face-meta p {
                    margin: 0 0 10px;
                    color: var(--text-muted, var(--text-light));
                    font-size: 13px;
                }
                .pr-page #face-enroll {
                    display: none;
                    margin-top: 14px;
                }
                .pr-page #face-enroll.is-open {
                    display: block;
                }
                @media (max-width: 640px) {
                    .pr-page #scan-cccd {
                        width: 100%;
                    }
                    .pr-page .form-grid,
                    .pr-page .detail-content {
                        grid-template-columns: 1fr;
                    }
                }
                @keyframes cccdScanLine {
                    0%, 100% { transform: translateY(0); }
                    50% { transform: translateY(320px); }
                }
            </style>
            <div class="pr-card">
            <div class="pr-titlebar">
                <h1
                    style="
                        font-size: 24px;
                        margin: 0;
                    "
                >
                    ${__("Create patient profile")}
                </h1>

                <button id="scan-cccd" type="button">
                    ${__("Scan CCCD")}
                </button>
                </div>
                <div class="pr-section-header">
                    <span class="pr-section-label">${__("Patient information")}</span>
                </div>
                <div class="form-grid">


                    <!-- HỌ TÊN -->
                    <div class="form-group">
                        <label>${__("Full name")} *</label>
                        <input id="first-name" type="text" required>
                        <input id="middle-name" type="hidden">
                        <input id="last-name" type="hidden">
                    </div>

                    <!-- CCCD -->
                    <div class="form-group">
                        <label>${__("Citizen ID number")} *</label>
                        <input id="uid" type="text" inputmode="numeric" required>
                    </div>
                    <input id="sex" type="hidden">

                    <!-- MOBILE -->

                    <div class="form-group">

                        <label>
                            ${__("Phone number")}
                        </label>

                        <input
                            id="mobile"
                            type="text"
                        >

                    </div>


                    <!-- EMAIL -->

                    <div class="form-group">

                        <label>
                            ${__("Email")}
                        </label>

                        <input
                            id="email"
                            type="email"
                        >

                    </div>


                    <!-- ĐỊA CHỈ -->

                    <div class="form-group full">

                        <label>
                            ${__("Address")}
                        </label>

                        <input
                            id="cccd-address"
                            type="text"
                        >

                    </div>


                    <!-- KHUÔN MẶT -->

                    <div class="form-group full">

                        <label>
                            ${__("Face")}
                        </label>

                        <div class="pr-face-field">
                            <div class="pr-face-thumb">
                                <img id="pr-face-img" alt="${__("Face image")}" style="display:none">
                                <span class="pr-face-placeholder" id="pr-face-placeholder">${__("No image")}</span>
                            </div>
                            <div class="pr-face-meta">
                                <p id="pr-face-caption">${__("Look at the camera and take one clear, front-facing photo. The image will be sent to Face ID when the patient is saved.")}</p>
                                <button type="button" id="register-face">
                                    ${__("Register face")}
                                </button>
                            </div>
                        </div>

                        <div id="face-enroll"></div>

                    </div>


                </div>
                <details class="detail">

                    <summary>
                        ${__("Additional medical information")}
                    </summary>

                    <div class="detail-content">

                        <div class="form-group">

                            <label for="blood-group">
                                ${__("Blood group")}
                            </label>

                            <select id="blood-group">
                                <option value="">
                                    ${__("Select blood group")}
                                </option>

                                <option value="A Positive">A+</option>
                                <option value="A Negative">A-</option>
                                <option value="B Positive">B+</option>
                                <option value="B Negative">B-</option>
                                <option value="AB Positive">AB+</option>
                                <option value="AB Negative">AB-</option>
                                <option value="O Positive">O+</option>
                                <option value="O Negative">O-</option>
                            </select>

                        </div>

                        <div class="form-group">

                            <label for="allergies">
                                ${__("Allergies")}
                            </label>

                            <input
                                id="allergies"
                                type="text"
                                placeholder="${__("Enter allergy information")}"
                            >

                        </div>
                        <div class="form-group">
                            <label for="surgical_history">
                                ${__("Surgical history")}
                            </label>

                            <input
                                id="surgical_history"
                                type="text"
                                placeholder="${__("Enter surgical history")}"
                            >
                        </div>
                                    <div class="form-group">
                            <label for="medical_history">
                                ${__("Medication history")}
                            </label>

                            <input
                                id="medical_history"
                                type="text"
                                placeholder="${__("Enter medication history")}"
                            >
                        </div>
                        
                    </div>

                </details>

                <!-- ACTIONS -->

                <div class="actions">

                    <button
                        id="create-patient"
                    >

                        ${__("Create patient profile")}

                    </button>


                </div>

            <!-- ======================================== -->
            <!-- CCCD SCANNER -->
            <!-- ======================================== -->

                <div
                    id="cccd-scanner"
                    style="
                        display: none;
                        margin-top: 20px;
                        padding: 20px;
                        background: #0c2245;
                        border-radius: 16px;
                    "
                >

                    <!-- Tiêu đề -->
                    <h3
                        style="
                            color: white;
                            margin: 0 0 15px 0;
                        "
                    >
                        Quét mã QR CCCD
                    </h3>


                    <!-- Khung camera -->
                    <div
                        style="
                            position: relative;
                            width: 100%;
                            max-width: 500px;
                            margin: auto;
                            overflow: hidden;
                            border-radius: 18px;
                            background: #0c2245;
                            aspect-ratio: 3 / 4;
                        "
                    >

                        <!-- Camera -->
                        <video
                            id="cccd-video"
                            autoplay
                            playsinline
                            muted
                            style="
                                width: 100%;
                                height: 100%;
                                display: block;
                                object-fit: cover;
                            "
                        ></video>


                        <!-- Khung quét QR -->
                        <div
                            id="cccd-scan-frame"
                            style="
                                position: absolute;
                                inset: 12% 10%;
                                border: 3px solid rgba(101, 199, 255, 0.9);
                                border-radius: 18px;
                                box-shadow:
                                    0 0 0 999px
                                    rgba(9, 20, 40, 0.28);
                                pointer-events: none;
                            "
                        ></div>


                        <!-- Vạch quét -->
                        <div
                            id="cccd-scan-line"
                            style="
                                position: absolute;
                                left: 12%;
                                right: 12%;
                                top: 16%;
                                height: 8px;
                                border-radius: 999px;
                                background:
                                    linear-gradient(
                                        180deg,
                                        rgba(101, 199, 255, 0) 0%,
                                        rgba(101, 199, 255, 0.95) 50%,
                                        rgba(101, 199, 255, 0) 100%
                                    );
                                box-shadow:
                                    0 0 20px
                                    rgba(101, 199, 255, 0.7);
                                animation:
                                    cccdScanAnimation
                                    1.6s
                                    ease-in-out
                                    infinite;
                                pointer-events: none;
                            "
                        ></div>

                    </div>


                    <!-- Nút đóng -->
                    <div
                        style="
                            margin-top: 15px;
                            text-align: center;
                        "
                    >

                        <button
                            id="close-cccd-scanner"
                            type="button"
                        >
                            Đóng máy quét
                        </button>

                    </div>

                </div>


                <style>

                @keyframes cccdScanAnimation {

                    0%,
                    100% {
                        transform: translateY(0);
                    }

                    50% {
                        transform: translateY(320px);
                    }

                }

                </style>


                <!-- STATUS -->

                <div
                    id="status"
                    style="
                        display: none;
                    "
                ></div>
            </div>
            </div>
            `);
                


    /*
    ========================================
    STATE
    ========================================
    */

    let currentPatient = null;
    let pendingFaceAvatarB64 = null;
    let savedFacePatientId = null;


    /*
    ========================================
    HELPER
    ========================================
    */

    function getValue(id) {

        const element =
            document.getElementById(id);

        if (!element) {

            console.error(
                "Không tìm thấy element:",
                id
            );

            return "";

        }

        return (
            element.value || ""
        ).trim();

    }


    function setValue(
        id,
        value
    ) {

        const element =
            document.getElementById(id);

        if (!element) {

            console.error(
                "Không tìm thấy element:",
                id
            );

            return;

        }

        element.value =
            value || "";

    }


    function setStatus(
        message,
        type = ""
    ) {

        const status =
            document.getElementById(
                "status"
            );

        status.textContent =
            message;

        status.className =
            type;

    }


    /*
    ========================================
    SPLIT FULL NAME
    ========================================
    */

    function splitFullName(
        fullName
    ) {

        const parts =
            String(
                fullName || ""
            )
            .trim()
            .split(/\s+/)
            .filter(Boolean);


        if (
            parts.length === 0
        ) {

            return {

                firstName: "",

                middleName: "",

                lastName: ""

            };

        }


        if (
            parts.length === 1
        ) {

            return {

                firstName:
                    parts[0],

                middleName:
                    "",

                lastName:
                    ""

            };

        }


        if (
            parts.length === 2
        ) {

            return {

                firstName:
                    parts[0],

                middleName:
                    "",

                lastName:
                    parts[1]

            };

        }


        return {

            firstName:
                parts[0],

            middleName:
                parts
                    .slice(
                        1,
                        -1
                    )
                    .join(" "),

            lastName:
                parts[
                    parts.length - 1
                ]

        };

    }


    /*
    ========================================
    FILL FROM CCCD
    ========================================
    */

    function fillPatientFromCCCD(
        data
    ) {

        console.log(
            "CCCD DATA:",
            data
        );


        setValue(
            "uid",
            data.nationalId
        );


        const name =
            splitFullName(
                data.fullName
            );


        setValue(
            "first-name",
            name.firstName
        );


        setValue(
            "middle-name",
            name.middleName
        );


        setValue(
            "last-name",
            name.lastName
        );


        /*
        Ngày sinh

        CCCD demo trả về:

        DD/MM/YYYY

        input date cần:

        YYYY-MM-DD
        */

        if (
            data.birthDate
        ) {

            const parts =
                data.birthDate
                    .split("/");


            if (
                parts.length === 3
            ) {

                const dateValue =

                    parts[2] +
                    "-" +
                    parts[1] +
                    "-" +
                    parts[0];


                setValue(
                    "dob",
                    dateValue
                );

            }

        }


        /*
        Giới tính

        Demo CCCD của bạn
        hiện trả trực tiếp
        chuỗi giới tính.

        Sau này có thể
        mapping chính xác hơn.
        */

        if (
            data.gender
        ) {

            const gender =
                data.gender
                    .toLowerCase();


            if (
                gender.includes(
                    "nam"
                )
            ) {

                setValue(
                    "sex",
                    "Male"
                );

            }


            else if (
                gender.includes(
                    "nữ"
                ) ||
                gender.includes(
                    "nu"
                )
            ) {

                setValue(
                    "sex",
                    "Female"
                );

            }

        }


        /*
        Địa chỉ
        */

        setValue(
            "cccd-address",
            data.address
        );


        setStatus(

            __("CCCD scanned and information filled automatically."),

            "success"

        );

    }


    /*
    ========================================
    SCAN CCCD
    ========================================
    */

    let cccdStream = null;
    let cccdScanInterval = null;
    let isCCCDScanning = false;


    /*
    ========================================
    BẤM NÚT QUÉT CCCD
    ========================================
    */

    const scanCCCDButton =
        document.getElementById("scan-cccd");

    if (scanCCCDButton) {

        scanCCCDButton.addEventListener(
            "click",
            function () {

                openCCCDScanner();

            }
        );

    }


    /*
    ========================================
    MỞ CAMERA
    ========================================
    */

    async function openCCCDScanner() {

        closeFaceEnroll();

        const scanner =
            document.getElementById(
                "cccd-scanner"
            );

        const video =
            document.getElementById(
                "cccd-video"
            );


        if (!scanner || !video) {

            console.error(
                "Không tìm thấy cccd-scanner hoặc cccd-video."
            );

            return;

        }


        if (cccdStream) {

            return;

        }


        /*
        Hiện khung camera
        */

        scanner.style.display =
            "block";


        setStatus(
            __("Opening camera to scan CCCD..."),
            ""
        );


        try {

            /*
            Kiểm tra trình duyệt
            */

            if (
                !navigator.mediaDevices ||
                !navigator.mediaDevices.getUserMedia
            ) {

                throw new Error(
                    "Trình duyệt không hỗ trợ camera."
                );

            }


 

            cccdStream =
                await navigator.mediaDevices
                    .getUserMedia({

                        video: {

                            facingMode: {
                                ideal: "environment"
                            },

                            width: {
                                ideal: 1280
                            },

                            height: {
                                ideal: 720
                            }

                        },

                        audio: false

                    });


            /*
            Gắn camera vào video
            */

            video.srcObject =
                cccdStream;


            await video.play();


            /*
            Camera đã mở thành công
            */

            isCCCDScanning =
                true;


            setStatus(
                __("Place the CCCD QR code in the center of the camera..."),
                ""
            );


            /*
            Bắt đầu scan QR
            */

            startCCCDQRScan();

        }

        catch (error) {

            console.error(
                "CCCD camera error:",
                error
            );


            /*
            Nếu camera lỗi
            thì đóng camera
            */

            closeCCCDScanner();


            setStatus(
                __("Unable to open the CCCD camera. Check the browser camera permission."),
                "error"
            );

        }

    }


    /*
    ========================================
    BẮT ĐẦU SCAN QR
    ========================================
    */

    function startCCCDQRScan() {


        /*
        Nếu đang scan
        thì không tạo interval mới
        */

        if (
            cccdScanInterval
        ) {

            return;

        }


        const video =
            document.getElementById(
                "cccd-video"
            );


        if (!video) {

            return;

        }


        /*
        Tạo canvas ẩn
        */

        const canvas =
            document.createElement(
                "canvas"
            );


        const context =
            canvas.getContext(
                "2d",
                {
                    willReadFrequently: true
                }
            );


        if (!context) {

            console.error(
                "Không thể tạo canvas context."
            );

            return;

        }


        /*
        Scan mỗi 300ms
        */

        cccdScanInterval =
            setInterval(

                function () {


                    /*
                    Camera chưa sẵn sàng
                    */

                    if (

                        !isCCCDScanning ||

                        !video.videoWidth ||

                        !video.videoHeight

                    ) {

                        return;

                    }


                    /*
                    Đặt kích thước canvas
                    */

                    canvas.width =
                        video.videoWidth;

                    canvas.height =
                        video.videoHeight;


                    /*
                    Chụp frame camera
                    */

                    context.drawImage(

                        video,

                        0,

                        0,

                        canvas.width,

                        canvas.height

                    );


                    /*
                    Lấy dữ liệu hình ảnh
                    */

                    const imageData =
                        context.getImageData(

                            0,

                            0,

                            canvas.width,

                            canvas.height

                        );


                    /*
                    Đọc QR bằng jsQR
                    */

                    if (
                        typeof jsQR !==
                        "function"
                    ) {

                        console.error(
                            "jsQR chưa được load."
                        );

                        return;

                    }


                    const qrCode =
                        jsQR(

                            imageData.data,

                            imageData.width,

                            imageData.height,

                            {
                                inversionAttempts:
                                    "attemptBoth"
                            }

                        );


                    /*
                    Nếu tìm thấy QR
                    */

                    if (

                        qrCode &&

                        qrCode.data

                    ) {

                        console.log(
                            "QR CCCD:",
                            qrCode.data
                        );


                        handleCCCDResult(
                            qrCode.data
                        );

                    }

                },

                300

            );

    }


    /*
    ========================================
    XỬ LÝ KẾT QUẢ QR
    ========================================
    */

    function handleCCCDResult(
        rawData
    ) {


        /*
        Tránh xử lý nhiều lần
        */

        if (
            !isCCCDScanning
        ) {

            return;

        }


        /*
        Dừng scan ngay lập tức
        */

        isCCCDScanning =
            false;


        if (
            cccdScanInterval
        ) {

            clearInterval(
                cccdScanInterval
            );

            cccdScanInterval =
                null;

        }


        console.log(
            "Raw CCCD QR:",
            rawData
        );


        /*
        Parse dữ liệu
        */

        const data =
            parseCCCDQR(
                rawData
            );


        /*
        QR không đúng format
        */

        if (
            !data
        ) {

            setStatus(

                __("QR was read, but the data is not in the correct CCCD format."),

                "error"

            );


            /*
            Cho phép scan lại
            */

            setTimeout(

                function () {

                    if (
                        cccdStream
                    ) {

                        isCCCDScanning =
                            true;

                        startCCCDQRScan();

                    }

                },

                1000

            );


            return;

        }


        /*
        Điền dữ liệu vào form
        */

        fillPatientFromCCCD(
            data
        );


        /*
        Đóng camera
        */

        closeCCCDScanner();


        /*
        Thông báo thành công
        */

        setStatus(

            __("CCCD scanned and information filled automatically."),

            "success"

        );

    }


    /*
    ========================================
    PARSE QR CCCD
    ========================================
    */

    function parseCCCDQR(
        payload
    ) {


        const parts =

            String(
                payload || ""
            )

            .split("|")

            .map(

                function (part) {

                    return part.trim();

                }

            );


        /*
        Format:

        0: CCCD
        1: CMND
        2: Họ tên
        3: Ngày sinh
        4: Giới tính
        5: Địa chỉ
        */

        if (
            parts.length < 4
        ) {

            return null;

        }


        const nationalId =
            parts[0];


        const fullName =
            parts[2] || "";


        const rawBirthDate =
            parts[3] || "";


        const gender =
            parts[4] || "";


        const address =
            parts[5] || "";


        /*
        CCCD phải có 9-12 số
        */

        if (

            !/^\d{9,12}$/.test(
                nationalId
            )

        ) {

            return null;

        }


        return {

            nationalId:
                nationalId,

            fullName:
                fullName,

            birthDate:
                formatCCCDDate(
                    rawBirthDate
                ),

            gender:
                gender,

            address:
                address

        };

    }


    /*
    ========================================
    FORMAT NGÀY SINH
    ========================================
    */

    function formatCCCDDate(
        value
    ) {


        const digits =

            String(
                value || ""
            )

            .replace(
                /\D/g,
                ""
            );


        if (
            digits.length !== 8
        ) {

            return "";

        }


        /*
        DDMMYYYY
        ->
        DD/MM/YYYY
        */

        return (

            digits.slice(
                0,
                2
            )

            +

            "/"

            +

            digits.slice(
                2,
                4
            )

            +

            "/"

            +

            digits.slice(
                4
            )

        );

    }


    /*
    ========================================
    NÚT ĐÓNG CAMERA
    ========================================
    */

    const closeCCCDButton =
        document.getElementById(
            "close-cccd-scanner"
        );


    if (closeCCCDButton) {

        closeCCCDButton.addEventListener(

            "click",

            function () {

                closeCCCDScanner();

            }

        );

    }


    /*
    ========================================
    ĐÓNG CAMERA
    ========================================
    */

    function closeCCCDScanner() {


        /*
        Dừng scan
        */

        isCCCDScanning =
            false;


        if (
            cccdScanInterval
        ) {

            clearInterval(
                cccdScanInterval
            );

            cccdScanInterval =
                null;

        }


        /*
        Tắt camera
        */

        if (
            cccdStream
        ) {

            cccdStream
                .getTracks()
                .forEach(

                    function (track) {

                        track.stop();

                    }

                );

            cccdStream =
                null;

        }


        /*
        Xóa video
        */

        const video =
            document.getElementById(
                "cccd-video"
            );


        if (video) {

            video.pause();

            video.srcObject =
                null;

        }


        /*
        Ẩn khung camera
        */

        const scanner =
            document.getElementById(
                "cccd-scanner"
            );


        if (scanner) {

            scanner.style.display =
                "none";

        }

    }
    /*
    ========================================
    REGISTER FACE (inline on this form)
    ========================================
    */

    function patientDisplayName() {
        const fromForm = [
            getValue("first-name"),
            getValue("middle-name"),
            getValue("last-name"),
        ].filter(Boolean).join(" ");
        return fromForm
            || (currentPatient && currentPatient.patient_name)
            || "";
    }

    function setFaceCaption(text) {
        const el = document.getElementById("pr-face-caption");
        if (el) {
            el.textContent = text;
        }
    }

    function showFaceThumb(dataUrl) {
        pendingFaceAvatarB64 = dataUrl;
        savedFacePatientId = null;
        const img = document.getElementById("pr-face-img");
        const placeholder = document.getElementById("pr-face-placeholder");
        if (img) {
            img.src = dataUrl;
            img.style.display = "block";
        }
        if (placeholder) {
            placeholder.style.display = "none";
        }
        const btn = document.getElementById("register-face");
        if (btn) {
            btn.textContent = __("Scan face again");
        }
        try {
            sessionStorage.setItem(
                "pending_face_avatar",
                JSON.stringify({
                    image_b64: dataUrl,
                    display_name: patientDisplayName(),
                    uid: getValue("uid") || (currentPatient && currentPatient.uid) || "",
                })
            );
        } catch (e) {
            /* ignore quota */
        }
    }

    function restorePendingFaceThumb() {
        try {
            const raw = sessionStorage.getItem("pending_face_avatar");
            if (!raw) {
                return;
            }
            const saved = JSON.parse(raw);
            if (saved && saved.image_b64) {
                showFaceThumb(saved.image_b64);
                setFaceCaption(__("A face image is ready. Create the profile to attach it to the patient, or scan again."));
            }
        } catch (e) {
            /* ignore */
        }
    }

    function closeFaceEnroll() {
        if (window.ClinicFaceEnroll && window.ClinicFaceEnroll.close) {
            window.ClinicFaceEnroll.close();
        }
    }

    function resetPatientRegistrationForm() {
        [
            "uid",
            "first-name",
            "middle-name",
            "last-name",
            "dob",
            "mobile",
            "email",
            "cccd-address",
            "allergies",
            "surgical_history",
            "medical_history",
        ].forEach(function (id) {
            const field = document.getElementById(id);
            if (field) {
                field.value = "";
                field.dispatchEvent(new Event("input", { bubbles: true }));
            }
        });

        ["sex", "blood-group"].forEach(function (id) {
            const field = document.getElementById(id);
            if (field) {
                field.selectedIndex = 0;
                field.dispatchEvent(new Event("change", { bubbles: true }));
            }
        });

        currentPatient = null;
        pendingFaceAvatarB64 = null;
        savedFacePatientId = null;
        try {
            sessionStorage.removeItem("pending_face_avatar");
        } catch (e) {
            /* ignore storage errors */
        }

        closeFaceEnroll();
        closeCCCDScanner();

        const faceImg = document.getElementById("pr-face-img");
        const facePlaceholder = document.getElementById("pr-face-placeholder");
        if (faceImg) {
            faceImg.removeAttribute("src");
            faceImg.style.display = "none";
        }
        if (facePlaceholder) {
            facePlaceholder.style.display = "inline";
        }
        const faceButton = document.getElementById("register-face");
        if (faceButton) {
            faceButton.textContent = __("Register face");
        }
        setFaceCaption(__("Look at the camera and take one clear, front-facing photo. The image will be sent to Face ID when the patient is saved."));

        const createButton = document.getElementById("create-patient");
        if (createButton) {
            createButton.disabled = false;
        }
    }

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

    async function saveFaceToPatient(patientId) {
        if (!pendingFaceAvatarB64 || !patientId) {
            return null;
        }
        const displayName = patientDisplayName() || patientId;
        setStatus(__("Saving the face image to the patient profile…"), "");
        const res = await frappe.call({
            method: "smart_hospital.api.face_identity.register_patient_face_avatar",
            args: {
                patient: patientId,
                image_b64: pendingFaceAvatarB64,
                display_name: displayName,
                push_today: 1,
            },
            freeze: true,
        });
        const msg = (res && res.message) || {};
        if (!msg.success) {
            throw new Error(msg.error || "Không lưu được ảnh khuôn mặt.");
        }
        try {
            sessionStorage.removeItem("pending_face_avatar");
        } catch (e) {
            /* ignore */
        }
        pendingFaceAvatarB64 = null;
        savedFacePatientId = patientId;
        const enrollId = (msg.patient && msg.patient.aiface_enroll_id) || "?";
        const station = msg.station_push;
        const stationNote = station && station.success
            ? " Ảnh đã được gửi tới thiết bị Face ID."
            : " Ảnh đã lưu vào hồ sơ và Face VectorDB.";
        setFaceCaption("Đã gắn ảnh khuôn mặt vào hồ sơ. Face ID #" + enrollId + "." + stationNote);
        return enrollId;
    }

    async function attachPendingFaceIfNeeded() {
        if (!pendingFaceAvatarB64 || !currentPatient || !currentPatient.patient) {
            return "";
        }
        try {
            const enrollId = await saveFaceToPatient(currentPatient.patient);
            return enrollId ? ("\nKhuôn mặt: Face ID #" + enrollId) : "";
        } catch (error) {
            console.error("FACE ATTACH ERROR:", error);
            throw new Error("Hồ sơ đã tạo nhưng chưa gắn được khuôn mặt: " + formatFrappeError(error));
        }
    }

    async function onFaceCaptured(dataUrl) {
        showFaceThumb(dataUrl);
        if (currentPatient && currentPatient.patient) {
            setStatus(__("Saving the face to the patient profile..."), "");
            try {
                const enrollId = await saveFaceToPatient(currentPatient.patient);
                setStatus(__("Face saved to the patient profile. Face ID #") + enrollId, "success");
            } catch (error) {
                setFaceCaption(__("The photo was taken, but saving to the patient profile or Face ID failed."));
                setStatus(__("Unable to save the face:") + " " + formatFrappeError(error), "error");
                throw error;
            }
            return;
        }
        setFaceCaption(__("Photo ready. Create the patient profile to save the image and send it to Face ID."));
        setStatus(__("Photo captured. Save the patient profile to send the image to Face ID."), "success");
    }

    function openFaceEnroll() {
        if (typeof closeCCCDScanner === "function") {
            closeCCCDScanner();
        }
        if (!window.ClinicFaceEnroll || !window.ClinicFaceEnroll.open) {
            setStatus(__("Face Service could not be loaded. Reload the page."), "error");
            return;
        }
        window.ClinicFaceEnroll.open();
    }

    const faceMount = document.getElementById("face-enroll");
    if (window.ClinicFaceEnroll && faceMount) {
        window.ClinicFaceEnroll.mount(faceMount, {
            onCaptured: onFaceCaptured,
            onStatus: setStatus,
        });
    }

    restorePendingFaceThumb();

    document.getElementById("register-face").addEventListener("click", function () {
        openFaceEnroll();
    });
    document.getElementById("uid").addEventListener("input", function () {
        if (currentPatient && getValue("uid") !== currentPatient.uid) {
            currentPatient = null;
            savedFacePatientId = null;
        }
    });


    /*
    ========================================
    CREATE PATIENT
    ========================================
    */

    document
        .getElementById(
            "create-patient"
        )
        .addEventListener(
            "click",
            async function () {


                /*
                ========================================
                READ FORM
                ========================================
                */

                const firstName =
                    getValue(
                        "first-name"
                    );


                const middleName =
                    getValue(
                        "middle-name"
                    );


                const lastName =
                    getValue(
                        "last-name"
                    );


                const sex =
                    getValue(
                        "sex"
                    );


                const uid =
                    getValue(
                        "uid"
                    );


                const dob =
                    getValue(
                        "dob"
                    );


                const mobile =
                    getValue(
                        "mobile"
                    );


                const email =
                    getValue(
                        "email"
                    );


                const cccdAddress =
                    getValue(
                        "cccd-address"
                    );
                const blood_group =
                    getValue("blood-group");

                const allergies =
                    getValue("allergies");

                const surgical_history =
                    getValue("surgical_history");

                const medical_history =
                    getValue("medical_history");
                

                /*
                ========================================
                VALIDATION
                ========================================
                */

                if (
                    !firstName
                ) {

                    setStatus(

                        __("Please enter the first name."),

                        "warning"

                    );

                    return;

                }


                if (
                    !uid
                ) {

                    setStatus(

                        __("Please enter the citizen ID number."),

                        "warning"

                    );

                    return;

                }


                /*
                ========================================
                DISABLE BUTTON
                ========================================
                */

                const createButton =
                    document.getElementById(
                        "create-patient"
                    );


                createButton.disabled =
                    true;


                setStatus(

                    __("Creating patient profile..."),

                    ""

                );


                /*
                ========================================
                CALL BACKEND
                ========================================
                */

                try {
                    const response = await frappe.call({

                        method:
                            "smart_hospital.api.createpatient.create_patient",

                        args: {

                            first_name:
                                firstName,

                            middle_name:
                                middleName,

                            last_name:
                                lastName,

                            sex:
                                sex,

                            dob:
                                dob,

                            uid:
                                uid,

                            national_id:
                                uid,

                            mobile:
                                mobile,

                            email:
                                email,

                            cccd_address:
                                cccdAddress,

                            blood_group:
                                blood_group,

                            allergies:
                                allergies,

                            surgical_history:
                                surgical_history,

                            medical_history:
                                medical_history

                        }
                        


                    });


                    console.log(
                        "CREATE PATIENT RESPONSE:",
                        response
                    );


                    const result =
                        response.message;


                    /*
                    ========================================
                    API KHÔNG TRẢ RESULT
                    ========================================
                    */

                    if (
                        !result
                    ) {

                        setStatus(

                            __("The API returned no data."),

                            "error"

                        );

                        return;

                    }


                    /*
                    ========================================
                    CCCD ĐÃ TỒN TẠI
                    ========================================
                    */

                    if (
                        !result.success
                    ) {


                        setStatus(

                            result.message ||

                            __("Unable to create patient."),

                            "warning"

                        );


                        /*
                        Nếu backend trả
                        Patient đã tồn tại
                        */

                        if (
                            result.patient
                        ) {

                            currentPatient = {

                                patient:
                                    result.patient,

                                patient_name:
                                    "",

                                uid:
                                    uid

                            };

                            await attachPendingFaceIfNeeded();

                        }


                        return;

                    }


                    /*
                    ========================================
                    CREATE SUCCESS
                    ========================================
                    */

                    currentPatient = {

                        patient:
                            result.patient,

                        patient_name:
                            result.patient_name,

                        uid:
                            result.uid || uid

                    };

                    const faceNote = await attachPendingFaceIfNeeded();
                    const faceReady = faceNote.startsWith("\nKhuôn mặt: Face ID #") || savedFacePatientId === result.patient;
                    const faceWarning = faceNote || (faceReady
                        ? "\n" + __("Face: saved to the profile.")
                        : "\n" + __("No face image yet. Scan the face and wait for the saved confirmation before using Face ID."));


                    /*
                    Hiện kết quả
                    */

                    setStatus(

                        __("Patient profile created successfully!") + "\n" +

                        "Patient ID: " +
                        result.patient +

                        "\n" + __("Patient name") + ": " +
                        result.patient_name +

                        "\n" + __("Citizen ID") + ": " +
                        (
                            result.uid ||
                            uid
                        ) +
                        faceWarning,

                        faceReady ? "success" : "warning"

                    );

                    frappe.show_alert({
                        message: "Đã tạo hồ sơ bệnh nhân. Biểu mẫu đã được làm mới.",
                        indicator: "green",
                    });
                    window.setTimeout(resetPatientRegistrationForm, 1200);


                }

                catch (
                    error
                ) {


                    console.error(

                        "CREATE PATIENT ERROR:",

                        error

                    );


                    /*
                    ========================================
                    LẤY LỖI Frappe
                    ========================================
                    */

                    let errorMessage =

                        "Lỗi khi tạo bệnh nhân.";


                    if (
                        error &&
                        error.message
                    ) {

                        errorMessage +=

                            "\n" +
                            error.message;

                    }


                    if (
                        error &&
                        error.responseJSON
                    ) {

                        const responseJSON =
                            error.responseJSON;


                        if (
                            responseJSON.exception
                        ) {

                            errorMessage +=

                                "\n" +
                                responseJSON.exception;

                        }

                    }


                    setStatus(

                        errorMessage,

                        "error"

                    );

                }


                finally {


                    createButton.disabled =
                        false;

                }

            }
        );
}
