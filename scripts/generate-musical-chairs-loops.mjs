#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const outDir = process.argv[2] || '/private/tmp/localplay-musical-chairs-audio';
const sampleRate = 22050;
const seconds = 16;
const volume = 0.22;

const tracks = [
  ['upbeat-confetti', 126, [261.63, 329.63, 392.0, 523.25]],
  ['upbeat-bounce', 132, [293.66, 369.99, 440.0, 587.33]],
  ['upbeat-neon', 122, [246.94, 311.13, 415.3, 493.88]],
  ['upbeat-sprinkles', 128, [329.63, 392.0, 493.88, 659.25]],
  ['jazzy-lounge', 104, [220.0, 277.18, 329.63, 392.0]],
  ['jazzy-swing', 112, [233.08, 293.66, 349.23, 415.3]],
  ['jazzy-walk', 108, [196.0, 246.94, 293.66, 369.99]],
  ['jazzy-wink', 116, [174.61, 220.0, 261.63, 329.63]],
  ['suspense-tiptoe', 92, [196.0, 207.65, 233.08, 261.63]],
  ['suspense-clock', 98, [220.0, 233.08, 261.63, 311.13]],
  ['suspense-pulse', 102, [164.81, 196.0, 220.0, 246.94]],
  ['suspense-sting', 88, [146.83, 174.61, 207.65, 246.94]],
  ['retro-arcade', 118, [261.63, 329.63, 415.3, 659.25]],
  ['retro-wave', 124, [220.0, 277.18, 369.99, 554.37]],
  ['retro-pixel', 120, [246.94, 311.13, 392.0, 622.25]],
  ['retro-cassette', 114, [196.0, 246.94, 329.63, 493.88]],
  ['tropical-island', 108, [261.63, 349.23, 392.0, 523.25]],
  ['tropical-sun', 112, [293.66, 369.99, 440.0, 587.33]],
  ['tropical-breeze', 104, [220.0, 293.66, 349.23, 440.0]],
  ['tropical-mango', 110, [246.94, 329.63, 392.0, 493.88]],
];

function envelope(t, duration) {
  const attack = Math.min(0.03, duration / 4);
  const release = Math.min(0.05, duration / 3);
  if (t < attack) return t / attack;
  if (t > duration - release) return Math.max(0, (duration - t) / release);
  return 1;
}

function tone(freq, t, kind = 'sine') {
  const x = 2 * Math.PI * freq * t;
  if (kind === 'square') return Math.sin(x) >= 0 ? 1 : -1;
  if (kind === 'tri') return (2 / Math.PI) * Math.asin(Math.sin(x));
  return Math.sin(x);
}

function writeWav(filePath, samples) {
  const dataSize = samples.length * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write('WAVE', 8);
  buffer.write('fmt ', 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataSize, 40);
  samples.forEach((sample, index) => {
    const clamped = Math.max(-1, Math.min(1, sample));
    buffer.writeInt16LE(Math.round(clamped * 32767), 44 + index * 2);
  });
  fs.writeFileSync(filePath, buffer);
}

function generateTrack([id, bpm, notes]) {
  const total = sampleRate * seconds;
  const beat = 60 / bpm;
  const samples = new Float32Array(total);
  for (let i = 0; i < total; i += 1) {
    const t = i / sampleRate;
    const beatIndex = Math.floor(t / beat);
    const beatPhase = (t % beat) / beat;
    const barPhase = (t % (beat * 4)) / (beat * 4);
    const note = notes[beatIndex % notes.length];
    const bass = notes[Math.floor(beatIndex / 2) % notes.length] / 2;
    let sample = 0;
    sample += tone(note, t, id.startsWith('retro') ? 'square' : 'tri') * envelope(beatPhase * beat, beat * 0.75) * 0.45;
    sample += tone(bass, t, 'sine') * 0.28;
    if (beatPhase < 0.07) sample += (Math.random() * 2 - 1) * (1 - beatPhase / 0.07) * 0.28;
    if ((beatIndex + 2) % 4 === 0 && beatPhase < 0.04) sample += tone(880, t, 'sine') * (1 - beatPhase / 0.04) * 0.16;
    sample *= 0.82 + Math.sin(barPhase * Math.PI * 2) * 0.08;
    samples[i] = sample * volume;
  }
  return samples;
}

fs.mkdirSync(outDir, { recursive: true });
for (const track of tracks) {
  writeWav(path.join(outDir, `${track[0]}.wav`), generateTrack(track));
}
fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(tracks.map(([id, bpm]) => ({ id, bpm, file: `${id}.wav` })), null, 2));
console.log(`Generated ${tracks.length} Musical Chairs loops in ${outDir}`);
