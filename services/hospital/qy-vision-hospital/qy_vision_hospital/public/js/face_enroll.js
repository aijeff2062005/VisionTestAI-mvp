(function () {
	"use strict";

	const HTML = `
<div class="pr-face-enroll">
	<div class="pr-face-camera-wrap">
		<video id="cfe-camera" autoplay muted playsinline></video>
		<div class="pr-face-guide"></div>
	</div>
	<p class="cfe-instruction">Nhìn thẳng vào camera, đảm bảo đủ sáng rồi chụp một ảnh chính diện.</p>
	<p class="cfe-status" id="cfe-status">Đang mở camera…</p>
	<div class="cfe-preview" id="cfe-preview">
		<img id="cfe-preview-img" alt="Ảnh khuôn mặt đã chụp">
	</div>
	<div class="cfe-actions">
		<button type="button" id="cfe-capture" disabled>Chụp ảnh</button>
		<button type="button" id="cfe-retake" hidden>Chụp lại</button>
		<button type="button" id="cfe-confirm" hidden>Xác nhận lưu</button>
		<button type="button" id="cfe-close">Hủy</button>
	</div>
</div>`;

	const CSS = `
.pr-face-enroll { color: #183b45; }
.pr-face-camera-wrap { position:relative; width:100%; max-width:850px; aspect-ratio:16/9; margin:16px auto; overflow:hidden; border-radius:12px; background:#111; }
.pr-face-camera-wrap video { width:100%; height:100%; object-fit:cover; transform:scaleX(-1); }
.pr-face-guide { position:absolute; inset:7% 32%; border:2px solid #08b89c; border-radius:50%; pointer-events:none; }
.cfe-instruction { font-size:16px; margin:0 0 10px; }
.cfe-status { min-height:22px; color:#718795; }
.cfe-preview { display:none; text-align:center; margin:12px 0; }
.cfe-preview.is-visible { display:block; }
.cfe-preview img { width:220px; max-height:260px; object-fit:cover; border-radius:10px; }
.cfe-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:16px; }
.cfe-actions button { border:1px solid #d5e1e5; border-radius:10px; padding:11px 18px; font-weight:600; cursor:pointer; background:white; color:#183b45; }
.cfe-actions #cfe-capture, .cfe-actions #cfe-confirm { background:#0a948a; border-color:#0a948a; color:white; }
.cfe-actions button:disabled { opacity:.55; cursor:wait; }
`;

	let opts = {};
	let stream = null;
	let pendingJpeg = null;

	function $(id) { return document.getElementById(id); }
	function status(message, type) {
		const el = $("cfe-status");
		if (el) el.textContent = message;
		if (opts.onStatus) opts.onStatus(message, type || "");
	}
	function stopCamera() {
		if (stream) {
			stream.getTracks().forEach(function (track) { track.stop(); });
			stream = null;
		}
		const video = $("cfe-camera");
		if (video) video.srcObject = null;
	}
	function close() {
		stopCamera();
		const panel = $("face-enroll");
		if (panel) panel.classList.remove("is-open");
	}
	function showCapturedImage(dataUrl) {
		pendingJpeg = dataUrl;
		$("cfe-preview-img").src = dataUrl;
		$("cfe-preview").classList.add("is-visible");
		$("cfe-capture").hidden = true;
		$("cfe-retake").hidden = false;
		$("cfe-confirm").hidden = false;
		status("Đã chụp ảnh. Xác nhận để lưu hồ sơ và gửi tới Face ID.", "success");
	}
	function capture() {
		const video = $("cfe-camera");
		if (!video || !video.videoWidth || !video.videoHeight) {
			status("Camera chưa sẵn sàng. Vui lòng thử lại.", "error");
			return;
		}
		const canvas = document.createElement("canvas");
		canvas.width = video.videoWidth;
		canvas.height = video.videoHeight;
		canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
		let quality = 0.82;
		let dataUrl = canvas.toDataURL("image/jpeg", quality);
		while (dataUrl.length > 480000 && quality > 0.4) {
			quality -= 0.08;
			dataUrl = canvas.toDataURL("image/jpeg", quality);
		}
		showCapturedImage(dataUrl);
	}
	async function open() {
		const panel = $("face-enroll");
		if (!panel) return;
		panel.classList.add("is-open");
		try {
			stream = await navigator.mediaDevices.getUserMedia({
				video: { facingMode: { ideal: "user" }, width: { ideal: 1280 }, height: { ideal: 720 } },
				audio: false,
			});
			const video = $("cfe-camera");
			video.srcObject = stream;
			await video.play();
			$("cfe-capture").disabled = false;
			status("Nhìn thẳng vào camera, đảm bảo đủ sáng rồi chụp một ảnh chính diện.");
		} catch (error) {
			close();
			status("Không mở được camera. Hãy kiểm tra quyền camera của trình duyệt. " + (error.message || ""), "error");
		}
	}
	function mount(container, options) {
		opts = options || {};
		if (!container) return;
		if (!document.getElementById("clinic-face-enroll-css")) {
			const style = document.createElement("style");
			style.id = "clinic-face-enroll-css";
			style.textContent = CSS;
			document.head.appendChild(style);
		}
		container.innerHTML = HTML;
		$("cfe-capture").addEventListener("click", capture);
		$("cfe-retake").addEventListener("click", function () {
			pendingJpeg = null;
			$("cfe-preview").classList.remove("is-visible");
			$("cfe-capture").hidden = false;
			$("cfe-retake").hidden = true;
			$("cfe-confirm").hidden = true;
			status("Nhìn thẳng vào camera rồi chụp lại.");
		});
		$("cfe-confirm").addEventListener("click", async function () {
			if (!pendingJpeg || typeof opts.onCaptured !== "function") return;
			$("cfe-confirm").disabled = true;
			try {
				await opts.onCaptured(pendingJpeg);
				close();
			} catch (error) {
				$("cfe-confirm").disabled = false;
				status("Không lưu được ảnh khuôn mặt: " + (error.message || error), "error");
			}
		});
		$("cfe-close").addEventListener("click", close);
	}

	window.ClinicFaceEnroll = { mount: mount, open: open, close: close };
})();
