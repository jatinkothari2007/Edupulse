/**
 * EduPulse WebRTC — Firestore-signaled peer-to-peer video call.
 */
const RTC_SERVERS = {
    iceServers: [
        { urls: ['stun:stun1.l.google.com:19302', 'stun:stun2.l.google.com:19302'] }
    ]
};

let _pc          = null;
let _localStream = null;
let _callStart   = null;
let _durationInterval = null;

async function startCall(sessionId, role) {
    const callDoc = window.db.collection('calls').doc(sessionId);
    _pc = new RTCPeerConnection(RTC_SERVERS);

    // Local media
    _localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
    _localStream.getTracks().forEach(track => _pc.addTrack(track, _localStream));

    const localVid = document.getElementById('local-video');
    if (localVid) { localVid.srcObject = _localStream; localVid.muted = true; }

    // Remote stream
    const remoteStream = new MediaStream();
    _pc.ontrack = e => {
        e.streams[0].getTracks().forEach(t => remoteStream.addTrack(t));
        const remoteVid = document.getElementById('remote-video');
        if (remoteVid) remoteVid.srcObject = remoteStream;
    };

    // Connection state
    _pc.onconnectionstatechange = () => {
        const status = document.getElementById('call-status');
        if (status) status.textContent = _pc.connectionState;
    };

    if (role === 'counsellor') {
        // Create offer
        const offer = await _pc.createOffer();
        await _pc.setLocalDescription(offer);
        await callDoc.set({ offer: { type: offer.type, sdp: offer.sdp } });

        // Listen for answer
        callDoc.onSnapshot(snap => {
            const data = snap.data();
            if (data?.answer && !_pc.currentRemoteDescription) {
                _pc.setRemoteDescription(new RTCSessionDescription(data.answer));
            }
        });

        // ICE
        _pc.onicecandidate = e => {
            if (e.candidate) callDoc.collection('offerCandidates').add(e.candidate.toJSON());
        };
        callDoc.collection('answerCandidates').onSnapshot(snap => {
            snap.docChanges().forEach(async change => {
                if (change.type === 'added') {
                    await _pc.addIceCandidate(new RTCIceCandidate(change.doc.data()));
                }
            });
        });

    } else {
        // Student: listen for offer first
        callDoc.onSnapshot(async snap => {
            const data = snap.data();
            if (data?.offer && !_pc.currentRemoteDescription) {
                await _pc.setRemoteDescription(new RTCSessionDescription(data.offer));
                const answer = await _pc.createAnswer();
                await _pc.setLocalDescription(answer);
                await callDoc.update({ answer: { type: answer.type, sdp: answer.sdp } });
            }
        });

        _pc.onicecandidate = e => {
            if (e.candidate) callDoc.collection('answerCandidates').add(e.candidate.toJSON());
        };
        callDoc.collection('offerCandidates').onSnapshot(snap => {
            snap.docChanges().forEach(async change => {
                if (change.type === 'added') {
                    await _pc.addIceCandidate(new RTCIceCandidate(change.doc.data()));
                }
            });
        });
    }

    // Duration timer
    _callStart = Date.now();
    _durationInterval = setInterval(() => {
        const sec = Math.floor((Date.now() - _callStart) / 1000);
        const mm  = String(Math.floor(sec / 60)).padStart(2, '0');
        const ss  = String(sec % 60).padStart(2, '0');
        const el = document.getElementById('call-duration');
        if (el) el.textContent = `${mm}:${ss}`;
    }, 1000);

    return _pc;
}

async function endCall(sessionId) {
    clearInterval(_durationInterval);
    const duration = _callStart ? Math.floor((Date.now() - _callStart) / 1000) : 0;
    if (_pc) { _pc.close(); _pc = null; }
    if (_localStream) { _localStream.getTracks().forEach(t => t.stop()); _localStream = null; }
    try {
        await apiCall(`/api/videocall/session/${sessionId}/complete`, 'PUT', { duration });
    } catch(_) {}
    return duration;
}

function toggleMute() {
    if (!_localStream) return;
    const track = _localStream.getAudioTracks()[0];
    if (track) {
        track.enabled = !track.enabled;
        const btn = document.getElementById('mute-btn');
        if (btn) btn.innerHTML = track.enabled
            ? '<i class="fas fa-microphone"></i>'
            : '<i class="fas fa-microphone-slash"></i>';
    }
}

function toggleCamera() {
    if (!_localStream) return;
    const track = _localStream.getVideoTracks()[0];
    if (track) {
        track.enabled = !track.enabled;
        const btn = document.getElementById('camera-btn');
        if (btn) btn.innerHTML = track.enabled
            ? '<i class="fas fa-video"></i>'
            : '<i class="fas fa-video-slash"></i>';
    }
}
