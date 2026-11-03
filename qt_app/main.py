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

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QTabWidget, QLabel, QPushButton, QComboBox, QSlider, QTextEdit,
    QFileDialog, QCheckBox, QProgressBar, QScrollArea, QGroupBox, QMessageBox, QFrame)
if os.environ.get("VOXORA_HEADLESS_TEST") != "1":
    from PySide6.QtMultimedia import (QMediaPlayer, QAudioOutput, QMediaDevices, QAudioInput,
        QMediaCaptureSession, QMediaRecorder, QMediaFormat)
else:
    QMediaPlayer = QAudioOutput = QMediaDevices = QAudioInput = None
    QMediaCaptureSession = QMediaRecorder = QMediaFormat = None

STYLE = """
QWidget { background:#0b1118; color:#e8f0f7; font-size:13px; }
QMainWindow { background:#0b1118; }
QTabWidget::pane { border:1px solid #263b4b; border-radius:12px; top:-1px; }
QTabBar::tab { background:#111d28; color:#aebfce; padding:12px 22px; margin:3px 5px 3px 0; border-radius:8px; min-width:105px; }
QTabBar::tab:selected { background:#103d39; color:#72f0cb; }
QGroupBox { border:1px solid #263b4b; border-radius:12px; margin-top:12px; padding:16px; font-weight:700; }
QGroupBox::title { subcontrol-origin:margin; left:14px; padding:0 6px; color:#72e8c7; }
QPushButton { background:#1a2a37; border:1px solid #2d4353; border-radius:9px; padding:10px 14px; }
QPushButton:hover { background:#233a4b; }
QPushButton:disabled { color:#627483; }
QPushButton#primary { background:#0f9b78; color:white; font-weight:800; }
QComboBox, QTextEdit { background:#0a141e; border:1px solid #2a4050; border-radius:8px; padding:9px; selection-background-color:#137e69; }
QComboBox:focus, QTextEdit:focus { border:1px solid #24b98e; }
QPushButton:focus, QSlider:focus { outline:1px solid #72f0cb; }
QLabel#pageTitle { font-size:20px; font-weight:800; color:#eef7fb; }
QLabel#muted { color:#91a9b9; }
QFrame#separator { background:#263b4b; max-height:1px; }
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
        ('variation','Prosody / rhythm variation',50,'F5-TTS sway sampling'),
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
        super().__init__(); self.setWindowTitle('Voxora · Local Voice Studio'); self.resize(1360,900); self.setMinimumSize(1080,720)
        self.reference=str(PROFILE_AUDIO) if PROFILE_AUDIO.exists() else ''
        self.output=''; self.worker=None; self.recorder=None
        self.player=None; self.audio=None; self.capture_session=None; self.audio_input=None; self.media_recorder=None
        # Headless widget tests do not initialize native audio device backends.
        if os.environ.get("VOXORA_HEADLESS_TEST") != "1":
            self.player=QMediaPlayer(self); self.audio=QAudioOutput(self); self.player.setAudioOutput(self.audio)
            self.capture_session=QMediaCaptureSession(self); self.audio_input=QAudioInput()
            self.media_recorder=QMediaRecorder(self); self.capture_session.setAudioInput(self.audio_input)
            self.capture_session.setRecorder(self.media_recorder)
            self.media_recorder.errorOccurred.connect(lambda _error,message:self.status.setText('Recording error: '+message) if hasattr(self,'status') else None)
            self.player.errorOccurred.connect(lambda _error:self.status.setText('Playback error: '+self.player.errorString()) if hasattr(self,'status') else None)
        self.setStyleSheet(STYLE)
        central=QWidget(); root=QVBoxLayout(central); root.setContentsMargins(22,18,22,18)
        head=QHBoxLayout(); brand=QLabel('Voxora'); brand.setStyleSheet('font-size:27px;font-weight:900;color:#72f0cb;')
        identity=QVBoxLayout(); identity.setSpacing(0); identity.addWidget(brand); sub=QLabel('Local voice studio'); sub.setObjectName('muted'); identity.addWidget(sub)
        head.addLayout(identity); head.addStretch(); privacy=QLabel('ON-DEVICE PROCESSING'); privacy.setStyleSheet('color:#72f0cb;font-weight:700;padding:7px 12px;border:1px solid #24594f;border-radius:12px;'); head.addWidget(privacy)
        root.addLayout(head)
        self.tabs=QTabWidget(); root.addWidget(self.tabs,1)
        self.build_create(); self.build_controls(); self.build_voices(); self.build_library(); self.build_settings()
        footer=QHBoxLayout(); self.status=QLabel('Ready · inference runs locally'); self.status.setObjectName('muted')
        self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); footer.addWidget(self.status,1); footer.addWidget(self.progress)
        root.addLayout(footer); self.setCentralWidget(central)
        self.load_saved_profile()

    def card(self,title,layout):
        box=QGroupBox(title); box.setLayout(layout); return box
    def page_heading(self, title, subtitle, layout):
        heading=QLabel(title); heading.setObjectName('pageTitle'); layout.addWidget(heading)
        detail=QLabel(subtitle); detail.setObjectName('muted'); detail.setWordWrap(True); layout.addWidget(detail)

    def build_create(self):
        page=QWidget(); outer=QVBoxLayout(page); outer.setContentsMargins(20,18,20,18); outer.setSpacing(14)
        self.page_heading('Create speech','Choose a reference voice, write your script and generate speech privately on this device.',outer)
        top=QHBoxLayout(); top.setSpacing(12)
        self.language=QComboBox(); self.language.addItems(['English','Hindi','Kannada']); self.language.setAccessibleName('Output language')
        self.preset=QComboBox(); self.preset.addItems(['Natural','Professional','Formal','Conversational','Expressive']); self.preset.setAccessibleName('Delivery preset'); self.preset.currentIndexChanged.connect(self.apply_style_preset)
        self.mood=QComboBox(); self.mood.addItems(['Neutral','Calm','Upbeat','Confident','Warm','Dramatic']); self.mood.setAccessibleName('Mood preset')
        for label_text,widget in [('Language',self.language),('Delivery',self.preset),('Mood',self.mood)]:
            col=QVBoxLayout(); col.setSpacing(5); lbl=QLabel(label_text); lbl.setObjectName('muted'); col.addWidget(lbl); col.addWidget(widget); top.addLayout(col,1)
        outer.addLayout(top)
        split=QHBoxLayout(); split.setSpacing(14)
        voice=QVBoxLayout(); voice.setSpacing(10)
        self.ref_label=QLabel(Path(self.reference).name if self.reference else 'No reference recording selected'); self.ref_label.setWordWrap(True); self.ref_label.setObjectName('muted')
        row=QHBoxLayout(); pick=QPushButton('Import audio'); pick.clicked.connect(self.choose_audio); row.addWidget(pick)
        self.record_btn=QPushButton('Record microphone'); self.record_btn.clicked.connect(self.toggle_recording); row.addWidget(self.record_btn)
        voice.addLayout(row); voice.addWidget(self.ref_label)
        voice.addWidget(QLabel('Exact recording transcript'))
        self.transcript=QTextEdit(); self.transcript.setPlaceholderText('Enter exactly what is spoken in your reference recording…'); self.transcript.setMaximumHeight(140); self.transcript.setAccessibleName('Reference recording transcript')
        if PROFILE_TEXT.exists(): self.transcript.setPlainText(PROFILE_TEXT.read_text(encoding='utf-8'))
        voice.addWidget(self.transcript)
        self.save_profile=QCheckBox('Save as my default voice profile'); voice.addWidget(self.save_profile)
        analyze=QPushButton('Analyze reference voice'); analyze.clicked.connect(self.analyze_profile); voice.addWidget(analyze); self.analyze_btn=analyze
        self.analysis=QLabel('Acoustic analysis will appear here after analysis or generation.'); self.analysis.setWordWrap(True); self.analysis.setObjectName('muted'); voice.addWidget(self.analysis)
        self.comparison=QLabel('Reference comparison will appear after generation.'); self.comparison.setWordWrap(True); self.comparison.setObjectName('muted'); voice.addWidget(self.comparison); voice.addStretch()
        script=QVBoxLayout(); script.setSpacing(9); script.addWidget(QLabel('Script'))
        self.script=QTextEdit(); self.script.setPlaceholderText('Write or paste the words you want spoken…'); self.script.setAccessibleName('Speech script'); self.script.setPlainText('This is a test of the Voxora desktop application.')
        script.addWidget(self.script,1)
        tools=QHBoxLayout(); tools.setSpacing(6)
        for title,callback in [('Pause',lambda:self.script.insertPlainText('[pause:500ms]')),('Emphasize selection',self.wrap_selection_emphasis),('Slower selection',self.wrap_selection_speed),('Apply delivery',self.wrap_selection_delivery)]:
            b=QPushButton(title); b.clicked.connect(callback); tools.addWidget(b)
        script.addLayout(tools)
        markup=QLabel('Markup: [pause:500ms] · [speed:0.9]…[/speed] · [delivery:formal]…[/delivery] · [emphasis]…[/emphasis]'); markup.setWordWrap(True); markup.setObjectName('muted'); script.addWidget(markup)
        self.script_count=QLabel('0 characters'); self.script_count.setObjectName('muted'); self.script_count.setAlignment(Qt.AlignmentFlag.AlignRight); script.addWidget(self.script_count)
        self.script.textChanged.connect(lambda:self.script_count.setText(f'{len(self.script.toPlainText()):,} characters'))
        self.script_count.setText(f'{len(self.script.toPlainText()):,} characters')
        split.addWidget(self.card('Reference voice',voice),1); split.addWidget(self.card('Speech script',script),1); outer.addLayout(split,1)
        actions=QHBoxLayout(); self.generate_btn=QPushButton('Generate speech'); self.generate_btn.setObjectName('primary'); self.generate_btn.clicked.connect(self.generate)
        self.play_btn=QPushButton('Play preview'); self.play_btn.clicked.connect(self.play_output); self.play_btn.setEnabled(False)
        self.export_btn=QPushButton('Export WAV'); self.export_btn.clicked.connect(self.export_output); self.export_btn.setEnabled(False)
        actions.addWidget(QLabel('Fine-tune voice settings in the Voice controls tab.')); actions.addStretch(); actions.addWidget(self.generate_btn); actions.addWidget(self.play_btn); actions.addWidget(self.export_btn); outer.addLayout(actions)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page); self.tabs.addTab(scroll,'Studio')

    def build_controls(self):
        page=QWidget(); outer=QVBoxLayout(page); outer.setContentsMargins(20,18,20,18); outer.setSpacing(12)
        self.page_heading('Voice controls','All controls are continuous 0–100 values. The tooltip explains the actual mapping and its limits.',outer)
        intro=QLabel('50 is neutral for centered controls. For amount controls, 0 disables the effect. These are bounded audio/model parameters, not a speaker-identity guarantee.'); intro.setWordWrap(True); intro.setObjectName('muted'); outer.addWidget(intro)
        controls=QGridLayout(); controls.setHorizontalSpacing(22); controls.setVerticalSpacing(13); self.sliders={}; self.control_values={}
        for i,(key,title,default,hint) in enumerate(self.CONTROL_SPEC):
            row,col=divmod(i,2); col*=3
            name=QLabel(title); slider=QSlider(Qt.Orientation.Horizontal); slider.setRange(0,100); slider.setValue(default); slider.setToolTip(hint); slider.setAccessibleName(title); slider.setAccessibleDescription(hint)
            value=QLabel(f'{default}/100'); value.setMinimumWidth(48); value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); value.setObjectName('muted')
            slider.valueChanged.connect(lambda v,l=value:l.setText(f'{v}/100'))
            controls.addWidget(name,row,col); controls.addWidget(slider,row,col+1); controls.addWidget(value,row,col+2); self.sliders[key]=slider; self.control_values[key]=value
        outer.addWidget(self.card('Fine controls',controls),1)
        foot=QHBoxLayout(); note=QLabel('Model-dependent controls are identified in their tooltips. Effects such as pitch shift, warmth and reverb are post-processing.'); note.setWordWrap(True); note.setObjectName('muted'); foot.addWidget(note,1)
        reset=QPushButton('Reset controls'); reset.clicked.connect(self.reset_controls); foot.addWidget(reset); outer.addLayout(foot)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page); self.tabs.addTab(scroll,'Voice controls')

    def reset_controls(self):
        for key,title,default,hint in self.CONTROL_SPEC: self.sliders[key].setValue(default)
        self.preset.setCurrentIndex(0); self.mood.setCurrentIndex(0)
        self.status.setText('Voice controls reset to defaults.')

    def apply_style_preset(self):
        presets={0:(50,50,50),1:(44,25,55),2:(37,15,58),3:(57,35,45),4:(50,65,40)}
        speed,variation,guidance=presets.get(self.preset.currentIndex(),presets[0])
        self.sliders['speed'].setValue(speed); self.sliders['variation'].setValue(variation); self.sliders['voice_adherence'].setValue(guidance)

    def wrap_selection(self, opening, closing, empty_message):
        cursor=self.script.textCursor()
        if not cursor.hasSelection(): self.status.setText(empty_message); return
        selected=cursor.selectedText().replace('\u2029','\n')
        cursor.insertText(opening+selected+closing)

    def wrap_selection_emphasis(self): self.wrap_selection('[emphasis]','[/emphasis]','Select script text before applying emphasis.')
    def wrap_selection_speed(self): self.wrap_selection('[speed:0.90]','[/speed]','Select script text before changing its pace.')
    def wrap_selection_delivery(self):
        style=['natural','professional','formal','conversational','expressive'][self.preset.currentIndex()]
        self.wrap_selection(f'[delivery:{style}]','[/delivery]','Select script text before applying a delivery style.')

    def build_voices(self):
        page=QWidget(); lay=QVBoxLayout(page); lay.setContentsMargins(20,18,20,18); lay.setSpacing(12)
        self.page_heading('My voice','Manage the default reference recording and transcript used for voice cloning.',lay)
        self.profile_info=QLabel(''); self.profile_info.setWordWrap(True); self.profile_info.setObjectName('muted'); lay.addWidget(self.card('Default voice profile',self._label_layout(self.profile_info)))
        row=QHBoxLayout(); b=QPushButton('Use saved recording'); b.clicked.connect(self.use_saved_profile); row.addWidget(b)
        choose=QPushButton('Choose a different recording'); choose.clicked.connect(self.choose_audio); row.addWidget(choose); row.addStretch(); lay.addLayout(row)
        hint=QLabel('Recommended reference: a clean 5–12 second recording in a quiet room, with an exact transcript. Longer recordings are analyzed, but the current F5-TTS conditioning segment is limited.'); hint.setWordWrap(True); hint.setObjectName('muted'); lay.addWidget(hint); lay.addStretch(); self.tabs.addTab(page,'My voice')

    def build_library(self):
        page=QWidget(); lay=QVBoxLayout(page); lay.setContentsMargins(20,18,20,18); lay.setSpacing(12)
        self.page_heading('Exports & history','Generated audio files stored locally on this computer.',lay)
        row=QHBoxLayout(); row.addStretch(); refresh=QPushButton('Refresh'); refresh.clicked.connect(self.refresh_library); row.addWidget(refresh); lay.addLayout(row)
        history=QScrollArea(); history.setWidgetResizable(True); history_content=QWidget(); self.library=QVBoxLayout(history_content); self.library.setSpacing(8); history.setWidget(history_content); lay.addWidget(history,1); self.tabs.addTab(page,'Library'); self.refresh_library()

    def build_settings(self):
        from model_adapters import list_adapters
        page=QWidget(); lay=QVBoxLayout(page); lay.setContentsMargins(20,18,20,18); lay.setSpacing(12)
        self.page_heading('Settings & models','Installed speech engines, supported capabilities, privacy and licensing.',lay)
        self.model_layout=QVBoxLayout(); self.model_layout.setSpacing(10)
        for adapter in list_adapters():
            d=adapter.descriptor; c=d.capabilities
            text=f'{d.name} · {d.version}\nLanguages: {", ".join(c.languages)}\nVoice cloning: {"Yes" if c.voice_cloning else "No"} · Voice design: {"Yes" if c.voice_design else "No"} · Instruction control: {"Yes" if c.instruction_control else "No"}\n'+'\n'.join(c.notes)+f'\nWeights/license: {d.license}'
            item=QLabel(text); item.setWordWrap(True); item.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); self.model_layout.addWidget(self.card(d.name,self._label_layout(item)))
        lay.addLayout(self.model_layout)
        privacy=QLabel('Inference runs locally. The application does not send reference recordings or generated speech to a cloud service. Model downloads and updates require internet access. Model weights have separate licenses; review MODEL-LICENSES.md before commercial use or redistribution.'); privacy.setWordWrap(True); privacy.setObjectName('muted'); lay.addWidget(privacy)
        platform=QLabel('Platform status: Linux is the currently tested desktop platform. Windows and macOS are migration targets, not validated releases. See docs/PLATFORM_SUPPORT.md.'); platform.setWordWrap(True); platform.setObjectName('muted'); lay.addWidget(platform); lay.addStretch(); self.tabs.addTab(page,'Settings')

    def _label_layout(self,label):
        layout=QVBoxLayout(); layout.addWidget(label); return layout

    def choose_audio(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose reference audio',str(VOICES),'Audio (*.wav *.mp3 *.flac *.ogg *.m4a *.aac)')
        if path:
            self.reference=path; self.ref_label.setText(Path(path).name); self.status.setText('Reference recording selected.')
            if self.tabs.currentIndex()==2: self.tabs.setCurrentIndex(0)
    def toggle_recording(self):
        if self.media_recorder is None:
            self.status.setText("Audio capture is disabled in headless test mode."); return
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
        self.record_btn.setText('Stop recording'); self.ref_label.setText('Recording… click Stop recording when finished.'); self.status.setText('Recording from the selected microphone.')
    def load_saved_profile(self):
        self.refresh_profile()
    def use_saved_profile(self):
        if PROFILE_AUDIO.exists():
            self.reference=str(PROFILE_AUDIO); self.ref_label.setText(PROFILE_AUDIO.name); self.transcript.setPlainText(PROFILE_TEXT.read_text(encoding='utf-8') if PROFILE_TEXT.exists() else ''); self.tabs.setCurrentIndex(0); self.status.setText('Saved voice profile loaded.')
        else: self.status.setText('No saved voice profile yet.')
    def refresh_profile(self):
        if not hasattr(self,'profile_info'): return
        if PROFILE_AUDIO.exists():
            try:
                import wave
                with wave.open(str(PROFILE_AUDIO),'rb') as w: duration=w.getnframes()/float(w.getframerate())
                profile_file=VOICES/'speaker_profile.json'; analyzed='Analyzed' if profile_file.exists() else 'Not analyzed yet'
                self.profile_info.setText(f'{PROFILE_AUDIO.name} · {duration:.1f} seconds\nTranscript: {"available" if PROFILE_TEXT.exists() else "missing"} · Acoustic profile: {analyzed}')
            except Exception: self.profile_info.setText('Saved recording found.')
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
        p=self.payload('analyze'); p['text']=''; p['transcript']=self.transcript.toPlainText().strip(); p['save_profile']=True; self.start_worker(p)
    def start_worker(self,payload):
        if self.worker and self.worker.isRunning(): return
        self.generate_btn.setEnabled(False); self.analyze_btn.setEnabled(False); self.progress.show(); self.status.setText('Starting local inference…')
        self.worker=BackendWorker(payload); self.worker.event.connect(lambda e:self.status.setText(e.get('message','Working…'))); self.worker.done.connect(self.finish_worker); self.worker.start()
    def finish_worker(self,result):
        self.generate_btn.setEnabled(True); self.analyze_btn.setEnabled(True); self.progress.hide()
        if result.get('stage')=='complete' and result.get('output'):
            self.output=result['output']; self.play_btn.setEnabled(True); self.export_btn.setEnabled(True); self.status.setText('Speech generated successfully · saved locally'); self.refresh_library()
            analysis=result.get('reference_analysis',{})
            self.render_analysis(analysis)
            self.render_comparison(result.get('comparison',{}))
        elif result.get('stage')=='complete':
            self.render_analysis(result.get('analysis',{})); self.status.setText('Speaker analysis complete and saved locally.'); self.refresh_profile()
        else: self.status.setText('Error: '+result.get('message','Unknown error'))

    def render_analysis(self,a):
        def val(key,unit=''):
            value=a.get(key); return f'{value}{unit}' if value is not None else 'n/a'
        self.analysis.setText(f"Reference analysis · {val('duration_seconds','s')} analyzed\nPitch median: {val('pitch_median_hz',' Hz')} · pitch variation: {val('pitch_variability_hz_estimate',' Hz')}\nSpeech rate: {val('speech_rate_wpm_estimate',' WPM')} · pause estimate: {val('pause_count_estimate')} · RMS: {val('rms_dbfs',' dBFS')}")

    def render_comparison(self,c):
        metrics=c.get('metrics',{})
        def delta(key,unit=''):
            value=metrics.get(key,{}).get('difference'); return f'{value:+.1f}{unit}' if isinstance(value,(int,float)) else 'n/a'
        self.comparison.setText('Generated vs reference · metric differences (not an identity score)\n'+f"Pitch: {delta('pitch_median_hz',' Hz')} · Rate: {delta('speech_rate_wpm_estimate',' WPM')} · RMS: {delta('rms_dbfs',' dB')}")

    def play_output(self):
        if not self.output or self.player is None: return
        if self.player.source().isEmpty() or self.player.source().toLocalFile()!=self.output: self.player.setSource(QUrl.fromLocalFile(self.output))
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState: self.player.pause(); self.play_btn.setText('Resume preview'); self.status.setText('Preview paused.')
        else: self.player.play(); self.play_btn.setText('Pause preview'); self.status.setText('Playing preview.')
    def export_output(self):
        if not self.output: return
        path,_=QFileDialog.getSaveFileName(self,'Export generated audio',Path(self.output).name,'WAV (*.wav)')
        if path: shutil.copy2(self.output,path); self.status.setText('Exported '+path)
    def refresh_library(self):
        while self.library.count():
            item=self.library.takeAt(0); w=item.widget(); w.deleteLater() if w else None
        files=sorted(OUTPUTS.glob('*.wav'),key=lambda p:p.stat().st_mtime,reverse=True)[:50]
        if not files:
            empty=QLabel('No generated audio yet. Your exports will appear here after synthesis.'); empty.setObjectName('muted'); self.library.addWidget(empty); return
        for path in files:
            row=QHBoxLayout(); info=QVBoxLayout(); name=QLabel(path.stem); name.setStyleSheet('font-weight:700;');
            size=path.stat().st_size/1024/1024; date=datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime('%d %b %Y · %H:%M')
            detail=QLabel(f'{size:.1f} MB · {date}'); detail.setObjectName('muted'); info.addWidget(name); info.addWidget(detail); row.addLayout(info,1)
            open_btn=QPushButton('Play file'); open_btn.clicked.connect(lambda checked=False,p=path:self.open_library_file(p)); row.addWidget(open_btn)
            export_btn=QPushButton('Export copy'); export_btn.clicked.connect(lambda checked=False,p=path:self.export_file(p)); row.addWidget(export_btn)
            self.library.addWidget(self.card('',row))

    def open_library_file(self,path):
        self.output=str(path); self.play_btn.setEnabled(True); self.export_btn.setEnabled(True); self.tabs.setCurrentIndex(0); self.play_output()

    def export_file(self,path):
        target,_=QFileDialog.getSaveFileName(self,'Export audio copy',path.name,'WAV (*.wav)')
        if target:
            try: shutil.copy2(path,target); self.status.setText('Exported '+target)
            except OSError as exc: QMessageBox.warning(self,'Export failed',str(exc))

    def closeEvent(self,event):
        if self.media_recorder is not None and self.media_recorder.recorderState()==QMediaRecorder.RecorderState.RecordingState: self.media_recorder.stop()
        if self.player is not None: self.player.stop()
        if self.worker is not None and self.worker.isRunning(): self.worker.wait(2000)
        super().closeEvent(event)

def main():
    app=QApplication(sys.argv); app.setApplicationName('Voxora'); app.setOrganizationName('PSP-YN')
    win=VoxoraWindow(); win.show(); return app.exec()
if __name__=='__main__': raise SystemExit(main())
