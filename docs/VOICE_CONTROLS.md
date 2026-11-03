# Voxora Voice Controls

All continuous controls use **0–100**. For centered controls, 50 is neutral; for amount controls, 0 disables the effect and 100 applies the strongest bounded effect.

| Control | Implementation | Limitation |
|---|---|---|
| Speaking speed | F5-TTS speed, 0.70×–1.30× | Not phoneme-duration editing |
| Reference conditioning guidance | F5-TTS CFG, 1–4 | Not a calibrated similarity percentage |
| Prosody variation | F5-TTS sway coefficient, −1 to +1 | Model-dependent |
| Output loudness | F5-TTS target RMS, 0.04–0.20 | Not mastering loudness |
| Pitch / register | Local pitch shift, −6 to +6 semitones | Extreme values sound artificial |
| Sentence intonation | Punctuation-aware segment pitch | Not a drawn F0 contour |
| Brightness / warmth | High-/low-frequency tone shaping | Not vocal identity editing |
| Breathiness | Filtered noise blend | Not vocal-fold simulation |
| Resonance / presence | Band-pass emphasis | Not formant tracking |
| Dynamic compression | Local saturation/compression | Not a studio mastering chain |
| Room / reverb | Short multi-tap delay | Not convolution reverb |
| Sentence spacing | 0–1000 ms silence insertion | Explicit pause markup supported |
| Marked emphasis | F5-TTS CFG on tagged spans | Only for emphasis markup |
| Mood intensity | Interpolated speed/CFG/sway preset | Approximation, not guaranteed emotion |
| Synthesis detail | F5-TTS NFE steps, 16–64 | Higher values take longer |

Script markup: [pause:500ms], [speed:0.9]...[/speed], [delivery:formal]...[/delivery], [emphasis]...[/emphasis].

The current F5-TTS backend does not expose independent neural controls for age, accent, dialect, exact phoneme duration/stress, breath placement, vocal fry, rasp, whispering, laughter/crying, emotion embeddings, formant trajectories or word-level F0 curves. Post-processing is not equivalent to those capabilities. Future adapters should evaluate instruction-controlled models (such as Qwen3-TTS voice design/instruction conditioning) and voice-conversion models only after licence, language, hardware and reproducibility review.
