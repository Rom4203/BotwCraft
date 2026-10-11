//! Direct Windows.Graphics.Capture of a real Ryujinx process, not browser titles.
use std::error::Error;
use std::sync::{Arc, Mutex, OnceLock};
use eframe::egui;
use std::time::{Duration,Instant};
use windows_capture::capture::{Context, GraphicsCaptureApiHandler};
use windows_capture::frame::Frame;
use windows_capture::graphics_capture_api::InternalCaptureControl;
use windows_capture::settings::{
    ColorFormat, CursorCaptureSettings, DirtyRegionSettings, DrawBorderSettings,
    MinimumUpdateIntervalSettings, SecondaryWindowSettings, Settings,
};
use windows_capture::window::Window;

#[derive(Clone)]
pub struct PixelFrame {
    pub width: usize,
    pub height: usize,
    pub data: Vec<u8>,
}

#[derive(Clone)]
pub struct FrameInbox {
    pub latest: Arc<Mutex<Option<PixelFrame>>>,
    pub wake: Arc<OnceLock<egui::Context>>,
}

struct Capture {
    inbox: FrameInbox,
    last_frame: Instant,
}

impl GraphicsCaptureApiHandler for Capture {
    type Flags = FrameInbox;
    type Error = Box<dyn Error + Send + Sync>;
    fn new(ctx: Context<Self::Flags>) -> Result<Self, Self::Error> {
        Ok(Self { inbox: ctx.flags, last_frame: Instant::now() - Duration::from_millis(20) })
    }
    fn on_frame_arrived(
        &mut self,
        frame: &mut Frame<'_>,
        _control: InternalCaptureControl,
    ) -> Result<(), Self::Error> {
        // Ryujinx can output 120Hz; avoid duplicating 1080p RGBA copies.
        // Does not slow the input ring or the camera's native update.
        if self.last_frame.elapsed() < Duration::from_millis(16) {
            return Ok(());
        }
        self.last_frame = Instant::now();
        let width = frame.width() as usize;
        let height = frame.height() as usize;
        if width == 0 || height == 0 || width > 3840 || height > 2160 {
            return Ok(());
        }
        let mut buffer = frame.buffer()?;
        let stride = buffer.row_pitch() as usize;
        let row = width * 4;
        let bytes = buffer.as_raw_buffer();
        if stride < row || bytes.len() < stride * height { return Ok(()); }
        let mut data = Vec::with_capacity(row * height);
        for y in 0..height {
            data.extend_from_slice(&bytes[y * stride..y * stride + row]);
        }
        // Never block WGC callback / GPU thread if compositor is late.
        // The old 2-frame FIFO could render a frame 32ms behind even if a
        // newer WGC frame was already captured. Replace pending frame with
        // the *newest*, using a short mutex only after GPU readback ends.
        if let Ok(mut latest) = self.inbox.latest.lock() {
            *latest=Some(PixelFrame { width, height, data });
        }
        // Guaranteed thread-safe egui request_repaint from capture thread.
        if let Some(ctx) = self.inbox.wake.get() { ctx.request_repaint(); }
        Ok(())
    }
}

pub fn run_capture(inbox: FrameInbox) -> Result<(), Box<dyn Error + Send + Sync>> {
    let target = Window::enumerate()?
        .into_iter()
        .filter(|window| window.is_valid())
        .find(|window| {
            window.process_name().is_ok_and(|name| {
                matches!(name.to_ascii_lowercase().as_str(), "ryujinx.exe" | "ryujinx.ava.exe")
            })
        })
        .ok_or("Ryujinx.exe not running / no capturable window")?;
    eprintln!("[BotwCraft] Capturing verified process {}", target.process_name()?);
    let settings = Settings::new(
        target,
        CursorCaptureSettings::WithoutCursor,
        DrawBorderSettings::Default,
        SecondaryWindowSettings::Default,
        MinimumUpdateIntervalSettings::Default,
        DirtyRegionSettings::Default,
        ColorFormat::Rgba8,
        inbox,
    );
    Capture::start(settings)?;
    Ok(())
}
