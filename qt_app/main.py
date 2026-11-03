#!/usr/bin/env python3
"""Cross-platform Qt desktop shell for Voxora; inference stays in the adapter-backed worker."""
import os, sys, json, shutil, subprocess, datetime
from pathlib import Path
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
VOICES, OUTPUTS, LOGS = ROOT / "voices", ROOT / "outputs", ROOT / "logs"
for folder in (VOICES, OUTPUTS, LOGS): folder.mkdir(exist_ok=True)
PROFILE_AUDIO, PROFILE_TEXT = VOICES / "my_voice.wav", VOICES / "my_voice.txt"

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QProcess
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QTabWidget, QLabel, QPushButton, QComboBox, QSlider, QTextEdit,
    QFileDialog, QCheckBox, QProgressBar, QScrollArea, QGroupBox, QMessageBox)
from PySide6.QtMultimedia import (QMediaPlayer, QAudioOutput, QMediaDevices, QAudioInput,
    QMediaCaptureSession, QMediaRecorder, QMediaFormat)

STYLE = """
QWidget { background:#0b1118; color:#e8f0f7; font-size:13px; }
QMainWindow { background:#0b1118; }
QTabWidget::pane { border:1px solid #263b4b; border-radius:12px; }
QTabBar::tab { background:#111d28; color:#aebfce; padding:12px 22px; margin:3px; border-radius:8px; }
QTabBar::tab:selected { background:#103d39; color:#72f0cb; }
QGroupBox { border:1px solid #263b4b; border-radius:12px; margin-top:12px; padding:16px; font-weight:700; }
QGroupBox::title { subcontrol-origin:margin; left:14px; padding:0 6px; color:#72e8c7; }
QPushButton { background:#1a2a37; border:1px solid #2d4353; border-radius:9px; padding:10px 14px; }
QPushButton:hover { background:#233a4b; }
QPushButton:disabled { color:#627483; }
QPushButton#primary { background:#0f9b78; color:white; font-weight:800; }
QComboBox, QTextEdit { background:#0a141e; border:1px solid #2a4050; border-radius:8px; padding:9px; }
QSlider::groove:horizontal { height:5px; background:#263b4b; border-radius:3px; }
QSlider::sub-page:horizontal { background:#24b98e; border-radius:3px; }
QSlider::handle:horizontal { background:#e5fff7; border:2px solid #1ab88d; width:14px; margin:-6px 0; border-radius:8px; }
QLabel#muted { color:#91a9b9; }
QProgressBar { background:#172a38; border:0; border-radius:4px; height:8px; text-align:center; }
QProgressBar::chunk { background:#24b98e; border-radius:4px; }
"""

class BackendWorker(QThread):
    event = Signal(dict)
    done = Signal(dict)
    def __init__(self, payload): super().__init__(); self.payload=payload
    def run(self):
        cmd=[sys.executable, str(ROOT/'native_backend.py')]
        try:
            p=subprocess.Popen(cmd,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            p.stdin.write(json.dumps(self.payload,ensure_ascii=False)); p.stdin.close()
            events=[]; diagnostics=[]
            for line in p.stdout:
                try:
                    obj=json.loads(line.strip())
                    if isinstance(obj,dict) and 'stage' in obj: events.append(obj); self.event.emit(obj)
                    else: diagnostics.append(line)
                except json.JSONDecodeError: diagnostics.append(line)
            code=p.wait()
            if diagnostics: (LOGS/'last-generation.log').write_text(''.join(diagnostics)[-30000:],encoding='utf-8')
            result=events[-1] if events else {'stage':'error','message':'Inference worker returned no result; inspect logs/last-generation.log.'}
            if code and result.get('stage')!='error': result={'stage':'error','message':'Inference failed; inspect logs/last-generation.log.'}
            self.done.emit(result)
        except Exception as exc: self.done.emit({'stage':'error','message':str(exc)})

class VoxoraWindow(QMainWindow):
    CONTROL_SPEC = [
        ('speed','Speaking speed',50,'Slow to fast; 50 is natural'),
        ('voice_adherence','Reference conditioning guidance',50,'F5-TTS classifier-free guidance mapping'),
        ('variation','Prosody / rhythm variation',0,'F5-TTS sway sampling'),
        ('loudness','Output loudness',38,'Normalized output RMS target'),
        ('pitch','Pitch / register',50,'Post-generation pitch shift, -6 to +6 semitones'),
        ('intonation','Sentence intonation',35,'Punctuation-aware segment inflection'),
        ('brightness','Brightness',50,'High-frequency tone shaping'),
        ('warmth','Warmth / low-mid body',50,'Low-frequency tone shaping'),
        ('breathiness','Breathiness',0,'Subtle noise blend; not neural vocal-fold control'),
        ('resonance','Resonance / presence',50,'Vocal presence band emphasis'),
        ('compression','Dynamic compression',0,'Peak-to-average dynamic control'),
        ('reverb','Room / reverb',0,'Local multi-tap room response'),
        ('sentence_pause','Sentence spacing',18,'Automatic silence between sentences'),
        ('emphasis','Marked emphasis intensity',50,'Strength for [emphasis] markup'),
        ('mood_intensity','Mood intensity',50,'Scales selected mood preset'),
        ('quality','Synthesis detail / quality',50,'F5-TTS denoising steps; higher is slower')]
    def __init__(self):
        super().__init__(); self.setWindowTitle('Voxora · Private Voice Studio'); self.resize(1420,960)
        self.reference=str(PROFILE_AUDIO) if PROFILE_AUDIO.exists() else ''
        self.output=''; self.worker=None; self.recorder=None
        self.player=QMediaPlayer(self); self.audio=QAudioOutput(self); self.player.setAudioOutput(self.audio)
        self.capture_session=QMediaCaptureSession(self); self.audio_input=QAudioInput()
        self.media_recorder=QMediaRecorder(self); self.capture_session.setAudioInput(self.audio_input)
        self.capture_session.setRecorder(self.media_recorder)
        self.setStyleSheet(STYLE)
        central=QWidget(); root=QVBoxLayout(central); root.setContentsMargins(22,18,22,18)
        head=QHBoxLayout(); brand=QLabel('VOXORA'); brand.setStyleSheet('font-size:25px;font-weight:900;color:#72f0cb;')
        head.addWidget(brand); head.addWidget(QLabel('LOCAL · PRIVATE · MODEL-ADAPTER ARCHITECTURE')); head.addStretch()
        root.addLayout(head)
        self.tabs=QTabWidget(); root.addWidget(self.tabs,1)
        self.build_create(); self.build_voices(); self.build_library(); self.build_settings()
        footer=QHBoxLayout(); self.status=QLabel('Ready · inference runs locally'); self.status.setObjectName('muted')
        self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); footer.addWidget(self.status,1); footer.addWidget(self.progress)
        root.addLayout(footer); self.setCentralWidget(central)
        self.load_saved_profile()

    def card(self,title,layout):
        box=QGroupBox(title); box.setLayout(layout); return box
    def build_create(self):
        page=QWidget(); outer=QVBoxLayout(page); outer.setSpacing(12)
        top=QHBoxLayout(); self.language=QComboBox(); self.language.addItems(['English','Hindi','Kannada'])
        self.preset=QComboBox(); self.preset.addItems(['Natural','Professional','Formal','Conversational','Expressive'])
        self.mood=QComboBox(); self.mood.addItems(['Neutral','Calm','Upbeat','Confident','Warm','Dramatic'])
        top.addWidget(QLabel('Language')); top.addWidget(self.language); top.addWidget(QLabel('Delivery')); top.addWidget(self.preset); top.addWidget(QLabel('Mood')); top.addWidget(self.mood); outer.addLayout(top)
        split=QHBoxLayout()
        voice=QVBoxLayout(); self.ref_label=QLabel(Path(self.reference).name if self.reference else 'No reference recording selected'); self.ref_label.setWordWrap(True)
        row=QHBoxLayout(); pick=QPushButton('Choose recording'); pick.clicked.connect(self.choose_audio); row.addWidget(pick)
        self.record_btn=QPushButton('Record microphone'); self.record_btn.clicked.connect(self.toggle_recording); row.addWidget(self.record_btn)
        voice.addLayout(row); voice.addWidget(self.ref_label); voice.addWidget(QLabel('Exact recording transcript'))
        self.transcript=QTextEdit(); self.transcript.setPlaceholderText('Type exactly what is spoken in your recording…'); self.transcript.setMaximumHeight(120)
        if PROFILE_TEXT.exists(): self.transcript.setPlainText(PROFILE_TEXT.read_text(encoding='utf-8'))
        voice.addWidget(self.transcript); self.save_profile=QCheckBox('Save as default voice profile'); voice.addWidget(self.save_profile)
        self.analysis=QLabel('Speaker acoustic analysis will appear here.'); self.analysis.setWordWrap(True); voice.addWidget(self.analysis)
        analyze=QPushButton('Analyze speaker profile'); analyze.clicked.connect(self.analyze_profile); voice.addWidget(analyze); voice.addStretch()
        script=QVBoxLayout(); script.addWidget(QLabel('Script to synthesize'))
        self.script=QTextEdit(); self.script.setPlaceholderText('Enter the text to speak…'); self.script.setPlainText('This is a test of the Voxora cross-platform desktop application.')
        script.addWidget(self.script,1)
        tools=QHBoxLayout()
        for title,tag in [('Pause 500 ms','[pause:500ms]'),('Emphasis','[emphasis][/emphasis]'),('Slower','[speed:0.9][/speed]'),('Formal delivery','[delivery:formal][/delivery]')]:
            b=QPushButton(title); b.clicked.connect(lambda checked=False,t=tag:self.script.insertPlainText(t)); tools.addWidget(b)
        script.addLayout(tools); script.addWidget(QLabel('Markup: [pause:500ms], [speed:0.9]…[/speed], [delivery:formal]…[/delivery], [emphasis]…[/emphasis]'))
        split.addWidget(self.card('01 · Reference voice',voice),1); split.addWidget(self.card('02 · Script editor',script),1); outer.addLayout(split,2)
        controls=QGridLayout(); self.sliders={}
        for i,(key,title,default,hint) in enumerate(self.CONTROL_SPEC):
            row,col=divmod(i,2); col*=3
            name=QLabel(title); slider=QSlider(Qt.Orientation.Horizontal); slider.setRange(0,100); slider.setValue(default); slider.setToolTip(hint)
            value=QLabel(f'{default}/100'); slider.valueChanged.connect(lambda v,l=value:l.setText(f'{v}/100'))
            controls.addWidget(name,row,col); controls.addWidget(slider,row,col+1); controls.addWidget(value,row,col+2); self.sliders[key]=slider
        outer.addWidget(self.card('03 · Continuous voice controls (0–100)',controls),2)
        actions=QHBoxLayout(); self.generate_btn=QPushButton('Generate speech'); self.generate_btn.setObjectName('primary'); self.generate_btn.clicked.connect(self.generate)
        self.play_btn=QPushButton('Play / pause'); self.play_btn.clicked.connect(self.play_output); self.play_btn.setEnabled(False)
        self.export_btn=QPushButton('Export WAV'); self.export_btn.clicked.connect(self.export_output); self.export_btn.setEnabled(False)
        actions.addStretch(); actions.addWidget(self.generate_btn); actions.addWidget(self.play_btn); actions.addWidget(self.export_btn); outer.addLayout(actions)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page); self.tabs.addTab(scroll,'Create')

    def build_voices(self):
        page=QWidget(); lay=QVBoxLayout(page); self.profile_info=QLabel(''); self.profile_info.setWordWrap(True); lay.addWidget(self.profile_info)
        b=QPushButton('Use saved recording'); b.clicked.connect(self.use_saved_profile); lay.addWidget(b); lay.addStretch(); self.tabs.addTab(page,'My voices')
    def build_library(self):
        page=QWidget(); lay=QVBoxLayout(page); self.library=QVBoxLayout(); lay.addLayout(self.library); refresh=QPushButton('Refresh history'); refresh.clicked.connect(self.refresh_library); lay.addWidget(refresh); lay.addStretch(); self.tabs.addTab(page,'Exports & history'); self.refresh_library()
    def build_settings(self):
        from model_adapters import list_adapters
        page=QWidget(); lay=QVBoxLayout(page)
        lay.addWidget(QLabel('Model adapters'))
        for adapter in list_adapters():
            d=adapter.descriptor; c=d.capabilities
            text=f'{d.name} · {d.version}\nLanguages: {", ".join(c.languages)}\nVoice cloning: {c.voice_cloning} · Voice design: {c.voice_design} · Instruction control: {c.instruction_control}\n{chr(10).join(c.notes)}\nLicense: {d.license}'
            item=QLabel(text); item.setWordWrap(True); lay.addWidget(item)
        privacy=QLabel('Privacy: inference is local/offline. Model weights have separate licenses; see MODEL-LICENSES.md. The current UI is Qt/PySide and designed for Linux, Windows and macOS, but native packaging/audio-device validation remains platform-specific.')
        privacy.setWordWrap(True); lay.addWidget(privacy); lay.addStretch(); self.tabs.addTab(page,'Settings & models')

    def choose_audio(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose reference audio',str(VOICES),'Audio (*.wav *.mp3 *.flac *.ogg *.m4a *.aac)')
        if path: self.reference=path; self.ref_label.setText(path)
    def toggle_recording(self):
        if self.media_recorder.recorderState() == QMediaRecorder.RecorderState.RecordingState:
            self.media_recorder.stop()
            self.reference=self.recording_path
            self.ref_label.setText(self.reference + ' · recording saved')
            self.record_btn.setText('Record microphone')
            self.status.setText('Recording stopped. Enter the exact transcript.')
            return
        device=QMediaDevices.defaultAudioInput()
        if device.isNull():
            QMessageBox.information(self,'No microphone','No default microphone was detected. Choose an existing audio recording instead.')
            return
        self.audio_input.setDevice(device)
        self.recording_path=str(VOICES/f'recording_{datetime.datetime.now():%Y%m%d_%H%M%S}.wav')
        self.media_recorder.setOutputLocation(QUrl.fromLocalFile(self.recording_path))
        fmt=QMediaFormat(); fmt.setFileFormat(QMediaFormat.FileFormat.Wave)
        self.media_recorder.setMediaFormat(fmt)
        self.media_recorder.record()
        if self.media_recorder.error()!=QMediaRecorder.Error.NoError:
            self.status.setText('Microphone recording failed: '+self.media_recorder.errorString())
            return
        self.record_btn.setText('Stop recording'); self.ref_label.setText('Recording… click Stop recording when finished.')
    def load_saved_profile(self):
        self.refresh_profile()
    def use_saved_profile(self):
        if PROFILE_AUDIO.exists(): self.reference=str(PROFILE_AUDIO); self.ref_label.setText(self.reference); self.transcript.setPlainText(PROFILE_TEXT.read_text(encoding='utf-8') if PROFILE_TEXT.exists() else '')
        else: self.status.setText('No saved voice profile yet.')
    def refresh_profile(self):
        if PROFILE_AUDIO.exists(): self.profile_info.setText(f'Saved recording: {PROFILE_AUDIO.name}\nTranscript: {"available" if PROFILE_TEXT.exists() else "missing"}')
        else: self.profile_info.setText('No default voice profile saved yet.')
    def payload(self, action='generate'):
        v={k:s.value()/100 for k,s in self.sliders.items()}
        settings={'speed':.70+v['speed']*.60,'guidance':1+v['voice_adherence']*3,'variation':-1+v['variation']*2,'loudness':.04+v['loudness']*.16,
          'mood':['neutral','calm','upbeat','confident','warm','dramatic'][self.mood.currentIndex()], 'pitch_shift':-6+v['pitch']*12,
          'intonation':v['intonation'],'brightness':-1+v['brightness']*2,'warmth':-1+v['warmth']*2,'breathiness':v['breathiness'],
          'resonance':-1+v['resonance']*2,'compression':v['compression'],'reverb':v['reverb'],'sentence_pause_ms':int(self.sliders['sentence_pause'].value()*10),
          'emphasis_strength':v['emphasis'],'mood_intensity':v['mood_intensity'],'nfe_step':int(16+self.sliders['quality'].value()*.48)}
        return {'action':action,'language':self.language.currentText(),'text':self.script.toPlainText().strip(),'transcript':self.transcript.toPlainText().strip(),
          'reference_audio':self.reference,'save_profile':self.save_profile.isChecked(),'settings':settings}
    def generate(self):
        if not self.reference or not Path(self.reference).is_file(): self.status.setText('Choose or record a reference voice first.'); return
        if not self.transcript.toPlainText().strip(): self.status.setText('Enter the exact recording transcript.'); return
        if not self.script.toPlainText().strip(): self.status.setText('Enter text to synthesize.'); return
        self.start_worker(self.payload())
    def analyze_profile(self):
        if not self.reference or not Path(self.reference).is_file(): self.status.setText('Choose a reference recording first.'); return
        p=self.payload('analyze'); p['text']=''; p['transcript']=self.transcript.toPlainText().strip(); self.start_worker(p)
    def start_worker(self,payload):
        if self.worker and self.worker.isRunning(): return
        self.generate_btn.setEnabled(False); self.progress.show(); self.status.setText('Starting local inference…')
        self.worker=BackendWorker(payload); self.worker.event.connect(lambda e:self.status.setText(e.get('message','Working…'))); self.worker.done.connect(self.finish_worker); self.worker.start()
    def finish_worker(self,result):
        self.generate_btn.setEnabled(True); self.progress.hide()
        if result.get('stage')=='complete' and result.get('output'):
            self.output=result['output']; self.play_btn.setEnabled(True); self.export_btn.setEnabled(True); self.status.setText('Speech generated successfully · saved locally'); self.refresh_library()
            analysis=result.get('reference_analysis',{}); self.analysis.setText(f"Reference: {analysis.get('duration_seconds','n/a')}s · pitch {analysis.get('pitch_median_hz','n/a')} Hz · speech rate {analysis.get('speech_rate_wpm_estimate','n/a')} WPM")
        elif result.get('stage')=='complete':
            a=result.get('analysis',{}); self.analysis.setText(json.dumps(a,indent=2)); self.status.setText('Speaker analysis complete and saved locally.'); self.refresh_profile()
        else: self.status.setText('Error: '+result.get('message','Unknown inference error'))
    def play_output(self):
        if not self.output: return
        if self.player.source().isEmpty() or self.player.source().toLocalFile()!=self.output: self.player.setSource(QUrl.fromLocalFile(self.output))
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState: self.player.pause()
        else: self.player.play()
    def export_output(self):
        if not self.output: return
        path,_=QFileDialog.getSaveFileName(self,'Export generated audio',Path(self.output).name,'WAV (*.wav)')
        if path: shutil.copy2(self.output,path); self.status.setText('Exported '+path)
    def refresh_library(self):
        while self.library.count():
            item=self.library.takeAt(0); w=item.widget(); w.deleteLater() if w else None
        for path in sorted(OUTPUTS.glob('*.wav'),key=lambda p:p.stat().st_mtime,reverse=True)[:50]:
            b=QPushButton(f'{path.name}   ·   {datetime.datetime.fromtimestamp(path.stat().st_mtime):%d %b %Y %H:%M}')
            b.clicked.connect(lambda checked=False,p=path:self.open_library_file(p)); self.library.addWidget(b)
    def open_library_file(self,path): self.output=str(path); self.play_btn.setEnabled(True); self.export_btn.setEnabled(True); self.tabs.setCurrentIndex(0); self.play_output()
    def closeEvent(self,event):
        if self.media_recorder.recorderState()==QMediaRecorder.RecorderState.RecordingState: self.media_recorder.stop()
        self.player.stop(); super().closeEvent(event)

def main():
    app=QApplication(sys.argv); app.setApplicationName('Voxora'); app.setOrganizationName('PSP-YN')
    win=VoxoraWindow(); win.show(); return app.exec()
if __name__=='__main__': raise SystemExit(main())
