//! Ryujinx chrome cropping and Minecraft coordinate conversion.
//! Cropping changes texture UVs on the GPU; the source frame is not copied.
use eframe::egui;

#[derive(Clone, Copy, Debug)]
pub struct SourceCrop {
    pub uv: egui::Rect,
    pub width: f32,
    pub height: f32,
}

/// Exclude Ryujinx's title/menu/status bars and center on its 16:9 game image.
/// Chrome sizes are user-adjustable at runtime. Without `game_only` the complete
/// source window is shown to help calibrate unusual Ryujinx versions.
pub fn crop_video(width: usize, height: usize, game_only: bool, top: usize, bottom: usize) -> SourceCrop {
    let w = width.max(1) as f32;
    let h = height.max(1) as f32;
    if !game_only || height < 120 {
        return SourceCrop { uv: egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0)), width:w, height:h };
    }
    let top = top.min(height.saturating_sub(4)) as f32;
    let bottom = bottom.min(height.saturating_sub(top as usize + 4)) as f32;
    let inner_h = (h - top - bottom).max(1.0);
    let target_aspect = 16.0 / 9.0;
    let (x, y, cw, ch) = if w / inner_h >= target_aspect {
        let cw = inner_h * target_aspect;
        ((w-cw)/2.0, top, cw, inner_h)
    } else {
        let ch = w / target_aspect;
        (0.0, top+(inner_h-ch)/2.0, w, ch)
    };
    SourceCrop {
        uv: egui::Rect::from_min_max(egui::pos2(x/w,y/h),egui::pos2((x+cw)/w,(y+ch)/h)),
        width: cw, height: ch,
    }
}

pub fn fit(area: egui::Rect, w: f32, h: f32) -> egui::Rect {
    let f=(area.width()/w.max(1.0)).min(area.height()/h.max(1.0));
    egui::Rect::from_center_size(area.center(),egui::vec2(w*f,h*f))
}

/// Convert a position in the BotwCraft viewport (logical egui points) to the
/// ACTUAL Minecraft HUD framebuffer pixels, with both letterboxes excluded.
/// Do not substitute Ryujinx 2860x1526 or the BotwCraft window size here.
pub fn to_minecraft(pos: egui::Pos2, game: egui::Rect, hud_size:(usize,usize)) -> Option<(i32,i32)> {
    if !game.contains(pos) || hud_size.0 == 0 || hud_size.1 == 0 { return None; }
    let fx = ((pos.x-game.left())/game.width()).clamp(0.0,1.0);
    let fy = ((pos.y-game.top())/game.height()).clamp(0.0,1.0);
    Some(((fx*hud_size.0 as f32).floor().min((hud_size.0-1) as f32) as i32,
          (fy*hud_size.1 as f32).floor().min((hud_size.1-1) as f32) as i32))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ryujinx_chrome_and_sidebars_disappear() {
        let crop=crop_video(2860,1526,true,54,22);
        assert!(crop.uv.min.y>0.03);
        assert!(crop.uv.max.y<0.99);
        assert!(crop.uv.min.x>0.03 && crop.uv.max.x<0.97);
        assert!((crop.width/crop.height-16.0/9.0).abs()<0.001);
    }
    #[test]
    fn source_aspect_and_pointer_scaling_are_independent() {
        let outer=egui::Rect::from_min_size(egui::pos2(20.0,30.0),egui::vec2(1280.0,740.0));
        let game=fit(outer,1920.0,1080.0);
        assert_eq!(to_minecraft(game.center(),game,(854,480)),Some((427,240)));
        assert_eq!(to_minecraft(game.left_top()+egui::vec2(1.0,1.0),game,(854,480)),Some((0,0)));
        assert_eq!(to_minecraft(egui::pos2(0.0,0.0),game,(854,480)),None);
    }
    #[test]
    fn full_window_mode_is_available_for_debugging() {
        let v=crop_video(1920,1080,false,60,20);
        assert_eq!(v.width,1920.0);
        assert_eq!(v.uv.min,egui::pos2(0.0,0.0));
        assert_eq!(v.uv.max,egui::pos2(1.0,1.0));
    }
}
