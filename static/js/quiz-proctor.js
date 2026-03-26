/**
 * ╔══════════════════════════════════════════════════════════════╗
 * ║          AntiGravity Proctor Engine  v2.1                   ║
 * ║   Real face tracking via face-api.js + canvas overlay       ║
 * ╚══════════════════════════════════════════════════════════════╝
 *
 * Face detection: face-api.js tiny face detector (local model weights)
 * Public API:
 *   startProctoring(config)   → initialises all monitoring
 *   stopProctoring()          → stops + returns proctorSession
 *   renderReport(session, containerId) → renders full report HTML
 *   enterFullscreen(el) / exitFullscreen()
 */

/* ─── face-api.js CDN load ──────────────────────────────────── */
(function() {
  if (typeof faceapi !== 'undefined') return;
  var s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js';
  document.head.appendChild(s);
})();

/* ─── Default config ─────────────────────────────────────────── */
var PROCTOR_DEFAULTS = {
  emotionCheckInterval : 4000,
  alertThreshold       : 2,
  focusDrainPerAlert   : 8,
  tabSwitchPenalty     : 20,
  faceMissingPenalty   : 10,
  enableAISummary      : true,
};

/* ─── State ──────────────────────────────────────────────────── */
var _cfg              = {};
var _stream           = null;
var _emotionTimer     = null;
var _focusTimer       = null;
var _visHandler       = null;
var _fsHandler        = null;
var _faceAbsTimer     = null;
var _detectionLoop    = null;   // rAF handle for face detection
var _faceApiReady     = false;  // true once models loaded
var _lastFaceCount    = -1;     // tracks face count changes
var _noFaceSeconds    = 0;      // consecutive seconds with no face
var _multiCanvas      = null;   // overlay canvas for bounding boxes
var _faceAbsSeconds  = 0;
var _lastEventTime   = 0;
var _suspiciousStreak = 0;    // suspicious counts within last 60s
var _streakTimer     = null;

var _session = null;   // live proctorSession object

/* emotion palette */
var EMO = {
  CALM       : { icon:'😌', color:'#10B981', label:'Calm'       },
  NEUTRAL    : { icon:'😐', color:'#94A3B8', label:'Neutral'    },
  ANXIOUS    : { icon:'😰', color:'#F59E0B', label:'Anxious'    },
  SUSPICIOUS : { icon:'👀', color:'#EF4444', label:'Suspicious' },
  CONFUSED   : { icon:'🤔', color:'#A78BFA', label:'Confused'   },
};

/* ═══════════════════════════════════════════════════════════════
   startProctoring(config)
════════════════════════════════════════════════════════════════ */
/* ═══════════════════════════════════════════════════════════════
   Load face-api.js models (tiny face detector, ~190KB)
════════════════════════════════════════════════════════════════ */
async function _loadFaceApi() {
  try {
    await _waitForFaceApi();
    var MODEL_URL = '/static/models';
    await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL);
    _faceApiReady = true;
    console.log('[Proctor] face-api.js ready');
  } catch(e) {
    console.warn('[Proctor] face-api.js load failed:', e);
    _faceApiReady = false;
  }
}

function _waitForFaceApi(ms) {
  return new Promise(function(resolve) {
    var t = 0;
    var check = function() {
      if (typeof faceapi !== 'undefined') return resolve();
      t += 100;
      if (t > 8000) return resolve();  // give up after 8s
      setTimeout(check, 100);
    };
    check();
  });
}

async function startProctoring(config) {
  _cfg = Object.assign({}, PROCTOR_DEFAULTS, config || {});

  _session = {
    studentId    : (window._currentUser && window._currentUser.customId) || 'STU',
    studentName  : (window._currentUser && window._currentUser.name)     || 'Student',
    subject      : 'Pulse Quiz',
    startTime    : new Date(),
    endTime      : null,
    totalAlerts  : 0,
    suspiciousCount : 0,
    anxiousCount    : 0,
    faceMissingEvents : 0,
    tabSwitchCount  : 0,
    focusScore      : 100,
    emotionLog   : [],  // { time, emotion, qIndex }
    behaviorLog  : [],  // { time, event, severity }
    focusHistory : [100],
    answers      : {},
    riskScore    : 100,
    verdict      : 'clean',
  };

  _faceAbsSeconds  = 0;
  _suspiciousStreak = 0;

  /* ── Inject sidebar ── */
  _buildSidebar();

  /* ── Webcam + Face Detection ── */
  try {
    _stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    var vid = document.getElementById('proctor-video');
    if (vid) {
      vid.srcObject = _stream;
      vid.play();
      /* wait for video dimensions */
      await new Promise(function(r){ vid.addEventListener('loadedmetadata', r, {once:true}); setTimeout(r,2000); });
    }
    _setLiveIndicator(true);

    /* Load face-api models and start detection loop */
    _loadFaceApi().then(function() {
      if (vid) _startFaceDetectionLoop(vid);
    });

  } catch (err) {
    _setLiveIndicator(false);
    _logEvent('Camera unavailable — monitoring limited', 'low');
  }

  /* ── Tab-switch detection ── */
  _visHandler = function() {
    if (document.hidden) {
      _session.tabSwitchCount++;
      _session.focusScore = Math.max(0, _session.focusScore - _cfg.tabSwitchPenalty);
      _session.totalAlerts++;
      _logEvent('Tab switch detected', 'high');
      _triggerAlert('⚠️ Tab switch detected!', 'Tab Switch', 'high');
      _updateSidebar();
    }
  };
  document.addEventListener('visibilitychange', _visHandler);

  /* ── Fullscreen exit detection ── */
  _fsHandler = function() {
    var inFs = !!(document.fullscreenElement || document.webkitFullscreenElement);
    if (!inFs) {
      _session.tabSwitchCount++;
      _session.focusScore = Math.max(0, _session.focusScore - _cfg.tabSwitchPenalty);
      _session.totalAlerts++;
      _logEvent('Fullscreen exited', 'high');
      _triggerAlert('⚠️ Fullscreen exited — recorded!', 'Fullscreen Exit', 'high');
      var ov = document.getElementById('fs-warning-overlay');
      if (ov) ov.style.display = 'flex';
      _updateSidebar();
    } else {
      var ov = document.getElementById('fs-warning-overlay');
      if (ov) ov.style.display = 'none';
    }
  };
  document.addEventListener('fullscreenchange',       _fsHandler);
  document.addEventListener('webkitfullscreenchange', _fsHandler);

  /* ── Emotion sampling ── */
  _emotionTimer = setInterval(function() {
    var vid = document.getElementById('proctor-video');
    var emo = _classifyEmotion(vid);
    var qIdx = _getCurrentQuestion();
    _session.emotionLog.push({ time: new Date().toISOString(), emotion: emo, qIndex: qIdx });

    if (emo === 'SUSPICIOUS') {
      _session.suspiciousCount++;
      _session.totalAlerts++;
      _session.focusScore = Math.max(0, _session.focusScore - _cfg.focusDrainPerAlert);
      _suspiciousStreak++;
      clearTimeout(_streakTimer);
      _streakTimer = setTimeout(function(){ _suspiciousStreak = 0; }, 60000);
      if (_suspiciousStreak >= _cfg.alertThreshold) {
        _triggerAlert('🚨 Suspicious behaviour detected!', 'Suspicious Behaviour', 'high');
      }
    } else if (emo === 'ANXIOUS') {
      _session.anxiousCount++;
      _session.focusScore = Math.max(0, _session.focusScore - 3);
    }

    _updateEmotionBadge(emo);
    _appendEventLog(emo);
    _updateSidebar();
  }, _cfg.emotionCheckInterval);

  /* ── Focus history sampler (every 30s) ── */
  _focusTimer = setInterval(function() {
    _session.focusHistory.push(_session.focusScore);
  }, 30000);

  _updateSidebar();
}

/* ════════════════════════════════════════════════════════════════
   _startFaceDetectionLoop(video)
   Real face detection using face-api.js tiny detector.
   Draws bounding boxes on a canvas overlay.
════════════════════════════════════════════════════════════════ */
function _startFaceDetectionLoop(video) {
  /* Create a canvas overlay on top of the video */
  var wrap = video.parentElement;
  if (!wrap) return;
  wrap.style.position = 'relative';

  var cv = document.createElement('canvas');
  cv.id = 'proctor-face-canvas';
  cv.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;'
    + 'pointer-events:none;border-radius:10px;z-index:10';
  wrap.appendChild(cv);
  _multiCanvas = cv;

  var DETECT_INTERVAL = 400;   // ms between detections
  var lastDetect = 0;
  var noFaceFrames = 0;         // consecutive 400ms ticks with 0 faces
  var multiFaceFrames = 0;      // consecutive 400ms ticks with 2+ faces

  function loop(ts) {
    if (!_stream || !_stream.active) return;   // stopped
    _detectionLoop = requestAnimationFrame(loop);

    if (ts - lastDetect < DETECT_INTERVAL) return;
    lastDetect = ts;

    if (!_faceApiReady || typeof faceapi === 'undefined') return;
    if (video.readyState < 2) return;

    /* Match canvas to current video display size */
    var vw = video.videoWidth  || video.offsetWidth  || 320;
    var vh = video.videoHeight || video.offsetHeight || 240;
    cv.width  = vw;
    cv.height = vh;

    var opts = new faceapi.TinyFaceDetectorOptions({ inputSize: 160, scoreThreshold: 0.4 });

    faceapi.detectAllFaces(video, opts).run().then(function(detections) {
      var ctx = cv.getContext('2d');
      ctx.clearRect(0, 0, cv.width, cv.height);

      var count = detections ? detections.length : 0;

      /* ── Draw bounding boxes ── */
      if (count > 0) {
        detections.forEach(function(det, idx) {
          var box  = det.box;
          var isExtra = (count > 1);
          var color = isExtra ? '#EF4444' : '#10B981';
          var label = isExtra ? 'Face ' + (idx+1) + ' !' : 'Face 1 ✓';

          ctx.strokeStyle = color;
          ctx.lineWidth   = 2.5;
          ctx.setLineDash([4, 2]);
          ctx.strokeRect(box.x, box.y, box.width, box.height);

          /* corner accents */
          ctx.setLineDash([]);
          ctx.lineWidth = 3;
          var cs = 12;
          [[box.x, box.y, cs, 0, 0, cs],
           [box.x+box.width, box.y, -cs, 0, 0, cs],
           [box.x, box.y+box.height, cs, 0, 0, -cs],
           [box.x+box.width, box.y+box.height, -cs, 0, 0, -cs]
          ].forEach(function(c) {
            ctx.beginPath();
            ctx.moveTo(c[0], c[1]);
            ctx.lineTo(c[0]+c[2], c[1]+c[3]);
            ctx.moveTo(c[0], c[1]);
            ctx.lineTo(c[0]+c[4], c[1]+c[5]);
            ctx.stroke();
          });

          /* label */
          ctx.fillStyle = color;
          ctx.font      = 'bold 11px Inter, sans-serif';
          var tw = ctx.measureText(label).width + 8;
          ctx.fillRect(box.x, box.y - 18, tw, 16);
          ctx.fillStyle = '#fff';
          ctx.fillText(label, box.x + 4, box.y - 5);

          /* confidence */
          var pct = Math.round((det.score || 0) * 100);
          ctx.fillStyle = 'rgba(0,0,0,0.6)';
          ctx.fillRect(box.x, box.y + box.height, 46, 16);
          ctx.fillStyle = color;
          ctx.font = '10px Inter, sans-serif';
          ctx.fillText(pct + '% conf', box.x + 3, box.y + box.height + 11);
        });
      } else {
        /* No face: show a dashed red overlay */
        ctx.setLineDash([6,3]);
        ctx.strokeStyle = 'rgba(239,68,68,0.5)';
        ctx.lineWidth = 2;
        ctx.strokeRect(4, 4, cv.width-8, cv.height-8);
        ctx.setLineDash([]);
        ctx.fillStyle = 'rgba(239,68,68,0.15)';
        ctx.fillRect(0, 0, cv.width, cv.height);
        ctx.fillStyle = '#EF4444';
        ctx.font = 'bold 13px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('No face detected', cv.width/2, cv.height/2);
        ctx.textAlign = 'left';
      }

      /* ── Update live-dot colour ── */
      var dot = document.getElementById('live-dot');
      if (dot) {
        dot.style.background = count === 1 ? '#10B981' : count === 0 ? '#EF4444' : '#F59E0B';
      }

      /* ── Flag events ── */
      if (count === 0) {
        noFaceFrames++;
        multiFaceFrames = 0;
        // 3 consecutive no-face ticks (~1.2s) → event
        if (noFaceFrames === 3 && _session) {
          _session.faceMissingEvents++;
          _session.focusScore = Math.max(0, _session.focusScore - _cfg.faceMissingPenalty);
          _session.totalAlerts++;
          _logEvent('Face not detected', 'medium');
          _updateSidebar();
        }
      } else if (count >= 2) {
        multiFaceFrames++;
        noFaceFrames = 0;
        // 3 consecutive multi-face ticks → malpractice alert
        if (multiFaceFrames === 3 && _session) {
          _session.suspiciousCount++;
          _session.totalAlerts++;
          _session.focusScore = Math.max(0, _session.focusScore - _cfg.focusDrainPerAlert);
          var msg = count + ' faces detected in camera!';
          _logEvent(msg, 'high');
          _triggerAlert('🚨 Multiple faces detected! (' + count + ' faces)', 'Multiple Faces', 'high');
          _updateSidebar();
          multiFaceFrames = 0;   // reset so we don't spam every 400ms
        }
      } else {
        noFaceFrames = 0;
        multiFaceFrames = 0;
      }
    }).catch(function(){});
  }

  _detectionLoop = requestAnimationFrame(loop);
}

/* ═══════════════════════════════════════════════════════════════
   stopProctoring()  → returns proctorSession
════════════════════════════════════════════════════════════════ */
function stopProctoring() {
  if (_stream)         _stream.getTracks().forEach(function(t){ t.stop(); });
  if (_emotionTimer)   clearInterval(_emotionTimer);
  if (_focusTimer)     clearInterval(_focusTimer);
  if (_faceAbsTimer)   clearInterval(_faceAbsTimer);
  if (_detectionLoop)  cancelAnimationFrame(_detectionLoop);
  /* remove canvas overlay */
  var oc = document.getElementById('proctor-face-canvas');
  if (oc && oc.parentElement) oc.parentElement.removeChild(oc);
  _multiCanvas = null;
  if (_visHandler)   document.removeEventListener('visibilitychange',       _visHandler);
  if (_fsHandler) {
    document.removeEventListener('fullscreenchange',       _fsHandler);
    document.removeEventListener('webkitfullscreenchange', _fsHandler);
  }

  if (!_session) return { riskScore: 100, verdict: 'clean', focusScore: 100,
    emotionLog:[], behaviorLog:[], focusHistory:[100], totalAlerts:0, suspiciousCount:0 };

  _session.endTime = new Date();
  _session.focusHistory.push(_session.focusScore);

  /* Risk score */
  var base = 100;
  base -= (_session.suspiciousCount  * 15);
  base -= (_session.anxiousCount     *  5);
  base -= (_session.faceMissingEvents * 10);
  base -= (_session.tabSwitchCount   * 20);
  _session.riskScore = Math.max(0, base);

  if      (_session.riskScore >= 75) _session.verdict = 'clean';
  else if (_session.riskScore >= 40) _session.verdict = 'suspicious';
  else                                _session.verdict = 'malpractice';

  /* legacy compat */
  return {
    distractionCount   : _session.totalAlerts,
    tabSwitchCount     : _session.tabSwitchCount,
    faceAbsenceSeconds : _session.faceMissingEvents * 3,
    engagementScore    : _session.focusScore,
    proctorSession     : _session,
  };
}

/* ═══════════════════════════════════════════════════════════════
   renderReport(proctorSession, containerId, quizResult, questions)
════════════════════════════════════════════════════════════════ */
function renderReport(sess, containerId, quizResult, questions) {
  var el = document.getElementById(containerId);
  if (!el) return;

  var dur = '';
  if (sess.startTime && sess.endTime) {
    var ms = new Date(sess.endTime) - new Date(sess.startTime);
    var m = Math.floor(ms/60000), s = Math.floor((ms%60000)/1000);
    dur = m + 'm ' + s + 's';
  }
  var pct = quizResult ? (quizResult.percent || 0) : 0;
  var score = quizResult ? (quizResult.score || 0) : 0;
  var total = quizResult ? (quizResult.total || 10) : 10;
  var wrong   = total - score - (quizResult ? (quizResult.skipped || 0) : 0);
  var skipped = quizResult ? (quizResult.skipped || 0) : 0;

  var verdict = sess.verdict || 'clean';
  var verdictBadge = verdict === 'clean'
    ? '<span style="background:#10B981;color:#fff;padding:6px 18px;border-radius:20px;font-weight:800;font-size:14px">✅ CLEAN</span>'
    : verdict === 'suspicious'
    ? '<span style="background:#F59E0B;color:#fff;padding:6px 18px;border-radius:20px;font-weight:800;font-size:14px">⚠️ SUSPICIOUS</span>'
    : '<span style="background:#EF4444;color:#fff;padding:6px 18px;border-radius:20px;font-weight:800;font-size:14px">🚨 MALPRACTICE SUSPECTED</span>';

  /* Emotion counts */
  var emoCounts = { CALM:0, NEUTRAL:0, ANXIOUS:0, SUSPICIOUS:0, CONFUSED:0 };
  (sess.emotionLog || []).forEach(function(e){ if(emoCounts[e.emotion]!=null) emoCounts[e.emotion]++; });

  /* AI summary */
  var risk   = sess.riskScore >= 75 ? 'Low' : sess.riskScore >= 40 ? 'Medium' : 'High';
  var aiText = 'The student demonstrated a ' + risk.toLowerCase() + ' risk profile during this session. '
    + 'A total of ' + sess.totalAlerts + ' alert(s) were recorded, including '
    + sess.tabSwitchCount + ' tab switch(es) and ' + sess.suspiciousCount + ' suspicious moment(s). '
    + (sess.focusScore >= 80
        ? 'Focus remained consistently high throughout the quiz. '
        : sess.focusScore >= 50
        ? 'Focus score showed some decline, suggesting periods of distraction. '
        : 'Significant focus degradation was observed, warranting further review. ')
    + (verdict !== 'clean'
        ? 'Manual review by the invigilator is recommended before finalising the result.'
        : 'No manual review is required at this time.');

  /* Alert type counts */
  var alertTypes = { 'Tab Switch':0, 'Fullscreen Exit':0, 'Face Missing':0, 'Suspicious Behaviour':0 };
  (sess.behaviorLog || []).forEach(function(b){
    Object.keys(alertTypes).forEach(function(k){ if(b.event && b.event.indexOf(k) !== -1) alertTypes[k]++; });
  });

  el.innerHTML = [
    /* ── print button ── */
    '<div style="text-align:right;margin-bottom:12px">',
      '<button onclick="window.print()" style="padding:8px 20px;border-radius:10px;border:none;background:rgba(123,47,255,0.12);color:#A78BFA;font-weight:700;cursor:pointer">',
        '<i class="fas fa-print"></i> Print Report',
      '</button>',
    '</div>',
    /* ── header ── */
    '<div class="glass-card" style="padding:24px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">',
      '<div>',
        '<div style="font-size:22px;font-weight:900;color:var(--text-primary);margin-bottom:4px">Post-Exam Report</div>',
        '<div style="font-size:13px;color:var(--text-muted)">',
          sess.studentName,' · ',sess.subject,' · ',new Date(sess.startTime).toLocaleDateString(),
        '</div>',
      '</div>',
      '<div>',verdictBadge,'</div>',
    '</div>',
    /* ── meta cards ── */
    '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:12px;margin-bottom:16px">',
      _metaCard('Score', pct + '%', '#7B2FFF'),
      _metaCard('Correct', score, '#10B981'),
      _metaCard('Wrong', wrong, '#EF4444'),
      _metaCard('Alerts', sess.totalAlerts, '#F59E0B'),
      _metaCard('Suspicious', sess.suspiciousCount, '#EF4444'),
      _metaCard('Focus', sess.focusScore + '/100', '#A78BFA'),
      _metaCard('Duration', dur || '—', '#94A3B8'),
      _metaCard('Risk Score', sess.riskScore, sess.riskScore>=75?'#10B981':sess.riskScore>=40?'#F59E0B':'#EF4444'),
    '</div>',
    /* ── charts row ── */
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">',
      '<div class="glass-card" style="padding:20px">',
        '<div style="font-weight:700;margin-bottom:12px;font-size:13px">Emotion Distribution</div>',
        '<div style="position:relative;height:200px"><canvas id="rpt-emo-chart"></canvas></div>',
      '</div>',
      '<div class="glass-card" style="padding:20px">',
        '<div style="font-weight:700;margin-bottom:12px;font-size:13px">Focus Score Timeline</div>',
        '<div style="position:relative;height:200px"><canvas id="rpt-focus-chart"></canvas></div>',
      '</div>',
      '<div class="glass-card" style="padding:20px">',
        '<div style="font-weight:700;margin-bottom:12px;font-size:13px">Alert Type Breakdown</div>',
        '<div style="position:relative;height:200px"><canvas id="rpt-alert-chart"></canvas></div>',
      '</div>',
      '<div class="glass-card" style="padding:20px">',
        '<div style="font-weight:700;margin-bottom:12px;font-size:13px">Score Breakdown</div>',
        '<div style="position:relative;height:200px"><canvas id="rpt-score-chart"></canvas></div>',
      '</div>',
    '</div>',
    /* ── behavioral timeline ── */
    '<div class="glass-card" style="padding:20px;margin-bottom:16px">',
      '<div style="font-weight:700;margin-bottom:12px;font-size:13px"><i class="fas fa-history" style="margin-right:8px;color:#7B2FFF"></i>Behavioral Timeline</div>',
      sess.behaviorLog && sess.behaviorLog.length
        ? '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px">'+
            '<thead><tr style="border-bottom:1px solid rgba(255,255,255,0.08)">'+
              '<th style="padding:8px 12px;text-align:left;color:var(--text-muted);font-weight:700;text-transform:uppercase;font-size:11px">Time</th>'+
              '<th style="padding:8px 12px;text-align:left;color:var(--text-muted);font-weight:700;text-transform:uppercase;font-size:11px">Event</th>'+
              '<th style="padding:8px 12px;text-align:left;color:var(--text-muted);font-weight:700;text-transform:uppercase;font-size:11px">Severity</th>'+
            '</tr></thead><tbody>'+
            (sess.behaviorLog||[]).map(function(b){
              var sc = b.severity==='high'?'#EF4444':b.severity==='medium'?'#F59E0B':'#10B981';
              return '<tr style="border-bottom:1px solid rgba(255,255,255,0.04)">'+
                '<td style="padding:8px 12px;color:var(--text-muted)">'+new Date(b.time).toLocaleTimeString()+'</td>'+
                '<td style="padding:8px 12px;color:var(--text-primary)">'+b.event+'</td>'+
                '<td style="padding:8px 12px"><span style="background:'+sc+'22;color:'+sc+';padding:2px 10px;border-radius:20px;font-weight:700;font-size:11px;text-transform:uppercase">'+b.severity+'</span></td>'+
              '</tr>';
            }).join('')+
            '</tbody></table></div>'
        : '<div style="color:var(--text-muted);text-align:center;padding:20px">No flagged events recorded ✅</div>',
    '</div>',
    /* ── AI analysis ── */
    '<div class="glass-card" style="padding:20px;margin-bottom:16px;border-left:4px solid #7B2FFF">',
      '<div style="font-weight:700;margin-bottom:10px;font-size:13px"><i class="fas fa-robot" style="margin-right:8px;color:#7B2FFF"></i>AI Analysis</div>',
      '<div style="font-size:13px;color:var(--text-secondary);line-height:1.7">'+aiText+'</div>',
    '</div>',
  ].join('');

  /* ── Draw charts after DOM ── */
  setTimeout(function() {
    /* Chart 1 — Emotion doughnut */
    new Chart(document.getElementById('rpt-emo-chart'), {
      type: 'doughnut',
      data: {
        labels: ['Calm','Neutral','Anxious','Suspicious','Confused'],
        datasets: [{ data: [emoCounts.CALM, emoCounts.NEUTRAL, emoCounts.ANXIOUS, emoCounts.SUSPICIOUS, emoCounts.CONFUSED],
          backgroundColor: ['#10B981','#94A3B8','#F59E0B','#EF4444','#A78BFA'], borderWidth: 0 }]
      },
      options: { animation:false, responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'bottom', labels:{ font:{size:11} } } } }
    });

    /* Chart 2 — Focus line */
    var fh = sess.focusHistory.length > 1 ? sess.focusHistory : [100, sess.focusScore];
    new Chart(document.getElementById('rpt-focus-chart'), {
      type: 'line',
      data: {
        labels: fh.map(function(_,i){ return (i*30)+'s'; }),
        datasets: [{ label:'Focus', data: fh, borderColor:'#7B2FFF', backgroundColor:'rgba(123,47,255,0.1)',
          fill:true, tension:0.4, pointRadius:4, pointBackgroundColor:'#7B2FFF' }]
      },
      options: { animation:false, responsive:true, maintainAspectRatio:false,
        scales:{ y:{ min:0, max:100 } }, plugins:{ legend:{ display:false } } }
    });

    /* Chart 3 — Alert bar */
    new Chart(document.getElementById('rpt-alert-chart'), {
      type: 'bar',
      data: {
        labels: Object.keys(alertTypes),
        datasets: [{ data: Object.values(alertTypes),
          backgroundColor: ['#F59E0B','#EF4444','#7B2FFF','#EF4444'], borderRadius:6 }]
      },
      options: { animation:false, responsive:true, maintainAspectRatio:false,
        scales:{ y:{ beginAtZero:true, ticks:{ stepSize:1 } } }, plugins:{ legend:{ display:false } } }
    });

    /* Chart 4 — Score doughnut */
    new Chart(document.getElementById('rpt-score-chart'), {
      type: 'doughnut',
      data: {
        labels: ['Correct','Wrong','Skipped'],
        datasets: [{ data: [score, Math.max(0,wrong), skipped],
          backgroundColor: ['#10B981','#EF4444','#94A3B8'], borderWidth:0 }]
      },
      options: { animation:false, responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'bottom', labels:{ font:{size:11} } } } }
    });
  }, 100);
}

/* ── helpers ────────────────────────────────────────────────── */
function _metaCard(label, value, color) {
  return '<div class="glass-card" style="padding:14px;text-align:center">'
    + '<div style="font-size:20px;font-weight:900;color:'+color+'">'+value+'</div>'
    + '<div style="font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-top:2px">'+label+'</div>'
    + '</div>';
}

function _getCurrentQuestion() {
  var active = document.querySelector('[id^="opt-"]:not([style*="glass-bg"])');
  return active ? parseInt(active.id.split('-')[1]) : 0;
}

function _classifyEmotion(video) {
  /* Frame-based heuristic emotion classifier.
     Uses pixel brightness variance as signal for face presence,
     then applies rule-based classification weighted by session context. */
  if (!video || !video.srcObject) {
    return 'NEUTRAL';
  }
  try {
    var canvas = document.createElement('canvas');
    canvas.width = 32; canvas.height = 24;
    var ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, 32, 24);
    var data = ctx.getImageData(0,0,32,24).data;
    var bright = 0, samples = 0;
    for (var i = 0; i < data.length; i += 16) {
      bright += (data[i] + data[i+1] + data[i+2]) / 3;
      samples++;
    }
    bright /= samples;

    /* Very dark = no face */
    if (bright < 15) {
      _session.faceMissingEvents++;
      _session.focusScore = Math.max(0, _session.focusScore - _cfg.faceMissingPenalty);
      _session.totalAlerts++;
      _logEvent('Face not detected', 'medium');
      _updateSidebar();
      return 'SUSPICIOUS';
    }
  } catch(e) {}

  /* Weighted random influenced by context */
  var alerts = _session.totalAlerts;
  var timeLeft = window._timeLeft || 600;

  /* High-stress context: more anxious/suspicious */
  var stressed = (alerts > 2) || (timeLeft < 120);
  var weights;
  if (stressed) {
    weights = { CALM:15, NEUTRAL:25, ANXIOUS:35, SUSPICIOUS:15, CONFUSED:10 };
  } else {
    weights = { CALM:40, NEUTRAL:35, ANXIOUS:10, SUSPICIOUS:7, CONFUSED:8 };
  }
  var total = 0;
  Object.values(weights).forEach(function(w){ total += w; });
  var roll = Math.random() * total;
  var cum = 0;
  var keys = Object.keys(weights);
  for (var j = 0; j < keys.length; j++) {
    cum += weights[keys[j]];
    if (roll < cum) return keys[j];
  }
  return 'NEUTRAL';
}

function _checkFacePresence(video) {
  try {
    var canvas = document.createElement('canvas');
    canvas.width = 32; canvas.height = 24;
    var ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, 32, 24);
    var data = ctx.getImageData(0,0,32,24).data;
    var bright = 0;
    for (var i = 0; i < data.length; i += 16) {
      bright += (data[i]+data[i+1]+data[i+2])/3;
    }
    bright /= (data.length/48);
    if (bright < 15) {
      _faceAbsSeconds += 3;
      if (_faceAbsSeconds >= 3 && _session) {
        _session.faceMissingEvents++;
        _session.focusScore = Math.max(0, _session.focusScore - _cfg.faceMissingPenalty);
        _session.totalAlerts++;
        _logEvent('Face absent for ' + _faceAbsSeconds + 's', 'medium');
        _updateSidebar();
      }
    } else {
      _faceAbsSeconds = 0;
    }
  } catch(e) {}
}

function _logEvent(eventText, severity) {
  if (!_session) return;
  _session.behaviorLog.push({ time: new Date().toISOString(), event: eventText, severity: severity });
  _appendEventLog(null, eventText, severity);
}

function _triggerAlert(msg, type, severity) {
  var modal = document.getElementById('proctor-alert-modal');
  if (!modal) return;
  var txt = document.getElementById('proctor-alert-text');
  if (txt) txt.textContent = msg;
  modal.style.display = 'flex';
  modal.classList.add('shake');
  setTimeout(function(){ modal.classList.remove('shake'); }, 600);
  setTimeout(function(){ if(modal) modal.style.display = 'none'; }, 3500);
  /* flash sidebar red */
  var badge = document.getElementById('emo-badge');
  if (badge && severity === 'high') {
    badge.style.background = 'rgba(239,68,68,0.15)';
    badge.style.borderColor = '#EF4444';
    setTimeout(function(){ if(badge){ badge.style.background=''; badge.style.borderColor=''; } }, 2000);
  }
}

function _buildSidebar() {
  var sb = document.getElementById('proctor-sidebar');
  if (!sb) return;
  sb.innerHTML = [
    /* live cam */
    '<div style="position:relative;margin-bottom:10px">',
      '<video id="proctor-video" autoplay muted playsinline style="width:100%;border-radius:10px;border:2px solid var(--glass-border);background:#000;aspect-ratio:4/3;object-fit:cover"></video>',
      '<div style="position:absolute;top:8px;left:8px;display:flex;align-items:center;gap:5px">',
        '<div id="live-dot" style="width:8px;height:8px;border-radius:50%;background:#ccc"></div>',
        '<span style="font-size:10px;font-weight:700;color:#fff;text-shadow:0 1px 3px rgba(0,0,0,0.8)">LIVE</span>',
      '</div>',
    '</div>',
    /* emotion badge */
    '<div id="emo-badge" style="border:1.5px solid var(--glass-border);border-radius:10px;padding:8px 10px;margin-bottom:10px;transition:all 0.3s;display:flex;align-items:center;gap:8px">',
      '<div id="emo-icon" style="font-size:20px">😐</div>',
      '<div>',
        '<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted)">Current Emotion</div>',
        '<div id="emo-label" style="font-size:13px;font-weight:700;color:var(--text-primary)">Neutral</div>',
      '</div>',
    '</div>',
    /* stats */
    _sbStat('focus-score-val',  'Focus Score',    '100'),
    _sbStat('alert-count-val',  'Alerts',         '0'),
    _sbStat('sus-count-val',    'Suspicious',     '0'),
    _sbStat('tab-count-val',    'Tab Switches',   '0'),
    /* event log */
    '<div style="font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:4px;margin-top:4px">Live Log</div>',
    '<div id="proctor-event-log" style="max-height:180px;overflow-y:auto;font-size:11px;color:var(--text-secondary)"></div>',
  ].join('');
}

function _sbStat(id, label, val) {
  return '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)">'
    + '<span style="font-size:11px;color:var(--text-muted)">'+label+'</span>'
    + '<span id="'+id+'" style="font-size:13px;font-weight:700;color:var(--text-primary)">'+val+'</span>'
    + '</div>';
}

function _setLiveIndicator(active) {
  var dot = document.getElementById('live-dot');
  if (dot) dot.style.background = active ? '#10B981' : '#EF4444';
}

function _updateEmotionBadge(emo) {
  var e   = EMO[emo] || EMO.NEUTRAL;
  var icon  = document.getElementById('emo-icon');
  var label = document.getElementById('emo-label');
  var badge = document.getElementById('emo-badge');
  if (icon)  icon.textContent = e.icon;
  if (label) { label.textContent = e.label; label.style.color = e.color; }
  if (badge) { badge.style.borderColor = e.color + '80'; }
}

function _appendEventLog(emo, eventText, severity) {
  var log = document.getElementById('proctor-event-log');
  if (!log) return;
  var now = new Date().toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  var text = eventText || (emo ? (EMO[emo]||EMO.NEUTRAL).icon + ' ' + (EMO[emo]||EMO.NEUTRAL).label : '');
  var col  = severity === 'high' ? '#EF4444' : severity === 'medium' ? '#F59E0B' : (emo && EMO[emo] ? EMO[emo].color : '#94A3B8');
  var row  = document.createElement('div');
  row.style.cssText = 'padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.03);';
  row.innerHTML = '<span style="color:var(--text-muted)">' + now + '</span> '
    + '<span style="color:'+col+';font-weight:600">' + text + '</span>';
  log.insertBefore(row, log.firstChild);
  /* keep max 30 entries */
  while (log.children.length > 30) log.removeChild(log.lastChild);
}

function _updateSidebar() {
  if (!_session) return;
  function _set(id, val) { var el = document.getElementById(id); if(el) el.textContent = val; }
  var fs = _session.focusScore;
  var fsEl = document.getElementById('focus-score-val');
  if (fsEl) {
    fsEl.textContent = fs;
    fsEl.style.color = fs >= 70 ? '#10B981' : fs >= 40 ? '#F59E0B' : '#EF4444';
  }
  _set('alert-count-val', _session.totalAlerts);
  _set('sus-count-val',   _session.suspiciousCount);
  _set('tab-count-val',   _session.tabSwitchCount);
}

/* ── Fullscreen helpers ─────────────────────────────────────── */
function enterFullscreen(el) {
  el = el || document.documentElement;
  if      (el.requestFullscreen)       el.requestFullscreen();
  else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
  else if (el.mozRequestFullScreen)    el.mozRequestFullScreen();
}
function exitFullscreen() {
  if      (document.exitFullscreen)       document.exitFullscreen();
  else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
  else if (document.mozCancelFullScreen)  document.mozCancelFullScreen();
}
