# JARVIS Voice Integration Guide

This guide covers adding **speech-to-text (STT)** input and **text-to-speech (TTS)** output to JARVIS. It is a design reference — **do not execute it as part of the advanced features sprint**. Voice is a Phase 2+ feature that depends on Security (key redaction), Agent Harness (`JarvisAgent`), and Performance (provider health) already being in place.

---

## Table of Contents
1. [Design goals](#design-goals)
2. [Architecture overview](#architecture-overview)
3. [WebSocket event additions](#websocket-event-additions)
4. [Speech-to-text (STT)](#speech-to-text-stt)
5. [Text-to-speech (TTS)](#text-to-speech-tts)
6. [UI integration](#ui-integration)
7. [Wake-word / hotword (optional)](#wake-word--hotword-optional)
8. [Privacy, security, permissions](#privacy-security-permissions)
9. [Performance considerations](#performance-considerations)
10. [Implementation order](#implementation-order)
11. [Open questions](#open-questions)

---

## 1. Design goals

- **Local-first by default.** "Secure mode" (local) MUST NOT send audio to cloud APIs. Match the existing local/cloud split in `backend/ai/providers.py`.
- **Streaming on both sides.** Partial STT transcripts stream into the chat input; TTS starts speaking before the full LLM response has been generated.
- **Interruptible.** Talking over JARVIS cancels current TTS playback (barge-in).
- **Zero regression on typed workflow.** Voice is additive — every feature must still work without a microphone.
- **One-key toggle.** Push-to-talk via Space/Ctrl+Space while focused on the input; click-to-toggle via a mic button in the input area.

---

## 2. Architecture overview

```
┌────────────────────┐  audio frames (PCM 16k)  ┌──────────────────────┐
│  Electron renderer │ ───────────────────────▶│  Backend WS handler  │
│  (MediaRecorder,   │                          │  (/backend/audio/)   │
│   Web Audio API)   │ ◀─ partial transcripts ──│  STT engine           │
│                    │ ◀─ TTS audio chunks ─────│  TTS engine           │
└────────────────────┘                          └──────────────────────┘
         │                                                 │
         ▼                                                 ▼
     Mic / Speakers                          Faster-whisper (local) OR
                                             Deepgram / Google Cloud STT (cloud)
                                             Piper (local) OR
                                             ElevenLabs / OpenAI TTS (cloud)
```

**Two new modules** on the backend:
- `backend/audio/stt_service.py` — routes to local/cloud STT based on `mode`
- `backend/audio/tts_service.py` — routes to local/cloud TTS based on `mode`

**One new hook** on the frontend:
- `src/hooks/useVoice.js` — wraps MediaRecorder + Web Audio playback, speaks to WS

---

## 3. WebSocket event additions

Follow the existing locked-name pattern (`user_query`, `jarvis_stream_chunk`, etc.). Add to `src/constants/wsEvents.js`:

```js
export const SEND = {
  ...existing,
  AUDIO_CHUNK:       'audio_chunk',        // frontend → backend: mic audio
  AUDIO_STREAM_END:  'audio_stream_end',   // frontend → backend: user stopped talking
  TTS_INTERRUPT:     'tts_interrupt',      // frontend → backend: cancel current TTS
};

export const RECV = {
  ...existing,
  STT_PARTIAL:       'stt_partial',        // backend → frontend: partial transcript
  STT_FINAL:         'stt_final',          // backend → frontend: final transcript (becomes the query)
  TTS_AUDIO_CHUNK:   'tts_audio_chunk',    // backend → frontend: PCM/Opus audio frame
  TTS_AUDIO_END:     'tts_audio_end',      // backend → frontend: stream done
};
```

**Payload shapes:**
- `audio_chunk`: `{ event, data: base64 PCM16 @ 16 kHz mono, seq }`
- `stt_partial`: `{ event, text, is_final: false }`
- `stt_final`:   `{ event, text, is_final: true }`  → frontend dispatches the text as a normal `user_query`
- `tts_audio_chunk`: `{ event, data: base64 Opus/PCM, seq, done: false }`
- `tts_audio_end`: `{ event, done: true }`

Binary frames (`ws.send(Buffer)`) would be more efficient than base64, but the existing contract is JSON; keep consistency for Phase 2 and switch later if measurement shows a problem.

---

## 4. Speech-to-text (STT)

### Local (Secure mode) — faster-whisper

```python
# backend/audio/stt_service.py
from faster_whisper import WhisperModel

_model = None
def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        size = os.environ.get("WHISPER_MODEL", "base.en")   # tiny.en is faster
        _model = WhisperModel(size, device="cpu", compute_type="int8")
    return _model

async def transcribe_stream(pcm_iter, send_event, lang="en"):
    """Chunked streaming transcription.
    pcm_iter: async iterator of 20-ms PCM16 frames.
    """
    buffer = bytearray()
    async for frame in pcm_iter:
        buffer.extend(frame)
        # Every ~400 ms, transcribe the accumulated buffer
        if len(buffer) >= 16000 * 2 * 0.4:
            partial = _transcribe_buffer(bytes(buffer))
            await send_event({"event": "stt_partial", "text": partial, "is_final": False})
    final = _transcribe_buffer(bytes(buffer))
    await send_event({"event": "stt_final", "text": final, "is_final": True})
```

**Why faster-whisper, not vanilla Whisper?** 4x faster, lower memory, works on CPU with int8 quantization. Acceptable latency for push-to-talk on a mid-tier laptop.

**VAD (voice activity detection):** use `webrtcvad` to drop silence frames — halves compute.

### Cloud mode — Deepgram (streaming) or OpenAI Whisper API

Deepgram is the better fit:
- True WebSocket streaming with interim results (matches JARVIS's chat streaming pattern)
- Per-minute pricing, ~$0.0043/min for Nova-2
- Language detection + punctuation built in

OpenAI Whisper API requires sending whole audio files — use only for non-streaming "attach audio" flows.

```python
# Cloud path
async def transcribe_stream_cloud(pcm_iter, send_event):
    async with deepgram.listen.stream.v("1", {
        "model": "nova-2", "language": "en",
        "encoding": "linear16", "sample_rate": 16000,
        "interim_results": True,
    }) as stream:
        async def forward():
            async for frame in pcm_iter:
                await stream.send(frame)
            await stream.finish()
        async def consume():
            async for evt in stream:
                if evt.is_final:
                    await send_event({"event": "stt_final", "text": evt.text, "is_final": True})
                else:
                    await send_event({"event": "stt_partial", "text": evt.text, "is_final": False})
        await asyncio.gather(forward(), consume())
```

**Key handling:** `DEEPGRAM_API_KEY` in `.env`; never log the key; redact via `security.py::redact_keys` if it ever hits a log path.

---

## 5. Text-to-speech (TTS)

### Local (Secure mode) — Piper

Piper produces natural-sounding speech on-CPU (<100 ms to first audio chunk for short sentences) with ONNX runtime. Pre-download a voice model (e.g., `en_US-amy-medium.onnx`) into `backend/audio/voices/`.

```python
# backend/audio/tts_service.py (local)
from piper import PiperVoice

_voice = None
def _get_voice() -> PiperVoice:
    global _voice
    if _voice is None:
        voice_path = Path(__file__).parent / "voices" / "en_US-amy-medium.onnx"
        _voice = PiperVoice.load(voice_path)
    return _voice

async def speak(text: str, send_event, interrupt_evt: asyncio.Event):
    voice = _get_voice()
    seq = 0
    for audio_chunk in voice.synthesize_stream_raw(text):  # yields PCM16 frames
        if interrupt_evt.is_set():
            return
        await send_event({
            "event": "tts_audio_chunk",
            "data": base64.b64encode(audio_chunk).decode(),
            "seq": seq, "done": False,
        })
        seq += 1
    await send_event({"event": "tts_audio_end", "done": True})
```

### Cloud mode — ElevenLabs or OpenAI TTS

ElevenLabs: premium voices, ~200 ms first-chunk latency via streaming endpoint, ~$0.18/1k chars on Pro plan.
OpenAI `tts-1`: cheaper, ~$0.015/1k chars, decent quality, no streaming (full response delivered once).

For JARVIS's "feel like a real assistant" goal, ElevenLabs streaming wins. OpenAI TTS is the fallback.

### Sentence-level chunking for barge-in

Don't wait for the full LLM response before synthesizing. Split incoming `jarvis_stream_chunk` text into sentences using a boundary regex (`[.!?](?:\s|$)`), synthesize each sentence as it completes, and check the interrupt event between sentences. This makes barge-in feel instant.

---

## 6. UI integration

### New component: microphone button in `ChatArea`

```jsx
// src/components/MicButton.jsx
export default function MicButton({ isRecording, onToggle, disabled }) {
  return (
    <button
      className={`btn-mic ${isRecording ? 'recording' : ''}`}
      onClick={onToggle}
      disabled={disabled}
      title={isRecording ? 'Stop recording (Space)' : 'Start recording (Space)'}
    >
      <IconMic />
      {isRecording && <span className="mic-pulse" />}
    </button>
  );
}
```

Place it next to the `btn-send` button in `ChatArea.jsx`. When `isRecording`, a pulsing red ring animates around the icon.

### `useVoice` hook

```js
// src/hooks/useVoice.js
export default function useVoice({ sendMessage, onFinalTranscript, onTtsChunk }) {
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const recorderRef = useRef(null);
  const audioCtxRef = useRef(null);

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const ctx = new AudioContext({ sampleRate: 16000 });
    const source = ctx.createMediaStreamSource(stream);
    const processor = ctx.createScriptProcessor(1024, 1, 1);
    processor.onaudioprocess = (e) => {
      const pcm = floatTo16BitPCM(e.inputBuffer.getChannelData(0));
      sendMessage({ event: 'audio_chunk', data: base64(pcm), seq: seqCounter++ });
    };
    source.connect(processor);
    processor.connect(ctx.destination);
    recorderRef.current = { stream, ctx, processor };
    setIsRecording(true);
  };

  const stopRecording = () => {
    const r = recorderRef.current;
    if (r) {
      r.processor.disconnect(); r.ctx.close();
      r.stream.getTracks().forEach(t => t.stop());
      sendMessage({ event: 'audio_stream_end' });
    }
    setIsRecording(false);
  };

  // Play TTS audio chunks as they arrive
  const playChunk = async (base64Data) => {
    if (!audioCtxRef.current) audioCtxRef.current = new AudioContext();
    const buf = await audioCtxRef.current.decodeAudioData(base64ToArrayBuffer(base64Data));
    const src = audioCtxRef.current.createBufferSource();
    src.buffer = buf; src.connect(audioCtxRef.current.destination); src.start();
  };

  // Push-to-talk: Space while input focused, not while typing
  useEffect(() => {
    const onKey = (e) => {
      if (e.code === 'Space' && document.activeElement?.id === 'jarvis-input' && !e.repeat) {
        e.preventDefault();
        isRecording ? stopRecording() : startRecording();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isRecording]);

  return { isRecording, isSpeaking, startRecording, stopRecording, playChunk };
}
```

**Wire into `App.jsx`:** register `stt_final` handler that calls `handleSend(text)` with the transcribed text; register `tts_audio_chunk` handler that calls `playChunk`.

---

## 7. Wake-word / hotword (optional)

Wake-word ("Hey JARVIS") is a nice-to-have, not a Phase 2 must. Two options:

- **Picovoice Porcupine** — commercial, free tier for personal use, <15 ms detection latency. Add `pvporcupine` to `requirements.txt`, run in a dedicated thread in `backend/audio/wake_word.py`.
- **openWakeWord** — fully OSS, requires training or using one of the pre-trained wake-words (none of which are "JARVIS" out of the box).

If implementing: keep it **opt-in via settings**, never auto-record, and **show a visible indicator** in the tray (and in the UI) whenever the wake-word listener is armed. Users must be able to disable it completely.

---

## 8. Privacy, security, permissions

- **Local-first constraint.** In `mode === 'local'`, backend MUST refuse to route audio to cloud providers, even if cloud STT/TTS keys are present. Guard at the routing layer, not at the provider layer.
- **Audio is never persisted to disk** unless the user explicitly enables "save audio for debugging". No raw audio in logs.
- **Redact transcripts.** Apply `security.py::redact_keys` to final transcripts before they enter the chat history — users often speak commands that include paths containing secrets.
- **Permissions prompt.** Electron grants mic access via `session.setPermissionRequestHandler(...)`. Default **deny**, prompt on first use. Remember the answer per project.
- **Visible recording indicator** must always be on-screen while recording (red dot in the header and pulse on the mic button). Never record silently.
- **Consent-gated wake-word.** If wake-word is enabled, require an extra confirmation dialog ("This will run a background listener on your mic") and remember the choice.

---

## 9. Performance considerations

| Concern | Mitigation |
|--------|-----------|
| STT model cold-start (1-3 s the first time) | Warm the model in `lifespan()` when `VOICE_ENABLED=true` |
| TTS first-chunk latency | Start synthesis per-sentence, not per-response |
| Barge-in (user talks over JARVIS) | Set `tts_interrupt_evt`, drain the current TTS generator, ignore remaining chunks |
| Echo cancellation | Rely on `getUserMedia({ audio: { echoCancellation: true } })`; do not route TTS through speakers while recording if the user has no mic array |
| CPU cost of local STT + TTS | Run both on a dedicated executor; never block the WS handler thread |
| Audio chunk size | 20 ms frames (320 samples @ 16 kHz) balance latency vs WS overhead |
| Buffering stability | Use `ScriptProcessorNode` fallback only; prefer `AudioWorklet` once implemented |

---

## 10. Implementation order

Don't build voice before Phase 1 ships. Sequence when it does start:

1. **STT local path (push-to-talk, no streaming).** Ship a working typed→spoken flow first. Use faster-whisper base.en, full-utterance transcription.
2. **STT streaming.** Add partial transcripts.
3. **TTS local path (Piper).** Speak the full response once it's done streaming.
4. **TTS streaming + sentence chunking.** First audio inside 300 ms.
5. **Barge-in.** Interrupt event wired end-to-end.
6. **Cloud mode STT + TTS.** Deepgram + ElevenLabs wired behind `mode === 'cloud'`.
7. **Mic button + keyboard shortcut.** UI polish.
8. **(Optional) Wake word.** Opt-in, tray indicator.

Each step merges to `main` before the next begins — voice is user-visible, regressions will be felt immediately.

---

## 11. Open questions

- Should TTS be **on by default** or **opt-in**? Default-off is safer (no surprise talking in a quiet room); default-on is more "Iron Man".
- Which voice model ships in `voices/`? Piper has ~30 English voices — pick one that sounds authoritative-neutral, not cartoony.
- Do we support multi-language input? If yes, detect language per-utterance (faster-whisper supports this) and route to matching TTS voice.
- Should voice transcripts appear in the chat as user messages the moment they're final, or only after the user presses "send"? (Current recommendation: appear immediately — matches Siri/Alexa mental model.)
- Does voice interact with the surface-card / proactive-context system? E.g., should JARVIS **speak** a surfaced bullet automatically when it appears, or only on request?

---

## 12. Dependency additions

**`requirements.txt` additions (conditional — only if `VOICE_ENABLED=true` at boot):**
```
faster-whisper==1.0.3
piper-tts==1.2.0
webrtcvad==2.0.10
deepgram-sdk==3.7.0            # cloud STT
elevenlabs==1.9.0              # cloud TTS (optional)
pvporcupine==3.0.2             # wake word (optional)
```

**`.env` additions:**
```
VOICE_ENABLED=false
WHISPER_MODEL=base.en
PIPER_VOICE=en_US-amy-medium
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=
```

Gate all voice imports behind `if os.environ.get("VOICE_ENABLED") == "true"` so the backend still starts cleanly without these dependencies installed.
