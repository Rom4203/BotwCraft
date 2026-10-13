#![cfg_attr(not(target_os = "windows"), allow(unused))]
mod capture;
mod hud;
mod viewport;

use capture::{FrameInbox, PixelFrame};
use eframe::egui;
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};

struct BotwCraftApp {
    latest_capture: Arc<Mutex<Option<PixelFrame>>>,
    hud_map: Option<hud::SharedHud>,
    game_texture: Option<egui::TextureHandle>,
    hud_texture: Option<egui::TextureHandle>,
    game_size: (usize, usize),
    hud_size: (usize, usize),
    last_reconnect: Instant,
    last_hud_upload: Instant,
    status: String,
    last_view: Option<egui::Rect>,
    last_pointer: Option<egui::Pos2>,
    only_game: bool,
    crop_top: usize,
    crop_bottom: usize,
    captured_cursor: bool,
}

fn upload(ctx: &egui::Context, texture: &mut Option<egui::TextureHandle>, frame: PixelFrame, label: &str) {
    let image = egui::ColorImage::from_rgba_unmultiplied([frame.width, frame.height], &frame.data);
    if let Some(existing) = texture { existing.set(image, egui::TextureOptions::LINEAR); }
    else { *texture = Some(ctx.load_texture(label, image, egui::TextureOptions::LINEAR)); }
}

// SDL3 scancodes used by original SkyCraft InputBridge, not Windows virtual keys.
fn minecraft_scancode(k: egui::Key) -> Option<u16> {
    use egui::Key::*;
    Some(match k {
        A=>4, B=>5, C=>6, D=>7, E=>8, F=>9, G=>10, H=>11, I=>12,
        J=>13, K=>14, L=>15, M=>16, N=>17, O=>18, P=>19, Q=>20,
        R=>21, S=>22, T=>23, U=>24, V=>25, W=>26, X=>27, Y=>28, Z=>29,
        Num1=>30, Num2=>31, Num3=>32, Num4=>33, Num5=>34,
        Num6=>35, Num7=>36, Num8=>37, Num9=>38, Num0=>39,
        Enter=>40, Escape=>41, Backspace=>42, Tab=>43, Space=>44,
        Minus=>45, Equals=>46, OpenBracket=>47, CloseBracket=>48,
        Backslash=>49, Semicolon=>51, Quote=>52, Comma=>54, Period=>55,
        Slash=>56, ArrowRight=>79, ArrowLeft=>80, ArrowDown=>81, ArrowUp=>82,
        _=>return None,
    })
}

impl eframe::App for BotwCraftApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        if self.hud_map.is_none() && self.last_reconnect.elapsed() >= Duration::from_secs(1) {
            self.hud_map = hud::SharedHud::open();
            self.last_reconnect = Instant::now();
        }
        let focused = ctx.input(|i| i.focused);
        let gameplay_mouse = focused && self.hud_map.as_ref().is_some_and(hud::SharedHud::is_gameplay_mouse);
        if gameplay_mouse != self.captured_cursor {
            ctx.send_viewport_cmd(egui::ViewportCommand::CursorGrab(if gameplay_mouse {
                egui::CursorGrab::Confined
            } else { egui::CursorGrab::None }));
            ctx.send_viewport_cmd(egui::ViewportCommand::CursorVisible(!gameplay_mouse));
            self.captured_cursor = gameplay_mouse;
            self.last_pointer = None;
        }

        let events = ctx.input(|i| i.events.clone());
        // PointerMoved and MouseMoved may both be generated: NEVER double
        // a relative camera event. MouseMoved is true unbounded raw motion.
        let raw_delta_in_frame = events.iter().any(|e| matches!(e, egui::Event::MouseMoved(_)));
        if let Some(mapping) = self.hud_map.as_mut().filter(|m| m.inputs_enabled()) {
            // Otherwise the 4096-entry ring would retain all early clicks
            // and replay them unexpectedly after /botwcraft inputs on.
            for event in events {
                match event {
                    egui::Event::Key { key, pressed, .. } => {
                        // Internal compositor controls are NOT routed to Minecraft.
                        if matches!(key,egui::Key::F7|egui::Key::F8|egui::Key::F10|egui::Key::F1) { continue; }
                        if let Some(scancode) = minecraft_scancode(key) {
                            let _ = mapping.push_input(1, scancode, i32::from(pressed), 0, 0);
                        }
                    }
                    egui::Event::PointerMoved(pos) => {
                        if gameplay_mouse {
                            // Fallback when egui integration cannot supply raw motion.
                            if !raw_delta_in_frame {
                                if let Some(old) = self.last_pointer {
                                    let dx=(pos.x-old.x).round() as i32;
                                    let dy=(pos.y-old.y).round() as i32;
                                    if dx.abs()<=200 && dy.abs()<=200 && (dx!=0 || dy!=0) {
                                        let _=mapping.push_input(9,0,dx,dy,0);
                                    }
                                }
                            }
                        } else if let Some(view) = self.last_view {
                            if let Some((x,y))=viewport::to_minecraft(pos,view,self.hud_size) {
                                let _=mapping.push_input(4,0,x,y,0);
                            }
                        }
                        self.last_pointer=Some(pos);
                    }
                    egui::Event::MouseMoved(delta) => {
                        if gameplay_mouse {
                            let dx=delta.x.round().clamp(-1000.0,1000.0) as i32;
                            let dy=delta.y.round().clamp(-1000.0,1000.0) as i32;
                            if dx!=0 || dy!=0 { let _=mapping.push_input(9,0,dx,dy,0); }
                        }
                    }
                    egui::Event::PointerButton { pos, button, pressed, .. } => {
                        let code = match button {
                            egui::PointerButton::Primary=>1,
                            egui::PointerButton::Secondary=>3,
                            egui::PointerButton::Middle=>2,
                            _=>0,
                        };
                        if code!=0 {
                            // Minecraft Screen.mouseClicked reads last cursor,
                            // so send mapped ABSOLUTE position BEFORE the click.
                            if !gameplay_mouse {
                                if let Some((x,y))=self.last_view.and_then(|v|
                                        viewport::to_minecraft(pos,v,self.hud_size)) {
                                    let _=mapping.push_input(4,0,x,y,0);
                                } else { continue; }
                            }
                            let _=mapping.push_input(2,code,i32::from(pressed),0,0);
                        }
                    }
                    egui::Event::MouseWheel { delta, .. } => {
                        let ticks=(delta.y*120.0/24.0).round() as i32;
                        if ticks!=0 { let _=mapping.push_input(3,0,ticks,0,0); }
                    }
                    egui::Event::Text(text) => {
                        for ch in text.chars() { let _=mapping.push_input(5,0,ch as i32,0,0); }
                    }
                    egui::Event::WindowFocused(false) => {
                        let _=mapping.push_input(6,0,0,0,0);
                        self.last_pointer=None;
                    }
                    _=>{}
                }
            }
        }

        // Input events have already been forwarded to Minecraft before
        // potentially expensive WGC RGBA texture / HUD GPU uploads.
        // Drop lagged WGC frames: the compositor should show LIVE Zelda.
        // The capture callback replaces stale frames atomically rather than
        // queuing up two old pictures. Dropped frames are NEVER replayed.
        let last = self.latest_capture.lock().ok().and_then(|mut frame| frame.take());
        if let Some(last) = last {
            self.game_size = (last.width, last.height);
            upload(ctx, &mut self.game_texture, last, "ryujinx-live-video");
        }
        // HUD uploads are 8 MiB each at 1080p. Cap at ~30Hz so Minecraft
        // keeps GPU/CPU headroom; process mouse/keyboard EVERY UI frame.
        if self.last_hud_upload.elapsed() >= Duration::from_millis(33) {
            if let Some(map) = self.hud_map.as_mut() {
                if let Some(next) = map.next_frame() {
                    self.hud_size = (next.width, next.height);
                    upload(ctx, &mut self.hud_texture, next, "minecraft-actual-hud");
                }
            }
            self.last_hud_upload=Instant::now();
        }

        if ctx.input(|i| i.key_pressed(egui::Key::F10)) { self.only_game=!self.only_game; }
        if ctx.input(|i| i.key_pressed(egui::Key::F7)) { self.crop_top=self.crop_top.saturating_sub(4); }
        if ctx.input(|i| i.key_pressed(egui::Key::F8)) { self.crop_top=(self.crop_top+4).min(200); }
        if ctx.input(|i| i.key_pressed(egui::Key::F1)) {
            self.status=format!("Zelda {}x{} / HUD {}x{} | coupe haut {}px bas {}px | F10: Zelda seul / F7-F8: cadrage",
                self.game_size.0,self.game_size.1,self.hud_size.0,self.hud_size.1,
                self.crop_top,self.crop_bottom);
        }

        egui::CentralPanel::default()
            .frame(egui::Frame::NONE.fill(egui::Color32::BLACK))
            .show(ctx, |ui| {
                let area=ui.available_rect_before_wrap();
                if let Some(game)=&self.game_texture {
                    let crop=viewport::crop_video(self.game_size.0,self.game_size.1,
                                                  self.only_game,self.crop_top,self.crop_bottom);
                    let screen=viewport::fit(area,crop.width,crop.height);
                    self.last_view=Some(screen);
                    ui.painter().image(game.id(),screen,crop.uv,egui::Color32::WHITE);
                    if let Some(hud)=&self.hud_texture {
                        let full_uv=egui::Rect::from_min_max(egui::pos2(0.0,0.0),egui::pos2(1.0,1.0));
                        ui.painter().image(hud.id(),screen,full_uv,egui::Color32::WHITE);
                    }
                } else {
                    self.last_view=None;
                    ui.painter().text(area.center(),egui::Align2::CENTER_CENTER,
                        "BotwCraft - capture de Zelda en attente...\nRyujinx ouvert (non minimise) + Minecraft /botwcraft connect /botwcraft hud on /botwcraft inputs on",
                        egui::FontId::proportional(18.0),egui::Color32::WHITE);
                }
                if !self.status.is_empty() {
                    ui.painter().text(area.left_top()+egui::vec2(12.0,14.0),
                        egui::Align2::LEFT_TOP,&self.status,
                        egui::FontId::proportional(13.0),egui::Color32::LIGHT_YELLOW);
                }
            });
        ctx.request_repaint_after(Duration::from_millis(16));
    }
}

#[cfg(target_os="windows")]
fn main() -> eframe::Result {
    // A single overwriteable latest-frame slot: zero frame queue latency.
    // WGC is still capped to ~60fps to protect Minecraft and Ryujinx.
    let latest_capture = Arc::new(Mutex::new(None));
    let repaint_ctx = Arc::new(OnceLock::new());
    let inbox = FrameInbox {
        latest: Arc::clone(&latest_capture),
        wake: Arc::clone(&repaint_ctx),
    };
    std::thread::spawn(move || {
        loop {
            match capture::run_capture(inbox.clone()) {
                Ok(()) => eprintln!("[COMPOSITOR] Capture ended; searching for Ryujinx again"),
                Err(err) => eprintln!("[COMPOSITOR] Ryujinx capture unavailable: {err}; retry in 2 seconds"),
            }
            std::thread::sleep(Duration::from_secs(2));
        }
    });
    let mut options=eframe::NativeOptions {
        renderer:eframe::Renderer::Wgpu,
        viewport:egui::ViewportBuilder::default()
            .with_inner_size([1280.0,720.0])
            .with_title("BotwCraft - Minecraft dans Hyrule"),
        ..Default::default()
    };
    // Default eframe/wgpu is AutoVsync with a GPU present queue, which can
    // add 1-3 monitor refreshes after Zelda has rendered its camera frame.
    // AutoNoVsync avoids the queued frames; one in-flight surface image.
    // Reversible via BOTWCRAFT_LOW_LATENCY=0 if a display stutters/tears.
    if std::env::var("BOTWCRAFT_LOW_LATENCY").ok().as_deref()!=Some("0") {
        options.wgpu_options.present_mode = eframe::wgpu::PresentMode::AutoNoVsync;
        options.wgpu_options.desired_maximum_frame_latency = Some(1);
        eprintln!("[COMPOSITOR] Low latency: newest-frame mailbox, immediate WGC repaint, no VSync queue");
    }
    eframe::run_native("BotwCraft",options,Box::new(move |cc| {
        // WGC callback can wake egui immediately when a NEW Zelda frame
        // arrives. No extra fixed 16ms wakeup wait between capture/display.
        let _ = repaint_ctx.set(cc.egui_ctx.clone());
        Ok(Box::new(BotwCraftApp {
        latest_capture,hud_map:None,game_texture:None,hud_texture:None,
        game_size:(1280,720),hud_size:(0,0),
        last_reconnect:Instant::now()-Duration::from_secs(2),
        last_hud_upload:Instant::now()-Duration::from_secs(1),
        status:String::new(),last_view:None,last_pointer:None,
        only_game:true,crop_top:54,crop_bottom:22,captured_cursor:false,
    }))}))
}

#[cfg(not(target_os="windows"))]
fn main() { eprintln!("This compositor runs only on Windows / Ryujinx."); }
