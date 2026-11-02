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
window, window.background { background: #161B22; color: #F0F3F6; }
.main-header { background: #0D1117; border-bottom: 1px solid #30363D; min-height: 52px; }
.main-header button { color: #C9D1D9; }
.sidebar { background: #0D1117; color: #F0F3F6; min-width: 252px; border-right: 1px solid #30363D; padding: 0 2px; }
.brand-title { color: #F0F3F6; font-size: 15px; font-weight: 750; }
.brand-subtitle { color: #8B949E; font-size: 10px; letter-spacing: 1.1px; font-weight: 750; }
.brand-logo { border-radius: 8px; }
.nav-button { color: #AAB4BF; background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 12px 14px; min-height: 44px; font-weight: 600; }
.nav-button:hover { background: #1C252D; color: #F0F3F6; }
.nav-button.nav-active { background: #0F5A47; color: #FFFFFF; border-color: #16765C; }
.nav-button.nav-active image { color: #FFFFFF; }
.sidebar-caption { color: #8B949E; font-size: 10px; font-weight: 800; letter-spacing: 1.2px; }
.sidebar-foot { color: #AAB4BF; font-size: 11px; }
.page-title { color: #F0F3F6; font-size: 30px; font-weight: 800; letter-spacing: -.6px; }
.page-subtitle { color: #AAB4BF; font-size: 13px; }
.section-title { color: #F0F3F6; font-size: 15px; font-weight: 750; }
.muted { color: #8B949E; font-size: 12px; }
.card { background: #161B22; border: 1px solid #30363D; border-radius: 8px; padding: 18px; }
button { color: #D0D7DE; background: #212830; border: 1px solid #30363D; border-radius: 8px; padding: 9px 13px; min-height: 38px; font-weight: 650; }
button:hover { background: #28333D; border-color: #46535F; }
button:disabled { opacity: .42; }
.primary-action { background: #15803D; color: #FFFFFF; border: 1px solid #15803D; border-radius: 8px; padding: 11px 19px; min-height: 44px; font-weight: 750; }
.primary-action:hover { background: #166534; border-color: #166534; }
.upload-action { background: #10B981; color: #052E25; border: 1px solid #10B981; border-radius: 8px; padding: 11px 15px; min-height: 44px; font-weight: 750; }
.upload-action:hover { background: #34D399; }
.record-action { background: #0F766E; color: #FFFFFF; border: 1px solid #0F766E; border-radius: 8px; padding: 11px 15px; min-height: 44px; font-weight: 750; }
.record-action:hover { background: #115E59; }
.soft-action { background: #212830; color: #D0D7DE; border-color: #30363D; }
.language-picker { color: #F0F3F6; background: #212830; border: 1px solid #30363D; border-radius: 8px; padding: 5px; min-height: 42px; }
entry, textview.entry-area { background: #0D1117; color: #F0F3F6; border: 1px solid #30363D; border-radius: 8px; padding: 11px; }
textview.entry-area text { background: #0D1117; color: #F0F3F6; }
.pill { background: #043422; color: #51CF66; border: 1px solid #0F5A47; border-radius: 99px; padding: 6px 12px; font-size: 10px; font-weight: 800; letter-spacing: .4px; }
.status-text { color: #AAB4BF; font-size: 12px; }
.wave-bar { background: #10B981; border-radius: 3px; min-width: 3px; }
.wave-muted { background: #48525D; border-radius: 3px; min-width: 3px; }
.footer-panel { background: #1C252D; border: 1px solid #30363D; border-radius: 8px; padding: 12px 16px; }
scrolledwindow { background: transparent; }
separator { background: #30363D; }
checkbutton { color: #C9D1D9; }
spinner { color: #10B981; }
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
        self.window.set_default_size(1360, 900)
        self.window.set_size_request(1040, 720)
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

        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        brand.set_halign(Gtk.Align.CENTER)
        brand.set_margin_top(4)
        logo = Gtk.Image.new_from_file(str(ROOT / "assets" / "voxora-logo.png"))
        logo.set_pixel_size(158)
        logo.set_halign(Gtk.Align.CENTER)
        logo.add_css_class("brand-logo")
        brand.append(logo)
        brand.append(label("LOCAL VOICE STUDIO", "brand-subtitle", False))
        sidebar.append(brand)
        sidebar.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        sidebar.append(label("WORKSPACE", "sidebar-caption"))

        self.nav_buttons = {}
        nav_items = [
            ("create", "Create speech", "document-new-symbolic"),
            ("voice", "My voices", "audio-input-microphone-symbolic"),
            ("library", "Exports & history", "folder-music-symbolic"),
            ("settings", "System Settings", "preferences-system-symbolic"),
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
        sidebar.append(label("◆  Your audio stays local  •  Secure & private", "sidebar-foot", True))

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
        page.set_margin_top(24)
        page.set_margin_bottom(20)
        page.set_margin_start(26)
        page.set_margin_end(26)

        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        heading.set_valign(Gtk.Align.CENTER)
        heading.set_margin_bottom(20)
        title_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        title_col.set_hexpand(True)
        self.page_heading("Create voiceover", "Turn text into natural speech using a short voice recording.", title_col)
        heading.append(title_col)
        heading.append(label("✓  LOCAL PROCESSING ONLY", "pill", False))
        page.append(heading)

        language_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        language_card.add_css_class("card")
        language_card.set_margin_bottom(18)
        self.language = Gtk.DropDown.new_from_strings(["English", "Hindi", "Kannada"])
        self.language.set_selected(0)
        self.language.set_size_request(-1, 42)
        self.language.set_hexpand(True)
        self.language.add_css_class("language-picker")
        language_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        language_row.append(label("Output language", "section-title", False))
        language_row.append(self.language)
        language_card.append(language_row)
        language_card.append(label("Select the target language for your cloned voice.", "muted"))
        page.append(language_card)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        body.set_vexpand(True)
        body.set_homogeneous(True)
        body.set_margin_bottom(16)
        page.append(body)

        voice_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        voice_card.add_css_class("card")
        voice_card.set_hexpand(True)
        voice_card.set_vexpand(True)
        script_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        script_card.add_css_class("card")
        script_card.set_hexpand(True)
        script_card.set_vexpand(True)
        body.append(voice_card)
        body.append(script_card)

        voice_heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        voice_heading.append(Gtk.Image.new_from_icon_name("audio-input-microphone-symbolic"))
        voice_heading.append(label("01  ·  Reference Voice", "section-title", False))
        voice_card.append(voice_heading)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        actions.set_homogeneous(True)
        upload = button("Choose audio file", "document-open-symbolic", "upload-action")
        upload.connect("clicked", self.choose_audio)
        actions.append(upload)
        self.record_button = button("Record now", "audio-input-microphone-symbolic", "record-action")
        self.record_button.connect("clicked", self.toggle_recording)
        actions.append(self.record_button)
        voice_card.append(actions)
        self.ref_label = label(Path(self.reference_path).name if self.reference_path else "No reference audio selected", "muted", True)
        voice_card.append(self.ref_label)
        voice_card.append(Gtk.Separator())
        voice_card.append(label("Recording transcript", "section-title", False))
        self.transcript = Gtk.TextView()
        self.transcript.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.transcript.set_size_request(-1, 70)
        self.transcript.add_css_class("entry-area")
        self.transcript.get_buffer().set_text(PROFILE_TEXT.read_text(encoding="utf-8") if PROFILE_TEXT.exists() else "")
        transcript_scroll = Gtk.ScrolledWindow()
        transcript_scroll.set_min_content_height(72)
        transcript_scroll.set_child(self.transcript)
        voice_card.append(transcript_scroll)
        wave = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        wave.set_halign(Gtk.Align.FILL)
        wave.set_margin_top(4)
        heights = [7,12,19,10,25,15,32,18,12,24,38,17,27,13,20,34,15,24,11,18,30,14,23,12,17,27,9,14,21,11,6]
        for h in heights:
            bar = Gtk.Box()
            bar.add_css_class("wave-bar")
            bar.set_size_request(3,h)
            bar.set_valign(Gtk.Align.CENTER)
            bar.set_hexpand(True)
            wave.append(bar)
        voice_card.append(wave)
        self.save_profile = Gtk.CheckButton(label="Save as default voice model")
        voice_card.append(self.save_profile)

        script_heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        script_heading.append(Gtk.Image.new_from_icon_name("text-x-generic-symbolic"))
        script_heading.append(label("02  ·  Script to generate", "section-title", False))
        script_card.append(script_heading)
        self.script = Gtk.TextView()
        self.script.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.script.set_vexpand(True)
        self.script.set_size_request(-1, 280)
        self.script.add_css_class("entry-area")
        self.script.get_buffer().set_text("This is a test of the Local Voice Studio desktop application.")
        script_scroll = Gtk.ScrolledWindow()
        script_scroll.set_min_content_height(280)
        script_scroll.set_vexpand(True)
        script_scroll.set_child(self.script)
        script_card.append(script_scroll)
        self.script_count = label("58 / 1000", "muted", False)
        self.script_count.set_halign(Gtk.Align.END)
        script_card.append(self.script_count)
        self.script.get_buffer().connect("changed", self.update_script_count)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.add_css_class("footer-panel")
        footer.set_valign(Gtk.Align.CENTER)
        footer.append(label("Generated Audio", "section-title", False))
        audio_wave = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        audio_wave.set_hexpand(True)
        audio_wave.set_halign(Gtk.Align.START)
        for h in [8,13,19,11,25,16,30,20,12,23,16,28,12,19,9,14,21,11,7]:
            bar=Gtk.Box(); bar.add_css_class("wave-muted"); bar.set_size_request(3,h); bar.set_valign(Gtk.Align.CENTER); audio_wave.append(bar)
        footer.append(audio_wave)
        self.spinner = Gtk.Spinner()
        footer.append(self.spinner)
        self.status = label("Ready", "status-text", True)
        self.status.set_max_width_chars(28)
        footer.append(self.status)
        self.generate_button = button("Generate speech", "media-playback-start-symbolic", "primary-action")
        self.generate_button.connect("clicked", self.generate)
        footer.append(self.generate_button)
        self.play_button = button("Play preview", "media-playback-start-symbolic")
        self.play_button.set_sensitive(False)
        self.play_button.connect("clicked", self.play_output)
        footer.append(self.play_button)
        self.save_button = button("Save file", "document-save-symbolic")
        self.save_button.set_sensitive(False)
        self.save_button.connect("clicked", self.save_output)
        footer.append(self.save_button)
        page.append(footer)

        self.output_path = None
        return page

    def update_script_count(self, buffer):
        if not hasattr(self, "script_count"):
            return
        value = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        self.script_count.set_text(f"{len(value)} / 1000")

    def build_voice_page(self):
        page = self.page_shell()
        self.page_heading("My voices", "Manage the recording and transcript used as your default voice profile.", page)
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
        self.page_heading("Exports & history", "Audio generated on this device. Nothing is uploaded.", page)
        self.library_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        self.library_box.set_margin_top(22)
        page.append(self.library_box)
        self.refresh_library()
        return page

    def build_settings_page(self):
        page = self.page_shell()
        self.page_heading("System Settings", "Local models, privacy and application information.", page)
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
        card.append(label("English F5-TTS pretrained weights: CC BY-NC 4.0 (non-commercial use only). Hindi SPRINGLab F5-Hindi: CC BY 4.0. Kannada OpenBible: CC BY-SA 4.0. See MODEL-LICENSES.md before redistribution or commercial use.", "muted", True))
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

    def save_output(self, *_):
        if not self.output_path or not Path(self.output_path).is_file():
            self.set_status("Generate speech before saving an audio file.")
            return
        dialog = Gtk.FileChooserNative.new(
            "Save generated audio", self.window, Gtk.FileChooserAction.SAVE,
            "Save file", "Cancel")
        dialog.set_current_name(Path(self.output_path).name)
        dialog.connect("response", self.on_output_save_response)
        dialog.show()

    def on_output_save_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            target = dialog.get_file()
            if target:
                try:
                    shutil.copy2(self.output_path, target.get_path())
                    self.set_status("Audio file saved successfully.")
                except Exception as exc:
                    self.set_status(f"Could not save audio: {exc}")
        dialog.destroy()

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
