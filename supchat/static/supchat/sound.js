/* Tiny WebAudio synth: no audio files to download. Respects a persisted mute flag. */
(function (root) {
  'use strict';
  var ctx = null;
  var KEY = 'supchat.sound';

  function enabled() {
    try { return localStorage.getItem(KEY) !== 'off'; } catch (_) { return true; }
  }
  function setEnabled(on) {
    try { localStorage.setItem(KEY, on ? 'on' : 'off'); } catch (_) { /* private mode */ }
  }
  function ac() {
    if (!ctx) {
      var C = root.AudioContext || root.webkitAudioContext;
      if (!C) return null;
      try { ctx = new C(); } catch (_) { return null; }
    }
    if (ctx.state === 'suspended') { try { ctx.resume(); } catch (_) { /* needs a gesture */ } }
    return ctx;
  }
  function tone(c, freq, start, dur, gain) {
    var o = c.createOscillator(), g = c.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(freq, start);
    g.gain.setValueAtTime(0.0001, start);
    g.gain.exponentialRampToValueAtTime(gain, start + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
    o.connect(g); g.connect(c.destination);
    o.start(start); o.stop(start + dur + 0.02);
  }
  var PATTERNS = {
    incoming: [[880, 0, 0.14], [1318, 0.09, 0.2]],
    outgoing: [[660, 0, 0.09], [880, 0.05, 0.12]],
    notify:   [[784, 0, 0.12], [988, 0.1, 0.12], [1319, 0.2, 0.22]]
  };
  function play(name) {
    if (!enabled()) return;
    var c = ac();
    if (!c) return;
    var p = PATTERNS[name] || PATTERNS.incoming, now = c.currentTime;
    p.forEach(function (n) { tone(c, n[0], now + n[1], n[2], 0.06); });
  }
  /* Browsers only allow audio after a user gesture: unlock on the first interaction. */
  ['pointerdown', 'keydown'].forEach(function (ev) {
    root.addEventListener(ev, function once() { ac(); root.removeEventListener(ev, once, true); }, true);
  });
  root.SupchatSound = { play: play, enabled: enabled, setEnabled: setEnabled };
})(window);
