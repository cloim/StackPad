import { Capacitor } from '@capacitor/core';
import { Haptics, ImpactStyle, NotificationType } from '@capacitor/haptics';

const STORAGE_KEY = 'stackpad.feedback';

export function getFeedbackSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { haptics: true, sound: false, ...JSON.parse(raw) };
  } catch (_) {}
  return { haptics: true, sound: false };
}

export function saveFeedbackSettings(settings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (_) {}
}

let audioCtx = null;

function getAudioContext() {
  if (typeof window === 'undefined') return null;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return null;
  if (!audioCtx) {
    audioCtx = new AudioContextClass();
  }
  if (audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

function playNoiseClick() {
  const ctx = getAudioContext();
  if (!ctx) return;
  const t = ctx.currentTime;

  // 25ms noise buffer
  const sampleRate = ctx.sampleRate;
  const bufferSize = Math.floor(sampleRate * 0.025);
  const buffer = ctx.createBuffer(1, bufferSize, sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < bufferSize; i++) {
    data[i] = (Math.random() * 2 - 1) * 0.3;
  }

  const noise = ctx.createBufferSource();
  noise.buffer = buffer;

  const filter = ctx.createBiquadFilter();
  filter.type = 'bandpass';
  filter.frequency.value = 1200;

  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0.06, t);
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.025);

  noise.connect(filter);
  filter.connect(gain);
  gain.connect(ctx.destination);

  // Low bass decay
  const osc = ctx.createOscillator();
  const oscGain = ctx.createGain();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(140, t);
  osc.frequency.exponentialRampToValueAtTime(40, t + 0.03);
  oscGain.gain.setValueAtTime(0.08, t);
  oscGain.gain.exponentialRampToValueAtTime(0.001, t + 0.03);

  osc.connect(oscGain);
  oscGain.connect(ctx.destination);

  noise.start(t);
  osc.start(t);
  noise.stop(t + 0.025);
  osc.stop(t + 0.03);
}

function playAscending() {
  const ctx = getAudioContext();
  if (!ctx) return;
  const t = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'triangle';
  osc.frequency.setValueAtTime(440, t);
  osc.frequency.setValueAtTime(660, t + 0.06);

  gain.gain.setValueAtTime(0.05, t);
  gain.gain.setValueAtTime(0.06, t + 0.06);
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.16);

  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(t);
  osc.stop(t + 0.16);
}

function playDescending() {
  const ctx = getAudioContext();
  if (!ctx) return;
  const t = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'triangle';
  osc.frequency.setValueAtTime(520, t);
  osc.frequency.setValueAtTime(330, t + 0.06);

  gain.gain.setValueAtTime(0.05, t);
  gain.gain.setValueAtTime(0.06, t + 0.06);
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.16);

  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(t);
  osc.stop(t + 0.16);
}

function playBuzzer() {
  const ctx = getAudioContext();
  if (!ctx) return;
  const t = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'sawtooth';
  osc.frequency.setValueAtTime(130, t);

  gain.gain.setValueAtTime(0.05, t);
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.18);

  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(t);
  osc.stop(t + 0.18);
}

export function press() {
  const { haptics, sound } = getFeedbackSettings();
  if (haptics) {
    try {
      if (Capacitor.isNativePlatform()) {
        Haptics.impact({ style: ImpactStyle.Light }).catch(() => {});
      } else if (typeof navigator !== 'undefined' && navigator.vibrate) {
        navigator.vibrate(10);
      }
    } catch (_) {}
  }
  if (sound) {
    try {
      playNoiseClick();
    } catch (_) {}
  }
}

export function success(action = 'start') {
  const { haptics, sound } = getFeedbackSettings();
  if (haptics) {
    try {
      if (Capacitor.isNativePlatform()) {
        Haptics.notification({ type: NotificationType.Success }).catch(() => {});
      } else if (typeof navigator !== 'undefined' && navigator.vibrate) {
        navigator.vibrate([10, 40, 10]);
      }
    } catch (_) {}
  }
  if (sound) {
    try {
      if (action === 'stop') {
        playDescending();
      } else {
        playAscending();
      }
    } catch (_) {}
  }
}

export function failure() {
  const { haptics, sound } = getFeedbackSettings();
  if (haptics) {
    try {
      if (Capacitor.isNativePlatform()) {
        Haptics.notification({ type: NotificationType.Error }).catch(() => {});
      } else if (typeof navigator !== 'undefined' && navigator.vibrate) {
        navigator.vibrate([30, 60, 30]);
      }
    } catch (_) {}
  }
  if (sound) {
    try {
      playBuzzer();
    } catch (_) {}
  }
}
