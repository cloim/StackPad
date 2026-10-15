use std::{sync::{Mutex, atomic::{AtomicBool, Ordering}}, thread, time::{Duration, Instant}};
use serde_json::{json, Value};
use tauri::{AppHandle, Manager, PhysicalPosition, PhysicalSize, Rect, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

#[derive(Clone, Copy, Debug)]
struct Area { x: f64, y: f64, width: f64, height: f64 }

impl Area {
    fn contains(self, point: PhysicalPosition<f64>) -> bool {
        point.x >= self.x && point.y >= self.y && point.x < self.x + self.width && point.y < self.y + self.height
    }
}

struct Popup {
    data: Mutex<Value>,
    icon: Mutex<Option<Area>>,
    suppressed: AtomicBool,
}

fn placement(icon: Area, work: Area, width: f64, height: f64, gap: f64) -> PhysicalPosition<i32> {
    let x = (icon.x + icon.width / 2.0 - width / 2.0).clamp(work.x, (work.x + work.width - width).max(work.x));
    let y = if icon.y - height - gap >= work.y { icon.y - height - gap } else { icon.y + icon.height + gap };
    PhysicalPosition::new(x.round() as i32, y.clamp(work.y, (work.y + work.height - height).max(work.y)).round() as i32)
}

fn present(window: &WebviewWindow, icon: Area, data: &Value) -> tauri::Result<()> {
    let Some(monitor) = window.monitor_from_point(icon.x + icon.width / 2.0, icon.y + icon.height / 2.0)? else { return Ok(()); };
    let scale = monitor.scale_factor();
    let work = monitor.work_area();
    let work = Area { x: work.position.x as f64, y: work.position.y as f64, width: work.size.width as f64, height: work.size.height as f64 };
    let rows: usize = data["providers"].as_array().into_iter().flatten().map(|provider|
        46 + 26 * provider["windows"].as_array().map(|windows| windows.len().max(1)).unwrap_or(1)
    ).sum();
    let width = (360.0 * scale).min(work.width);
    let height = ((64.0 + rows.max(58) as f64) * scale).min(work.height);
    window.set_size(PhysicalSize::new(width as u32, height as u32))?;
    window.set_position(placement(icon, work, width, height, 6.0 * scale))?;
    window.show()
}

fn publish(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("tray-usage") {
        let data = app.state::<Popup>().data.lock().unwrap().clone();
        let _ = window.eval(format!("window.__STACKPAD_USAGE__={data};window.dispatchEvent(new Event('stackpad-usage'));"));
    }
}

pub fn update(app: &AppHandle, mut data: Value, update_available: bool) {
    data["update_available"] = json!(update_available);
    *app.state::<Popup>().data.lock().unwrap() = data.clone();
    if let Some(window) = app.get_webview_window("tray-usage") {
        let icon = *app.state::<Popup>().icon.lock().unwrap();
        if let Some(icon) = icon.filter(|_| window.is_visible().unwrap_or(false)) {
            let _ = present(&window, icon, &data);
        }
    }
    publish(app);
}

pub fn hover(app: &AppHandle, rect: Rect) {
    // Tray events always supply physical coordinates, including on scaled displays.
    let position = rect.position.to_physical::<f64>(1.0);
    let size = rect.size.to_physical::<f64>(1.0);
    *app.state::<Popup>().icon.lock().unwrap() = Some(Area { x: position.x, y: position.y, width: size.width, height: size.height });
}

pub fn dismiss(app: &AppHandle) {
    app.state::<Popup>().suppressed.store(true, Ordering::SeqCst);
    if let Some(window) = app.get_webview_window("tray-usage") { let _ = window.hide(); }
}

pub fn init(app: &AppHandle) -> tauri::Result<()> {
    app.manage(Popup { data: Mutex::new(Value::Null), icon: Mutex::new(None), suppressed: AtomicBool::new(false) });
    let window = WebviewWindowBuilder::new(app, "tray-usage", WebviewUrl::External(format!("http://{}/tray-usage.html", super::ENGINE).parse().unwrap()))
        .title(super::text("StackPad 사용량", "StackPad Usage")).inner_size(360.0, 250.0).decorations(false).resizable(false)
        .always_on_top(true).skip_taskbar(true).visible(false).focused(false).focusable(false)
        .initialization_script("window.__STACKPAD_USAGE__=null;")
        .on_page_load(|window, _| publish(window.app_handle()))
        .build()?;
    let app = app.clone();
    thread::spawn(move || {
        let (mut entered, mut left) = (None::<Instant>, None::<Instant>);
        loop {
            thread::sleep(Duration::from_millis(50));
            let state = app.state::<Popup>();
            let icon = *state.icon.lock().unwrap();
            let (Some(icon), Ok(cursor)) = (icon, app.cursor_position()) else { continue; };
            let on_icon = icon.contains(cursor);
            let visible = window.is_visible().unwrap_or(false);
            if state.suppressed.load(Ordering::SeqCst) {
                entered = None;
                if !on_icon { state.suppressed.store(false, Ordering::SeqCst); }
                continue;
            }
            let on_popup = visible && window.outer_position().ok().zip(window.outer_size().ok()).map(|(position, size)|
                Area { x: position.x as f64, y: position.y as f64, width: size.width as f64, height: size.height as f64 }.contains(cursor)
            ).unwrap_or(false);
            if on_icon || on_popup {
                left = None;
                if !visible && entered.get_or_insert_with(Instant::now).elapsed() >= Duration::from_millis(250) {
                    let data = state.data.lock().unwrap().clone();
                    let _ = present(&window, icon, &data);
                    publish(&app);
                }
            } else {
                entered = None;
                if visible && left.get_or_insert_with(Instant::now).elapsed() >= Duration::from_millis(350) {
                    let _ = window.hide();
                    left = None;
                }
            }
        }
    });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn popup_stays_on_the_icons_monitor_for_every_taskbar_edge() {
        for scale in [1.0, 1.5, 2.0] {
            let work = Area { x: -1920.0, y: -200.0, width: 1920.0, height: 1080.0 };
            for (x, y) in [(-1900.0, 860.0), (-20.0, 860.0), (-1900.0, -220.0), (-1940.0, 500.0), (0.0, 500.0)] {
                let icon = Area { x, y, width: 20.0, height: 20.0 };
                let position = placement(icon, work, 360.0 * scale, 432.0 * scale, 6.0 * scale);
                assert!(position.x as f64 >= work.x && position.y as f64 >= work.y);
                assert!(position.x as f64 + 360.0 * scale <= work.x + work.width);
                assert!(position.y as f64 + 432.0 * scale <= work.y + work.height);
            }
        }
    }
}
