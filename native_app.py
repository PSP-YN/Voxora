#!/usr/bin/python3
"""Native GNOME desktop application for fully local voice cloning."""
import os, sys, json, subprocess, threading, datetime, shutil
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, Gdk

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "native_backend.py"
PYTHON = ROOT / ".venv" / "bin" / "python"
VOICES = ROOT / "voices"
OUTPUTS = ROOT / "outputs"
LOGS = ROOT / "logs"
for folder in (VOICES, OUTPUTS, LOGS):
    folder.mkdir(exist_ok=True)
PROFILE_AUDIO = VOICES / "my_voice.wav"
PROFILE_TEXT = VOICES / "my_voice.txt"

CSS = """
window { background: #f7f5ff; color: #241b38; }
.main-header { background: #ffffff; border-bottom: 1px solid #e8e1f4; }
.sidebar { background: #21182f; color: #f8f5ff; min-width: 224px; }
.brand-title { color: #ffffff; font-size: 17px; font-weight: 800; }
.brand-subtitle { color: #c2b5da; font-size: 10px; }
.nav-button { color: #d6cce7; background: transparent; border: 0; border-radius: 10px; padding: 11px 13px; }
.nav-button:hover { background: #38294f; color: #ffffff; }
.nav-button.nav-active { background: #593a82; color: #ffffff; }
.sidebar-caption { color: #a99abd; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
.sidebar-foot { color: #d0c6df; font-size: 11px; }
.page-title { color: #241b38; font-size: 27px; font-weight: 800; }
.page-subtitle { color: #766b88; font-size: 13px; }
.section-title { color: #302342; font-size: 14px; font-weight: 750; }
.muted { color: #786f88; font-size: 12px; }
.card { background: #ffffff; border: 1px solid #e9e3f1; border-radius: 15px; padding: 17px; }
button { color: #57317d; background: #f0e9fa; border: 1px solid #e3d8f0; border-radius: 9px; padding: 7px 10px; }
button:hover { background: #e7dcf4; }
dropdown, .language-picker { color: #302342; background: #ffffff; border: 1px solid #ded5eb; border-radius: 9px; padding: 4px; }
.primary-action { background: #7042a5; color: #ffffff; border-radius: 10px; padding: 11px 20px; font-weight: 700; }
.primary-action:hover { background: #5e348f; }
.soft-action { background: #f0e9fa; color: #61388f; border-radius: 9px; }
.entry-area { background: #ffffff; color: #241b38; border: 1px solid #ded5eb; border-radius: 10px; padding: 10px; }
textview.entry-area { background: #ffffff; color: #241b38; }
.pill { background: #eee5f8; color: #61388f; border-radius: 99px; padding: 5px 10px; font-size: 10px; font-weight: 800; }
.status-text { color: #665b76; font-size: 12px; }
scrolledwindow { background: transparent; }
"""

def label(text, css=None, wrap=True):
    w = Gtk.Label(label=text)
    w.set_xalign(0)
    w.set_yalign(0)
    w.set_wrap(wrap)
    w.set_hexpand(False)
    w.set_max_width_chars(72)
    if css: w.add_css_class(css)
    return w

def button(text, icon=None, css=None):
    b = Gtk.Button()
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    if icon: row.append(Gtk.Image.new_from_icon_name(icon))
    row.append(Gtk.Label(label=text))
    b.set_child(row)
    if css: b.add_css_class(css)
    return b

class VoiceStudio(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.pspyn.Voxora",
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None
        self.reference_path = str(PROFILE_AUDIO) if PROFILE_AUDIO.exists() else None
        self.recording = None
        self.recording_path = None
        self.preview = None
        self.busy = False

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.build_window()
        self.window.present()
        self.window.maximize()

    def build_window(self):
        self.window = Adw.ApplicationWindow(application=self)
        self.window.set_title("Voxora")
        self.window.set_default_size(1240, 860)
        self.window.set_size_request(980, 700)
        self.window.set_decorated(True)

        # Explicit native window controls: minimize, maximize/restore and close.
        header = Adw.HeaderBar()
        header.add_css_class("main-header")
        header.set_title_widget(Adw.WindowTitle.new("Voxora", "Private voice studio"))
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        toolbar.set_content(shell)
        self.window.set_content(toolbar)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sidebar.add_css_class("sidebar")
        sidebar.set_size_request(240, -1)
        sidebar.set_hexpand(False)
        sidebar.set_vexpand(True)
        sidebar.set_margin_top(22); sidebar.set_margin_bottom(18)
        sidebar.set_margin_start(15); sidebar.set_margin_end(15)
        shell.append(sidebar)

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        mark = Gtk.Box()
        mark.add_css_class("pill")
        mark.set_size_request(42, 42)
        mark.set_valign(Gtk.Align.CENTER)
        mark.append(Gtk.Image.new_from_icon_name("audio-speakers-symbolic"))
        brand.append(mark)
        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        brand_text.append(label("VOXORA", "brand-title"))
        brand_text.append(label("PRIVATE  ·  ON-DEVICE AI", "brand-subtitle"))
        brand.append(brand_text)
        sidebar.append(brand)
        sidebar.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        sidebar.append(label("WORKSPACE", "sidebar-caption"))

        self.nav_buttons = {}
        nav_items = [
            ("create", "Create speech", "document-new-symbolic"),
            ("voice", "My voice", "audio-input-microphone-symbolic"),
            ("library", "Your exports", "folder-music-symbolic"),
            ("settings", "Models & settings", "preferences-system-symbolic"),
        ]
        for key, title, icon in nav_items:
            b = button(title, icon, "nav-button")
            b.set_halign(Gtk.Align.FILL)
            b.set_hexpand(True)
            b.set_has_frame(False)
            b.connect("clicked", self.navigate, key)
            sidebar.append(b)
            self.nav_buttons[key] = b

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        sidebar.append(spacer)
        sidebar.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        sidebar.append(label("YOUR AUDIO STAYS HERE", "sidebar-caption"))
        sidebar.append(label("No cloud inference\nNo API keys\nNo account required", "sidebar-foot", True))

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(140)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        content_scroll = Gtk.ScrolledWindow()
        content_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content_scroll.set_hexpand(True)
        content_scroll.set_vexpand(True)
        content_scroll.set_child(self.stack)
        shell.append(content_scroll)

        self.stack.add_named(self.build_create_page(), "create")
        self.stack.add_named(self.build_voice_page(), "voice")
        self.stack.add_named(self.build_library_page(), "library")
        self.stack.add_named(self.build_settings_page(), "settings")
        self.navigate(None, "create")

    def page_shell(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(28); outer.set_margin_bottom(24)
        outer.set_margin_start(28); outer.set_margin_end(28)
        outer.set_hexpand(True); outer.set_vexpand(True)
        return outer

    def page_heading(self, title, subtitle, parent):
        parent.append(label(title, "page-title"))
        parent.append(label(subtitle, "page-subtitle"))

    def build_create_page(self):
        page = self.page_shell()
        self.page_heading("Create your voiceover", "Turn text into natural speech using a short recording of your voice.", page)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        top.set_margin_top(18)
        top.append(label("NEW GENERATION", "sidebar-caption", False))
        spacer = Gtk.Box(); spacer.set_hexpand(True); top.append(spacer)
        top.append(label("LOCAL PROCESSING", "pill", False))
        page.append(top)

        language_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        language_card.add_css_class("card")
        language_card.append(label("Output language", "section-title"))
        self.language = Gtk.DropDown.new_from_strings(["English", "Hindi", "Kannada"])
        self.language.set_selected(0)
        self.language.set_size_request(-1, 40)
        self.language.set_hexpand(True)
        self.language.set_visible(True)
        self.language.add_css_class("language-picker")
        language_card.append(self.language)
        language_card.append(label("Choose the language you want your cloned voice to speak.", "muted"))
        page.append(language_card)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        body.set_margin_top(14)
        body.set_vexpand(True)
        page.append(body)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        left.set_hexpand(True); left.set_vexpand(True)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        right.set_hexpand(True); right.set_vexpand(True)
        body.append(left); body.append(right)

        voice_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        voice_card.add_css_class("card")
        voice_card.append(label("01  ·  YOUR VOICE SAMPLE", "section-title"))
        voice_card.append(label("Use a clean 5–12 second recording. A transcript is required for accurate cloning.", "muted", True))
        self.ref_label = label(self.reference_path or "No recording selected", "status-text", True)
        voice_card.append(self.ref_label)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_homogeneous(True)
        upload = button("Choose audio", "document-open-symbolic", "soft-action")
        upload.connect("clicked", self.choose_audio)
        actions.append(upload)
        self.record_button = button("Record", "media-record-symbolic")
        self.record_button.set_visible(True)
        self.record_button.set_hexpand(False)
        self.record_button.add_css_class("soft-action")
        self.record_button.connect("clicked", self.toggle_recording)
        actions.append(self.record_button)
        voice_card.append(actions)
        voice_card.append(label("Recording transcript", "section-title"))
        self.transcript = Gtk.TextView()
        self.transcript.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.transcript.set_size_request(-1, 86)
        self.transcript.add_css_class("entry-area")
        self.transcript.get_buffer().set_text(PROFILE_TEXT.read_text(encoding="utf-8") if PROFILE_TEXT.exists() else "")
        transcript_scroll = Gtk.ScrolledWindow()
        transcript_scroll.set_min_content_height(82); transcript_scroll.set_child(self.transcript)
        voice_card.append(transcript_scroll)
        self.save_profile = Gtk.CheckButton(label="Save this as my default voice")
        voice_card.append(self.save_profile)
        left.append(voice_card)

        tips_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        tips_card.add_css_class("card")
        tips_card.append(label("RECORDING TIPS", "section-title", False))
        tips_card.append(label("Record in a quiet room and keep the microphone at a steady distance.", "muted", True))
        tips_card.append(label("Use one speaker, avoid music and background voices, and speak naturally.", "muted", True))
        tips_card.append(label("Write the exact words from your reference recording in the transcript box.", "muted", True))
        left.append(tips_card)

        text_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        text_card.add_css_class("card")
        text_card.append(label("02  ·  WHAT SHOULD I SAY?", "section-title"))
        text_card.append(label("Paste the words you want spoken. Use the selected language.", "muted", True))
        self.script = Gtk.TextView()
        self.script.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.script.set_vexpand(True)
        self.script.set_size_request(-1, 210)
        self.script.add_css_class("entry-area")
        self.script.get_buffer().set_text("")
        script_scroll = Gtk.ScrolledWindow()
        script_scroll.set_min_content_height(220)
        script_scroll.set_vexpand(True)
        script_scroll.set_child(self.script)
        text_card.append(script_scroll)
        right.append(text_card)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bottom.set_margin_top(14)
        self.spinner = Gtk.Spinner()
        bottom.append(self.spinner)
        self.status = label("Ready. Your models run entirely on this computer.", "status-text", True)
        self.status.set_hexpand(True)
        bottom.append(self.status)
        self.generate_button = button("Generate speech", "media-playback-start-symbolic", "primary-action")
        self.generate_button.connect("clicked", self.generate)
        bottom.append(self.generate_button)
        page.append(bottom)

        output_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        output_card.add_css_class("card")
        output_card.set_margin_top(12)
        out_icon = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
        output_card.append(out_icon)
        output_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        output_col.set_hexpand(True)
        output_col.append(label("Your generated audio", "section-title"))
        self.output_label = label("Your WAV file will appear here after generation.", "muted")
        output_col.append(self.output_label)
        output_card.append(output_col)
        self.play_button = button("Play", "media-playback-start-symbolic")
        self.play_button.set_sensitive(False)
        self.play_button.connect("clicked", self.play_output)
        output_card.append(self.play_button)
        self.save_button = button("Show file", "folder-open-symbolic")
        self.save_button.set_sensitive(False)
        self.save_button.connect("clicked", self.reveal_output)
        output_card.append(self.save_button)
        page.append(output_card)
        self.output_path = None
        return page

    def build_voice_page(self):
        page = self.page_shell()
        self.page_heading("My voice", "Manage the recording and transcript used as your default voice profile.", page)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("card"); card.set_margin_top(22)
        card.append(label("DEFAULT VOICE PROFILE", "section-title"))
        self.profile_status = label("", "muted", True)
        card.append(self.profile_status)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        use = button("Use saved recording", "audio-input-microphone-symbolic", "soft-action")
        use.connect("clicked", self.use_saved_profile)
        row.append(use)
        replace = button("Choose new recording", "document-open-symbolic")
        replace.connect("clicked", self.choose_audio)
        row.append(replace)
        card.append(row)
        card.append(label("A good reference is 5–12 seconds, recorded in a quiet room. The transcript must match the spoken words exactly.", "muted", True))
        page.append(card)
        self.refresh_profile()
        return page

    def build_library_page(self):
        page = self.page_shell()
        self.page_heading("Your exports", "Audio generated on this device. Nothing is uploaded.", page)
        self.library_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        self.library_box.set_margin_top(22)
        page.append(self.library_box)
        self.refresh_library()
        return page

    def build_settings_page(self):
        page = self.page_shell()
        self.page_heading("Models & settings", "Local models, privacy and application information.", page)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.add_css_class("card"); card.set_margin_top(22)
        card.append(label("INSTALLED SPEECH MODELS", "section-title"))
        for lang, name, detail in [
            ("English", "F5-TTS v1 Base", "General-purpose English voice cloning."),
            ("Hindi", "SPRINGLab F5-Hindi Small", "Hindi speech synthesis checkpoint."),
            ("Kannada", "F5-TTS OpenBible Kannada", "Kannada checkpoint; quality can vary by accent and text style."),
        ]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            col.set_hexpand(True)
            col.append(label(name, "section-title")); col.append(label(detail, "muted"))
            row.append(col); row.append(label("ON DEVICE", "pill"))
            card.append(row)
        card.append(Gtk.Separator())
        card.append(label("PRIVACY", "section-title"))
        card.append(label("Speech generation runs locally. The app sets Hugging Face and Transformers offline flags. No API key, account or cloud inference is used. Internet is only needed if you choose to update or download models.", "muted", True))
        card.append(label("MODEL LICENCES", "section-title"))
        card.append(label("English F5-TTS: MIT. Hindi SPRINGLab F5-Hindi: CC BY 4.0. Kannada OpenBible: CC BY-SA 4.0. See MODEL-LICENSES.md before redistribution.", "muted", True))
        page.append(card)
        return page

    def navigate(self, _button, key):
        self.stack.set_visible_child_name(key)
        for name, b in self.nav_buttons.items():
            b.add_css_class("nav-button")
            if name == key: b.add_css_class("nav-active")
            else: b.remove_css_class("nav-active")
        if key == "library": self.refresh_library()
        if key == "voice": self.refresh_profile()

    def choose_audio(self, *_):
        dialog = Gtk.FileChooserNative.new("Choose a voice recording", self.window,
            Gtk.FileChooserAction.OPEN, "Choose recording", "Cancel")
        filt = Gtk.FileFilter(); filt.set_name("Audio files")
        for ext in ("wav", "mp3", "flac", "ogg", "m4a", "aac"): filt.add_pattern("*." + ext)
        dialog.add_filter(filt)
        dialog.connect("response", self.on_audio_chosen)
        dialog.show()

    def on_audio_chosen(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            f = dialog.get_file()
            if f:
                self.reference_path = f.get_path()
                self.ref_label.set_text(Path(self.reference_path).name)
        dialog.destroy()

    def toggle_recording(self, *_):
        if self.recording:
            self.recording.terminate()
            try: self.recording.wait(timeout=3)
            except subprocess.TimeoutExpired: self.recording.kill()
            self.recording = None
            self.reference_path = self.recording_path
            self.ref_label.set_text(Path(self.reference_path).name + "  ·  recording saved")
            self.record_button.set_label("Record again")
            self.set_status("Recording saved. Enter the exact transcript below.")
            return
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.recording_path = str(VOICES / f"recording_{stamp}.wav")
        try:
            self.recording = subprocess.Popen(["arecord", "-q", "-f", "S16_LE", "-r", "24000", "-c", "1", self.recording_path],
                                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self.record_button.set_label("Stop recording")
            self.ref_label.set_text("Recording… click Stop recording when finished.")
            self.set_status("Recording from your default microphone.")
        except FileNotFoundError:
            self.set_status("Audio recorder is not installed. Install alsa-utils.")

    def get_text(self, view):
        buf = view.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True).strip()

    def set_status(self, message):
        self.status.set_text(message)

    def generate(self, *_):
        if self.busy: return
        script = self.get_text(self.script)
        transcript = self.get_text(self.transcript)
        if not self.reference_path or not Path(self.reference_path).is_file():
            self.set_status("Choose or record your voice sample first."); return
        if not transcript:
            self.set_status("Enter the exact transcript of your voice sample."); return
        if not script:
            self.set_status("Enter the text you want spoken."); return
        language = ["English", "Hindi", "Kannada"][self.language.get_selected()]
        payload = {"language": language, "text": script, "transcript": transcript,
                   "reference_audio": self.reference_path, "save_profile": self.save_profile.get_active()}
        self.busy = True
        self.generate_button.set_sensitive(False)
        self.spinner.start()
        self.set_status(f"Starting {language} generation… first load can take a little while.")
        threading.Thread(target=self.run_backend, args=(payload,), daemon=True).start()

    def run_backend(self, payload):
        try:
            proc = subprocess.Popen([str(PYTHON), str(BACKEND)],
                cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1)
            proc.stdin.write(json.dumps(payload, ensure_ascii=False))
            proc.stdin.close()
            events = []
            for line in proc.stdout:
                try:
                    event = json.loads(line.strip())
                    events.append(event)
                    GLib.idle_add(self.set_status, event.get("message", "Working…"))
                except json.JSONDecodeError:
                    pass
            stderr = proc.stderr.read()
            code = proc.wait()
            if stderr:
                (LOGS / "last-generation.log").write_text(stderr[-30000:], encoding="utf-8")
            result = events[-1] if events else {"stage":"error","message":"The inference worker returned no result. Check logs/last-generation.log."}
            if code != 0 and result.get("stage") != "error":
                result = {"stage":"error","message":"Generation process failed. Check logs/last-generation.log."}
            GLib.idle_add(self.finish_generation, result)
        except Exception as exc:
            GLib.idle_add(self.finish_generation, {"stage":"error","message":str(exc)})

    def finish_generation(self, result):
        self.busy = False
        self.generate_button.set_sensitive(True)
        self.spinner.stop()
        if result.get("stage") == "complete":
            self.output_path = result.get("output")
            self.output_label.set_text(Path(self.output_path).name)
            self.play_button.set_sensitive(True); self.save_button.set_sensitive(True)
            self.set_status("Speech generated successfully. Saved on this computer.")
            self.refresh_library()
        else:
            self.set_status("Could not generate speech: " + result.get("message", "Unknown error"))
        return GLib.SOURCE_REMOVE

    def play_output(self, *_):
        if self.output_path and Path(self.output_path).exists():
            subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", self.output_path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def reveal_output(self, *_):
        if self.output_path:
            subprocess.Popen(["xdg-open", str(Path(self.output_path).parent)])

    def use_saved_profile(self, *_):
        if PROFILE_AUDIO.exists():
            self.reference_path = str(PROFILE_AUDIO)
            self.ref_label.set_text(PROFILE_AUDIO.name)
            if PROFILE_TEXT.exists():
                self.transcript.get_buffer().set_text(PROFILE_TEXT.read_text(encoding="utf-8"))
            self.navigate(None, "create")
            self.set_status("Saved voice profile loaded.")
        else:
            self.set_status("No saved profile yet. Choose or record a voice sample.")

    def refresh_profile(self):
        if not hasattr(self, "profile_status"): return
        if PROFILE_AUDIO.exists():
            try:
                import wave
                with wave.open(str(PROFILE_AUDIO), "rb") as w:
                    duration = w.getnframes() / float(w.getframerate())
                self.profile_status.set_text(f"Saved recording: {PROFILE_AUDIO.name}  ·  {duration:.1f} seconds\nTranscript: {'available' if PROFILE_TEXT.exists() else 'missing'}")
            except Exception:
                self.profile_status.set_text("Saved recording found.")
        else:
            self.profile_status.set_text("No default voice saved yet. Create speech and enable “Save this as my default voice”.")

    def refresh_library(self):
        if not hasattr(self, "library_box"): return
        child = self.library_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.library_box.remove(child)
            child = nxt
        files = sorted(OUTPUTS.glob("*.wav"), key=lambda p:p.stat().st_mtime, reverse=True)
        if not files:
            self.library_box.append(label("No exports yet. Your generated WAV files will appear here.", "muted"))
            return
        for path in files[:30]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.add_css_class("card")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3); col.set_hexpand(True)
            col.append(label(path.name, "section-title"))
            col.append(label(datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%d %b %Y, %I:%M %p"), "muted"))
            row.append(col)
            play = button("Play", "media-playback-start-symbolic"); play.connect("clicked", lambda _b,p=path: subprocess.Popen(["ffplay","-nodisp","-autoexit","-loglevel","error",str(p)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)); row.append(play)
            reveal = button("Show", "folder-open-symbolic"); reveal.connect("clicked", lambda _b,p=path: subprocess.Popen(["xdg-open",str(p.parent)])); row.append(reveal)
            self.library_box.append(row)

def main():
    if "--self-test" in sys.argv:
        # Automated desktop-to-inference smoke test using F5's bundled demo voice.
        app = VoiceStudio()
        language = sys.argv[sys.argv.index("--self-test") + 1] if len(sys.argv) > sys.argv.index("--self-test") + 1 else "English"
        if language not in ("English", "Hindi", "Kannada"):
            print("SELF_TEST_FAIL: unknown language", language, flush=True)
            return 2
        sample = ROOT / ".venv/lib/python3.12/site-packages/f5_tts/infer/examples/basic/basic_ref_en.wav"
        transcript = "Some call me nature, others call me mother nature."
        scripts = {
            "English": "This is a test of the Local Voice Studio desktop application.",
            "Hindi": "नमस्ते, यह स्थानीय डेस्कटॉप ऐप का परीक्षण है।",
            "Kannada": "ನಮಸ್ಕಾರ, ಇದು ಸ್ಥಳೀಯ ಡೆಸ್ಕ್‌ಟಾಪ್ ಅಪ್ಲಿಕೇಶನ್ ಪರೀಕ್ಷೆ."
        }
        def start_test():
            app.reference_path = str(sample)
            app.transcript.get_buffer().set_text(transcript)
            app.script.get_buffer().set_text(scripts[language])
            app.language.set_selected(["English", "Hindi", "Kannada"].index(language))
            app.generate()
            GLib.timeout_add_seconds(1, monitor_test)
            return GLib.SOURCE_REMOVE
        def monitor_test():
            if app.busy:
                return GLib.SOURCE_CONTINUE
            if app.output_path and Path(app.output_path).is_file():
                print("SELF_TEST_PASS", language, app.output_path, flush=True)
                app.quit()
                return GLib.SOURCE_REMOVE
            print("SELF_TEST_FAIL", app.status.get_text(), flush=True)
            app.quit()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(1200, start_test)
        return app.run([sys.argv[0]])
    app = VoiceStudio()
    return app.run(sys.argv)

if __name__ == "__main__":
    raise SystemExit(main())
