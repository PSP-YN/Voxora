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
gi.require_version("Gst", "1.0")
from gi.repository import Gtk, Adw, Gio, GLib, Gdk, Gst
Gst.init(None)

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
        self.preview_source = None
        self.preview_path = None
        self.preview_state = "stopped"
        self.busy = False

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.build_window()
        self.window.present()
        self.window.maximize()
        saved_profile = VOICES / "speaker_profile.json"
        if saved_profile.exists():
            try:
                self.render_speaker_analysis(json.loads(saved_profile.read_text(encoding="utf-8")))
            except Exception:
                pass
        comparisons = sorted(OUTPUTS.glob("*.comparison.json"), key=lambda p:p.stat().st_mtime, reverse=True)
        if comparisons:
            try:
                self.render_speaker_comparison(json.loads(comparisons[0].read_text(encoding="utf-8")))
            except Exception:
                pass

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
        analyze_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.analyze_button = button("Analyze speaker profile", "view-statistics-symbolic")
        self.analyze_button.connect("clicked", self.analyze_speaker_profile)
        analyze_row.append(self.analyze_button)
        voice_card.append(analyze_row)
        self.speaker_analysis_label = label("Pitch, pause, speech-rate and vocal-signal analysis will appear here.", "muted", True)
        voice_card.append(self.speaker_analysis_label)
        self.speaker_comparison_label = label("Generated-vs-reference comparison appears after synthesis.", "muted", True)
        voice_card.append(self.speaker_comparison_label)

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
        script_tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pause_insert = button("Insert 500 ms pause", "media-playback-pause-symbolic")
        pause_insert.connect("clicked", lambda *_: self.script.get_buffer().insert_at_cursor("[pause:500ms]"))
        script_tools.append(pause_insert)
        emphasis_insert = button("Emphasize selection", "format-text-bold-symbolic")
        emphasis_insert.connect("clicked", self.wrap_script_selection_emphasis)
        script_tools.append(emphasis_insert)
        speed_insert = button("Selected text · slower", "speedometer-symbolic")
        speed_insert.connect("clicked", self.wrap_script_selection_speed)
        script_tools.append(speed_insert)
        delivery_insert = button("Selected text · delivery", "text-formatting-symbolic")
        delivery_insert.connect("clicked", self.wrap_script_selection_delivery)
        script_tools.append(delivery_insert)
        script_card.append(script_tools)
        script_hint = label("Sentence-level tags: [pause:500ms] · [speed:0.9]…[/speed] · [delivery:formal]…[/delivery] · [emphasis]words[/emphasis]", "muted", True)
        script_card.append(script_hint)
        self.script_count = label("58 characters", "muted", False)
        self.script_count.set_halign(Gtk.Align.END)
        script_card.append(self.script_count)
        self.script.get_buffer().connect("changed", self.update_script_count)

        # Generation controls map to parameters genuinely supported by F5-TTS.
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        controls.add_css_class("card")
        controls.set_margin_bottom(14)
        controls.append(label("03  ·  Delivery & voice controls", "section-title", False))
        controls.append(label("Presets adjust generation behaviour; they do not guarantee a specific emotion or accent.", "muted"))
        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        preset_row.append(label("Delivery preset", "section-title", False))
        self.style_preset = Gtk.DropDown.new_from_strings(["Natural", "Professional", "Formal", "Conversational", "Expressive"])
        self.style_preset.set_selected(0)
        self.style_preset.set_hexpand(True)
        self.style_preset.connect("notify::selected", self.apply_style_preset)
        preset_row.append(self.style_preset)
        controls.append(preset_row)
        mood_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mood_row.append(label("Emotional delivery (approximate)", "section-title", False))
        self.mood_picker = Gtk.DropDown.new_from_strings(["Neutral", "Calm", "Upbeat", "Confident", "Warm", "Dramatic"])
        self.mood_picker.set_selected(0)
        self.mood_picker.set_hexpand(True)
        mood_row.append(self.mood_picker)
        controls.append(mood_row)
        slider_grid = Gtk.Grid()
        slider_grid.set_column_spacing(18); slider_grid.set_row_spacing(10)
        self.speed_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.70, 1.30, 0.05)
        self.speed_scale.set_value(1.0); self.speed_scale.set_digits(2); self.speed_scale.set_hexpand(True)
        self.speed_value = label("1.00×", "muted", False)
        self.speed_scale.connect("value-changed", lambda w: self.speed_value.set_text(f"{w.get_value():.2f}×"))
        slider_grid.attach(label("Pace / speed", "muted", False), 0, 0, 1, 1); slider_grid.attach(self.speed_scale, 1, 0, 1, 1); slider_grid.attach(self.speed_value, 2, 0, 1, 1)
        self.guidance_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1.0, 4.0, 0.1)
        self.guidance_scale.set_value(2.0); self.guidance_scale.set_digits(1); self.guidance_scale.set_hexpand(True)
        self.guidance_value = label("2.0", "muted", False)
        self.guidance_scale.connect("value-changed", lambda w: self.guidance_value.set_text(f"{w.get_value():.1f}"))
        slider_grid.attach(label("Voice adherence", "muted", False), 0, 1, 1, 1); slider_grid.attach(self.guidance_scale, 1, 1, 1, 1); slider_grid.attach(self.guidance_value, 2, 1, 1, 1)
        self.variation_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.1)
        self.variation_scale.set_value(-1.0); self.variation_scale.set_digits(1); self.variation_scale.set_hexpand(True)
        self.variation_value = label("Auto", "muted", False)
        self.variation_scale.connect("value-changed", lambda w: self.variation_value.set_text("Auto" if w.get_value() <= -0.95 else f"{w.get_value():.1f}"))
        slider_grid.attach(label("Rhythm / prosody variation", "muted", False), 0, 2, 1, 1); slider_grid.attach(self.variation_scale, 1, 2, 1, 1); slider_grid.attach(self.variation_value, 2, 2, 1, 1)
        self.loudness_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.04, 0.20, 0.01)
        self.loudness_scale.set_value(0.10); self.loudness_scale.set_digits(2); self.loudness_scale.set_hexpand(True)
        self.loudness_value = label("0.10", "muted", False)
        self.loudness_scale.connect("value-changed", lambda w: self.loudness_value.set_text(f"{w.get_value():.2f}"))
        slider_grid.attach(label("Output loudness", "muted", False), 0, 3, 1, 1); slider_grid.attach(self.loudness_scale, 1, 3, 1, 1); slider_grid.attach(self.loudness_value, 2, 3, 1, 1)
        self.pitch_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -3.0, 3.0, 0.5)
        self.pitch_scale.set_value(0.0); self.pitch_scale.set_digits(1); self.pitch_scale.set_hexpand(True)
        self.pitch_value = label("0.0 st", "muted", False)
        self.pitch_scale.connect("value-changed", lambda w: self.pitch_value.set_text(f"{w.get_value():+.1f} st"))
        slider_grid.attach(label("Pitch / intonation shift", "muted", False), 0, 4, 1, 1); slider_grid.attach(self.pitch_scale, 1, 4, 1, 1); slider_grid.attach(self.pitch_value, 2, 4, 1, 1)
        self.emphasis_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.1)
        self.emphasis_scale.set_value(0.5); self.emphasis_scale.set_digits(1); self.emphasis_scale.set_hexpand(True)
        self.emphasis_value = label("0.5", "muted", False)
        self.emphasis_scale.connect("value-changed", lambda w: self.emphasis_value.set_text(f"{w.get_value():.1f}"))
        slider_grid.attach(label("Marked emphasis strength", "muted", False), 0, 5, 1, 1); slider_grid.attach(self.emphasis_scale, 1, 5, 1, 1); slider_grid.attach(self.emphasis_value, 2, 5, 1, 1)
        controls.append(slider_grid)
        controls.append(label("Mood presets indirectly adjust pace and sampling (model-dependent, not guaranteed emotion). Pitch shift is post-processing and can alter perceived timbre. Pauses and emphasis tags operate sentence-by-sentence; this model cannot guarantee human-like acting.", "muted", True))
        page.append(controls)

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

    def wrap_script_selection_emphasis(self, *_):
        buf = self.script.get_buffer()
        bounds = buf.get_selection_bounds()
        if not bounds:
            self.set_status("Select text in the script first, then mark it for emphasis.")
            return
        start, end = bounds
        selected = buf.get_text(start, end, True)
        buf.delete(start, end)
        buf.insert(start, f"[emphasis]{selected}[/emphasis]")

    def wrap_script_selection_speed(self, *_):
        buf = self.script.get_buffer()
        bounds = buf.get_selection_bounds()
        if not bounds:
            self.set_status("Select a sentence or phrase first to adjust its pace.")
            return
        start, end = bounds
        selected = buf.get_text(start, end, True)
        buf.delete(start, end)
        buf.insert(start, f"[speed:0.90]{selected}[/speed]")

    def wrap_script_selection_delivery(self, *_):
        buf = self.script.get_buffer()
        bounds = buf.get_selection_bounds()
        if not bounds:
            self.set_status("Select a sentence or phrase first to set its delivery.")
            return
        choices = ["natural", "professional", "formal", "conversational", "expressive"]
        selected_style = choices[self.style_preset.get_selected()]
        start, end = bounds
        selected = buf.get_text(start, end, True)
        buf.delete(start, end)
        buf.insert(start, f"[delivery:{selected_style}]{selected}[/delivery]")

    def analyze_speaker_profile(self, *_):
        if self.busy:
            return
        if not self.reference_path or not Path(self.reference_path).is_file():
            self.set_status("Choose a reference recording before analyzing it.")
            return
        payload = {"action":"analyze", "language":"English", "text":"", "transcript":self.get_text(self.transcript),
                   "reference_audio":self.reference_path, "save_profile":True}
        self.busy=True
        self.generate_button.set_sensitive(False)
        self.analyze_button.set_sensitive(False)
        self.spinner.start()
        self.set_status("Analyzing reference voice profile…")
        threading.Thread(target=self.run_backend, args=(payload,), daemon=True).start()

    def apply_style_preset(self, *_):
        # Conservative mappings: presets only adjust speed and sampling variation.
        presets = {
            0: (1.00, -1.0, 2.0),  # Natural
            1: (0.96, -0.5, 2.2),  # Professional
            2: (0.92, -0.7, 2.3),  # Formal
            3: (1.04, -0.3, 1.9),  # Conversational
            4: (1.00, 0.2, 1.8),   # Expressive
        }
        speed, variation, guidance = presets.get(self.style_preset.get_selected(), presets[0])
        self.speed_scale.set_value(speed)
        self.variation_scale.set_value(variation)
        self.guidance_scale.set_value(guidance)

    def update_script_count(self, buffer):
        if not hasattr(self, "script_count"):
            return
        value = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        self.script_count.set_text(f"{len(value):,} characters")

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
                   "reference_audio": self.reference_path, "save_profile": self.save_profile.get_active(),
                   "settings": {"speed": self.speed_scale.get_value(),
                                "guidance": self.guidance_scale.get_value(),
                                "variation": self.variation_scale.get_value(),
                                "loudness": self.loudness_scale.get_value(),
                                "mood": ["neutral","calm","upbeat","confident","warm","dramatic"][self.mood_picker.get_selected()],
                                "pitch_shift": self.pitch_scale.get_value(),
                                "emphasis_strength": self.emphasis_scale.get_value()}}
        self.busy = True
        self.generate_button.set_sensitive(False)
        self.spinner.start()
        self.set_status(f"Starting {language} generation… first load can take a little while.")
        threading.Thread(target=self.run_backend, args=(payload,), daemon=True).start()

    def run_backend(self, payload):
        try:
            # Merge stderr into stdout so the UI drains one pipe. Reading stdout
            # while leaving stderr unread can deadlock if model logs fill the pipe.
            proc = subprocess.Popen([str(PYTHON), str(BACKEND)],
                cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1)
            proc.stdin.write(json.dumps(payload, ensure_ascii=False))
            proc.stdin.close()
            events = []
            diagnostics = []
            for line in proc.stdout:
                try:
                    event = json.loads(line.strip())
                    if isinstance(event, dict) and "stage" in event:
                        events.append(event)
                        GLib.idle_add(self.set_status, event.get("message", "Working…"))
                    else:
                        diagnostics.append(line)
                except json.JSONDecodeError:
                    diagnostics.append(line)
            code = proc.wait()
            if diagnostics:
                (LOGS / "last-generation.log").write_text(
                    "".join(diagnostics)[-30000:], encoding="utf-8")
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
        if hasattr(self, "analyze_button"):
            self.analyze_button.set_sensitive(True)
        if result.get("stage") == "complete" and result.get("analysis") and not result.get("output"):
            self.render_speaker_analysis(result.get("analysis", {}))
            self.set_status("Speaker profile analyzed and saved locally.")
            self.refresh_profile()
        elif result.get("stage") == "complete":
            self.stop_preview_silently()
            self.output_path = result.get("output")
            self.play_button.set_sensitive(True); self.save_button.set_sensitive(True)
            analysis = result.get("reference_analysis", {})
            if analysis:
                self.render_speaker_analysis(analysis)
                comp = result.get("comparison", {}).get("metrics", {})
                pitch_delta = comp.get("pitch_median_hz", {}).get("difference")
                rate_delta = comp.get("speech_rate_wpm_estimate", {}).get("difference")
                compare_text = f" · pitch delta {pitch_delta:+.1f} Hz" if isinstance(pitch_delta, (int,float)) else ""
                compare_text += f" · rate delta {rate_delta:+.1f} WPM" if isinstance(rate_delta, (int,float)) else ""
                self.render_speaker_comparison(result.get("comparison", {}))
                self.set_status(f"Speech ready · analyzed reference {analysis.get('duration_seconds', 0):.0f}s{compare_text}")
            else:
                self.set_status("Speech generated successfully. Saved on this computer.")
            self.refresh_library()
        else:
            self.set_status("Could not generate speech: " + result.get("message", "Unknown error"))
        return GLib.SOURCE_REMOVE

    def render_speaker_analysis(self, analysis):
        if not hasattr(self, "speaker_analysis_label"):
            return
        def fmt(value, unit=""):
            return f"{value}{unit}" if value is not None else "n/a"
        self.speaker_analysis_label.set_text(
            f"Speaker profile · {fmt(analysis.get('duration_seconds'), 's')} analyzed\n"
            f"Pitch median: {fmt(analysis.get('pitch_median_hz'), ' Hz')} · range: {fmt(analysis.get('pitch_p05_hz'), '–')} {fmt(analysis.get('pitch_p95_hz'), ' Hz')}\n"
            f"Pitch variation: {fmt(analysis.get('pitch_variability_hz_estimate'), ' Hz')} · intonation slope: {fmt(analysis.get('intonation_slope_hz_estimate'), ' Hz')} · rate: {fmt(analysis.get('speech_rate_wpm_estimate'), ' WPM')}\n"
            f"Pauses: {fmt(analysis.get('pause_count_estimate'))} · median {fmt(analysis.get('pause_median_seconds_estimate'), 's')} · low-energy frames: {fmt(analysis.get('pause_frame_percent'), '%')}\n"
            f"Energy emphasis ratio: {fmt(analysis.get('energy_emphasis_ratio_estimate'))} · RMS: {fmt(analysis.get('rms_dbfs'), ' dBFS')} · centroid: {fmt(analysis.get('spectral_centroid_median_hz'), ' Hz')}\n"
            "These are acoustic estimates, not emotion/identity detection.")

    def render_speaker_comparison(self, comparison):
        if not hasattr(self, "speaker_comparison_label"):
            return
        metrics = comparison.get("metrics", {})
        def delta(key, unit=""):
            value = metrics.get(key, {}).get("difference")
            return f"{value:+.1f}{unit}" if isinstance(value, (int, float)) else "n/a"
        self.speaker_comparison_label.set_text(
            "Generated audio vs reference (difference):\n"
            f"Pitch median {delta('pitch_median_hz', ' Hz')} · pitch range {delta('pitch_range_hz_estimate', ' Hz')} · pitch variation {delta('pitch_variability_hz_estimate', ' Hz')}\n"
            f"Estimated speaking rate {delta('speech_rate_wpm_estimate', ' WPM')} · pause/low-energy {delta('pause_frame_percent', '%')} · RMS {delta('rms_dbfs', ' dB')}\n"
            f"Spectral centroid {delta('spectral_centroid_median_hz', ' Hz')}\n"
            "Metric differences are not a speaker identity or quality score.")

    def play_library_file(self, path):
        self.stop_preview_silently()
        self.output_path = str(path)
        self.play_button.set_sensitive(True)
        self.navigate(None, "create")
        self.play_output()

    def play_output(self, *_):
        if not self.output_path or not Path(self.output_path).is_file():
            self.set_status("Generate speech before playing a preview.")
            return
        if self.preview is None:
            self.preview = Gst.ElementFactory.make("playbin", "voxora-preview")
            if self.preview is None:
                self.set_status("GStreamer playback is unavailable. Install GStreamer plugins.")
                return
            self.preview.set_property("uri", Path(self.output_path).resolve().as_uri())
            bus = self.preview.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_preview_message)
            self.preview_path = self.output_path
        if self.preview_state == "playing":
            self.preview_state = "paused"
            self.preview.set_state(Gst.State.PAUSED)
            self.play_button.set_label("Resume preview")
            self.play_button.set_icon_name("media-playback-start-symbolic")
            self.set_status("Preview paused. Resume continues from the same position.")
        else:
            self.preview_state = "playing"
            self.preview.set_state(Gst.State.PLAYING)
            self.play_button.set_label("Pause preview")
            self.play_button.set_icon_name("media-playback-pause-symbolic")
            self.set_status("Playing preview.")

    def _on_preview_message(self, _bus, message):
        if message.type == Gst.MessageType.EOS:
            self.stop_preview_silently()
            self.set_status("Preview finished.")
        elif message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            self.stop_preview_silently()
            self.set_status(f"Audio playback error: {err.message}")

    def _reset_preview_controls(self):
        if hasattr(self, "play_button"):
            self.play_button.set_label("Play preview")
            self.play_button.set_icon_name("media-playback-start-symbolic")

    def stop_preview_silently(self):
        player = self.preview
        self.preview = None
        self.preview_state = "stopped"
        if player is not None:
            bus = player.get_bus()
            if bus: bus.remove_signal_watch()
            player.set_state(Gst.State.NULL)
        self._reset_preview_controls()

    def stop_preview(self):
        self.stop_preview_silently()
        self.set_status("Preview stopped.")

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

    def do_shutdown(self):
        self.stop_preview_silently()
        if self.recording and self.recording.poll() is None:
            self.recording.terminate()
        Adw.Application.do_shutdown(self)

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
                profile_file = VOICES / "speaker_profile.json"
                analyzed = "Speaker profile: analyzed" if profile_file.exists() else "Speaker profile: not analyzed yet"
                self.profile_status.set_text(f"Saved recording: {PROFILE_AUDIO.name}  ·  {duration:.1f} seconds\nTranscript: {'available' if PROFILE_TEXT.exists() else 'missing'}\n{analyzed}")
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
            play = button("Play", "media-playback-start-symbolic"); play.connect("clicked", lambda _b,p=path: self.play_library_file(p)); row.append(play)
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
