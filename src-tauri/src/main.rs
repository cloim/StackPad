#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{fs, io::{Read, Write}, net::{TcpStream, SocketAddr}, path::PathBuf, process::{Command, Stdio}, sync::{Arc, Mutex, atomic::{AtomicU64, Ordering}}, thread, time::Duration};
use std::os::windows::process::CommandExt;
use serde_json::{json, Value};
use tauri::{AppHandle, Manager, Monitor, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindow, WebviewWindowBuilder, menu::{Menu, MenuItem, PredefinedMenuItem}, tray::{TrayIconBuilder, TrayIconEvent, MouseButton}};
use tauri_plugin_updater::{Update, UpdaterExt};

// A square window like the 272 x 272 mm MPC One, docked to the bottom-right of the main screen.
const WINDOW_SIDE: f64 = 460.0;
const SCREEN_MARGIN: f64 = 8.0;
// Both dimensions are resizable; keep the four-column pad grid usable.
const MIN_WIDTH: f64 = 360.0;
const MIN_HEIGHT: f64 = 420.0;
mod tray_usage;
mod cli;
mod shared;
use shared::{ENGINE, config_dir, korean, text};

const RELEASES: &str = "https://github.com/cloim/StackPad/releases/latest";

enum Probe { Ready, Other, Free }

fn probe() -> Probe {
    let address: SocketAddr = ENGINE.parse().unwrap();
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else { return Probe::Free; };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    if stream.write_all(format!("GET /api/health HTTP/1.1\r\nHost: {ENGINE}\r\nConnection: close\r\n\r\n").as_bytes()).is_err() { return Probe::Other; }
    let mut reply = String::new();
    let _ = stream.read_to_string(&mut reply);
    if reply.starts_with("HTTP/1.1 200") && reply.contains("\"app\":\"stackpad\"") { Probe::Ready } else { Probe::Other }
}

fn start_engine() -> Result<(), Box<dyn std::error::Error>> {
    match probe() {
        Probe::Ready => return Ok(()),
        Probe::Other => return Err(text("포트 48731을 다른 프로그램이 사용 중입니다. 그 프로그램을 종료한 뒤 StackPad를 다시 실행해 주세요.",
                                        "Another program is using port 48731. Close it and start StackPad again.").into()),
        Probe::Free => {}
    }
    let desktop = std::env::current_exe()?;
    let sibling = desktop.parent().unwrap().join("StackPadEngine.exe");
    let development = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("binaries/StackPadEngine-x86_64-pc-windows-msvc.exe");
    let engine = if sibling.exists() { sibling } else { development };
    if !engine.exists() { return Err(text("관리 엔진 실행 파일을 찾지 못했습니다. StackPad를 다시 설치해 주세요.", "The StackPad engine is missing. Reinstall StackPad.").into()); }
    let command_line = format!("\"{}\" --desktop-exe \"{}\"", engine.display(), desktop.display());
    let literal = command_line.replace('\'', "''");
    let cwd = engine.parent().unwrap().display().to_string().replace('\'', "''");
    let script = format!("$ErrorActionPreference='Stop'; $s=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -Property @{{ShowWindow=[uint16]0}} -ClientOnly; $r=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='{literal}';CurrentDirectory='{cwd}';ProcessStartupInformation=$s}}; if($r.ReturnValue -ne 0){{throw 'WMI launch failed'}}");
    let output = Command::new("powershell.exe").args(["-NoProfile", "-NonInteractive", "-Command", &script]).creation_flags(0x08000000).stdin(Stdio::null()).output()?;
    if !output.status.success() { return Err(String::from_utf8_lossy(&output.stderr).into_owned().into()); }
    for _ in 0..80 {
        if let Probe::Ready = probe() { return Ok(()); }
        thread::sleep(Duration::from_millis(250));
    }
    Err(text("관리 엔진에 연결하지 못했습니다. ~/.config/stackpad/logs/ 에 실행 기록이 있습니다.", "Could not reach the StackPad engine. See the logs in ~/.config/stackpad/logs/.").into())
}

// The engine writes a fresh control token into the user's folder; only this user's tray can read it.
fn shutdown_engine(stop_services: bool) {
    let Some(token) = config_dir().and_then(|dir| fs::read_to_string(dir.join("control-token")).ok()) else { return; };
    let body = json!({ "stop_services": stop_services }).to_string();
    let address: SocketAddr = ENGINE.parse().unwrap();
    if let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(500)) {
        // Stopping every service can take a while, so wait for the answer before the window goes away.
        let _ = stream.set_read_timeout(Some(Duration::from_secs(120)));
        let request = format!("POST /api/engine/shutdown HTTP/1.1\r\nHost: {ENGINE}\r\nContent-Type: application/json\r\nX-StackPad-Control: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", token.trim(), body.len());
        if stream.write_all(request.as_bytes()).is_ok() {
            let mut reply = String::new();
            let _ = stream.read_to_string(&mut reply);
        }
    }
}

// A portable copy has no installer to run, so it only points to the download page.
fn portable() -> bool {
    std::env::current_exe().ok().and_then(|exe| exe.parent().map(|dir| dir.join("portable").exists())).unwrap_or(false)
}

struct Updates { item: MenuItem<tauri::Wry>, pending: Mutex<Option<Update>>, usage: Mutex<Value> }

fn refresh_popup(app: &AppHandle) {
    let state = app.state::<Updates>();
    let data = state.usage.lock().unwrap().clone();
    tray_usage::update(app, data, state.pending.lock().unwrap().is_some());
}

fn watch_usage(app: AppHandle) {
    thread::spawn(move || loop {
        let data = (|| -> Option<Value> {
            let token = fs::read_to_string(config_dir()?.join("control-token")).ok()?;
            let address: SocketAddr = ENGINE.parse().ok()?;
            let mut stream = TcpStream::connect_timeout(&address, Duration::from_millis(500)).ok()?;
            stream.set_read_timeout(Some(Duration::from_secs(15))).ok()?;
            stream.set_write_timeout(Some(Duration::from_secs(2))).ok()?;
            let request = format!("GET /api/desktop/usage HTTP/1.0\r\nHost: {ENGINE}\r\nX-StackPad-Control: {}\r\nConnection: close\r\n\r\n", token.trim());
            stream.write_all(request.as_bytes()).ok()?;
            let mut reply = String::new();
            stream.read_to_string(&mut reply).ok()?;
            let (headers, body) = reply.split_once("\r\n\r\n")?;
            if !headers.starts_with("HTTP/1.1 200 ") { return None; }
            serde_json::from_str(body).ok()
        })();
        *app.state::<Updates>().usage.lock().unwrap() = data.unwrap_or_else(|| json!({"error": true, "providers": []}));
        refresh_popup(&app);
        thread::sleep(Duration::from_secs(60));
    });
}

fn show_alert_toast(app: &AppHandle, alert: &Value) {
    use tauri_plugin_notification::NotificationExt;
    let pad_name = alert["pad_name"].as_str().unwrap_or("StackPad");
    let message = alert["message"].as_str().unwrap_or("");
    let kind = alert["kind"].as_str().unwrap_or("");
    let title = match kind {
        "crashed" => format!("{pad_name}: {}", text("비정상 종료", "Crashed")),
        "restarted" => format!("{pad_name}: {}", text("자동 재시작", "Restarted")),
        "gave_up" => format!("{pad_name}: {}", text("재시작 포기", "Gave up restarting")),
        "unhealthy" => format!("{pad_name}: {}", text("응답 이상", "Unhealthy")),
        "schedule_failed" => format!("{pad_name}: {}", text("예약 실행 실패", "Schedule failed")),
        "scene_failed" => format!("{pad_name}: {}", text("장면 실행 실패", "Scene failed")),
        _ => pad_name.to_string(),
    };
    let _ = app.notification().builder().title(title).body(message).show();
}

fn watch_alerts(app: AppHandle) {
    thread::spawn(move || {
        let mut backoff = 1;
        loop {
            let res = (|| -> Result<(), Box<dyn std::error::Error>> {
                let token = fs::read_to_string(config_dir().ok_or("no config dir")?.join("control-token"))?;
                let address: SocketAddr = ENGINE.parse()?;
                let mut stream = TcpStream::connect_timeout(&address, Duration::from_millis(1000))?;
                stream.set_read_timeout(Some(Duration::from_secs(30)))?;
                let request = format!(
                    "GET /api/events?topics=alert HTTP/1.1\r\nHost: {ENGINE}\r\nX-StackPad-Control: {}\r\nAccept: text/event-stream\r\nConnection: keep-alive\r\n\r\n",
                    token.trim()
                );
                stream.write_all(request.as_bytes())?;
                let mut reader = std::io::BufReader::new(stream);
                let mut status_line = String::new();
                use std::io::BufRead;
                reader.read_line(&mut status_line)?;
                if !status_line.starts_with("HTTP/1.1 200") {
                    return Err("HTTP error".into());
                }
                loop {
                    let mut header = String::new();
                    reader.read_line(&mut header)?;
                    if header == "\r\n" || header == "\n" || header.is_empty() {
                        break;
                    }
                }
                backoff = 1;
                let mut current_event = String::new();
                let mut current_data = String::new();
                loop {
                    let mut line = String::new();
                    if reader.read_line(&mut line)? == 0 {
                        break;
                    }
                    let line = line.trim_end_matches(['\r', '\n']);
                    if line.is_empty() {
                        if current_event == "alert" && !current_data.is_empty() {
                            if let Ok(alert) = serde_json::from_str::<Value>(&current_data) {
                                show_alert_toast(&app, &alert);
                            }
                        }
                        current_event.clear();
                        current_data.clear();
                    } else if let Some(ev) = line.strip_prefix("event: ") {
                        current_event = ev.trim().to_string();
                    } else if let Some(dt) = line.strip_prefix("data: ") {
                        current_data = dt.to_string();
                    }
                }
                Ok(())
            })();

            if res.is_err() {
                thread::sleep(Duration::from_secs(backoff));
                backoff = (backoff * 2).min(60);
            }
        }
    });
}

fn check_updates(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        loop {
            if let Ok(updater) = app.updater() {
                if let Ok(Some(update)) = updater.check().await {
                    let state = app.state::<Updates>();
                    let label = if portable() { text("새 버전 내려받기", "Download new version") } else { text("업데이트 설치", "Install update") };
                    let _ = state.item.set_text(format!("{label} (v{})", update.version));
                    let _ = state.item.set_enabled(true);
                    *state.pending.lock().unwrap() = Some(update);
                    refresh_popup(&app);
                    return;
                }
            }
            tokio_sleep(Duration::from_secs(6 * 60 * 60)).await;
        }
    });
}

async fn tokio_sleep(duration: Duration) {
    let _ = tauri::async_runtime::spawn_blocking(move || thread::sleep(duration)).await;
}

fn install_update(app: &AppHandle) {
    let Some(update) = app.state::<Updates>().pending.lock().unwrap().clone() else { return; };
    if portable() {
        let _ = Command::new("explorer.exe").arg(RELEASES).creation_flags(0x08000000).spawn();
        return;
    }
    let app = app.clone();
    let _ = app.state::<Updates>().item.set_enabled(false);
    tauri::async_runtime::spawn(async move {
        // The installer stops the engine before replacing files; running services keep going.
        if update.download_and_install(|_, _| {}, || {}).await.is_ok() { app.restart(); }
        let _ = app.state::<Updates>().item.set_enabled(true);
    });
}

// Windows adds invisible resize borders on the left, right and bottom only, inside a 1px visible border.
fn hidden_border(window: &WebviewWindow) -> tauri::Result<u32> {
    let (outer, inner) = (window.outer_size()?, window.inner_size()?);
    Ok(((outer.width - inner.width) / 2).saturating_sub(1))
}

// Keep both dimensions within the monitor work area, with a square default.
fn fit(window: &WebviewWindow, monitor: &Monitor, width: Option<u32>, height: Option<u32>) -> tauri::Result<()> {
    let scale = monitor.scale_factor();
    let side = (WINDOW_SIDE * scale).round() as u32;
    let (outer, inner) = (window.outer_size()?, window.inner_size()?);
    let (frame_w, frame_h) = (outer.width - inner.width, outer.height - inner.height);
    let hidden = (frame_w / 2).saturating_sub(1);
    let max_w = monitor.work_area().size.width.saturating_sub(frame_w - 2 * hidden).max(1);
    let max_h = (monitor.work_area().size.height + hidden).saturating_sub(frame_h).max(1);
    let min_w = ((MIN_WIDTH * scale).round() as u32).min(max_w);
    let min_h = ((MIN_HEIGHT * scale).round() as u32).min(max_h);
    window.set_min_size(Some(PhysicalSize::new(min_w, min_h)))?;
    window.set_max_size(Some(PhysicalSize::new(max_w, max_h)))?;
    let width = width.unwrap_or(side.saturating_sub(frame_w - 2 * hidden));
    let height = height.unwrap_or((side + hidden).saturating_sub(frame_h));
    window.set_size(PhysicalSize::new(width.clamp(min_w, max_w), height.clamp(min_h, max_h)))
}

// The monitor whose work area holds the title bar, so the window can still be dragged back.
fn monitor_at(window: &WebviewWindow, position: PhysicalPosition<i32>, width: u32) -> tauri::Result<Option<Monitor>> {
    let (x, y) = (position.x + width as i32 / 2, position.y + 10);
    Ok(window.available_monitors()?.into_iter().find(|monitor| {
        let work = monitor.work_area();
        x >= work.position.x && x < work.position.x + work.size.width as i32 && y >= work.position.y && y < work.position.y + work.size.height as i32
    }))
}

// Dock to the bottom-right of the main screen, keeping the user's height on later docks.
fn dock(window: &WebviewWindow, keep_height: bool) -> tauri::Result<()> {
    let Some(monitor) = window.primary_monitor()?.or(window.current_monitor()?) else { return Ok(()); };
    let size = if keep_height { Some(window.inner_size()?) } else { None };
    fit(window, &monitor, size.map(|s| s.width), size.map(|s| s.height))?;
    let (outer, hidden, work) = (window.outer_size()?, hidden_border(window)?, monitor.work_area());
    let margin = (SCREEN_MARGIN * monitor.scale_factor()).round() as i32;
    window.set_position(PhysicalPosition::new(
        work.position.x + work.size.width as i32 - outer.width as i32 + hidden as i32 - margin,
        (work.position.y + work.size.height as i32 - outer.height as i32 + hidden as i32 - margin).max(work.position.y),
    ))
}

fn state_path() -> Option<PathBuf> {
    std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(|dir| PathBuf::from(dir).join(".config").join("stackpad").join("window.json"))
}

// Put the window back where the user left it; false when no saved place is on a connected screen.
fn restore(window: &WebviewWindow) -> tauri::Result<bool> {
    let Some(state) = state_path().and_then(|path| fs::read_to_string(path).ok()).and_then(|text| serde_json::from_str::<Value>(&text).ok()) else { return Ok(false); };
    let (Some(x), Some(y), Some(height)) = (state["x"].as_i64(), state["y"].as_i64(), state["height"].as_u64()) else { return Ok(false); };
    let position = PhysicalPosition::new(x as i32, y as i32);
    let Some(monitor) = monitor_at(window, position, window.outer_size()?.width)? else { return Ok(false); };
    window.set_position(position)?;
    fit(window, &monitor, state["width"].as_u64().map(|width| width as u32), Some(height as u32))?;
    window.set_position(position)?;
    Ok(true)
}

fn save(window: &WebviewWindow) {
    if window.is_minimized().unwrap_or(true) || !window.is_visible().unwrap_or(false) { return; }
    let (Ok(position), Ok(size), Some(path)) = (window.outer_position(), window.inner_size(), state_path()) else { return; };
    let _ = fs::create_dir_all(path.parent().unwrap());
    let _ = fs::write(path, json!({ "x": position.x, "y": position.y, "width": size.width, "height": size.height }).to_string());
}

// Moves and resizes arrive in bursts while dragging, so write once they settle.
fn schedule_save(window: &WebviewWindow, pending: &Arc<AtomicU64>) {
    let ticket = pending.fetch_add(1, Ordering::SeqCst) + 1;
    let (window, pending) = (window.clone(), pending.clone());
    thread::spawn(move || {
        thread::sleep(Duration::from_millis(400));
        if pending.load(Ordering::SeqCst) == ticket { save(&window); }
    });
}

fn show(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        // Keep the user's place, and dock again only when that screen is gone.
        let on_screen = window.outer_position().ok().and_then(|position| monitor_at(&window, position, window.outer_size().ok()?.width).ok().flatten()).is_some();
        if !on_screen { let _ = dock(&window, true); }
        let _ = window.show(); let _ = window.set_focus();
    }
}

fn main() {
    // Commands such as `StackPad.exe pad list` print their answer and exit before any window or tray starts.
    let args: Vec<String> = std::env::args().collect();
    if cli::requested(&args) { std::process::exit(cli::run(&args[1..])); }
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| show(app)))
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            if let Err(error) = start_engine() {
                // Without the engine there is nothing to show, so explain and exit.
                let message = error.to_string().replace('\'', "''");
                let script = format!("Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('{message}', 'StackPad') | Out-Null");
                let _ = Command::new("powershell.exe").args(["-NoProfile", "-NonInteractive", "-Command", &script]).creation_flags(0x08000000).stdin(Stdio::null()).status();
                return Err(error);
            }
            let hidden = std::env::args().any(|arg| arg == "--hidden");
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::External(format!("http://{ENGINE}").parse()?))
                // Let WebView2 deliver HTML drag/drop to pad and padset controls on Windows.
                .disable_drag_drop_handler()
                .title("StackPad").inner_size(WINDOW_SIDE, WINDOW_SIDE).resizable(true).maximizable(false).visible(false).skip_taskbar(true).build()?;
            if !restore(&window)? { dock(&window, false)?; }
            if !hidden { window.show()?; }
            let (handle, pending) = (window.clone(), Arc::new(AtomicU64::new(0)));
            window.on_window_event(move |event| match event {
                tauri::WindowEvent::CloseRequested { api, .. } => { api.prevent_close(); save(&handle); let _ = handle.hide(); }
                tauri::WindowEvent::Moved(_) | tauri::WindowEvent::Resized(_) => schedule_save(&handle, &pending),
                // Update both size limits when crossing to a screen with another scale.
                tauri::WindowEvent::ScaleFactorChanged { .. } => {
                    let (window, pending) = (handle.clone(), pending.clone());
                    thread::spawn(move || {
                        thread::sleep(Duration::from_millis(100));
                        if let (Ok(Some(monitor)), Ok(size)) = (window.current_monitor(), window.inner_size()) { let _ = fit(&window, &monitor, Some(size.width), Some(size.height)); }
                        schedule_save(&window, &pending);
                    });
                }
                _ => {}
            });
            let open = MenuItem::with_id(app, "open", text("StackPad 열기", "Open StackPad"), true, None::<&str>)?;
            let update = MenuItem::with_id(app, "update", text("최신 버전입니다", "Up to date"), false, None::<&str>)?;
            let close = MenuItem::with_id(app, "close", text("앱 닫기 (엔진과 서비스 유지)", "Close app (keep engine and services)"), true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", text("완전 종료 (서비스 유지)", "Quit StackPad (keep services)"), true, None::<&str>)?;
            let quit_all = MenuItem::with_id(app, "quit-all", text("완전 종료 (서비스도 중지)", "Quit StackPad and stop services"), true, None::<&str>)?;
            let separator = PredefinedMenuItem::separator(app)?;
            let menu = Menu::with_items(app, &[&open, &update, &separator, &close, &quit, &quit_all])?;
            app.manage(Updates { item: update, pending: Mutex::new(None), usage: Mutex::new(Value::Null) });
            tray_usage::init(app.handle())?;
            TrayIconBuilder::with_id("main").icon(app.default_window_icon().unwrap().clone()).menu(&menu).show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show(app),
                    "update" => install_update(app),
                    "close" => app.exit(0),
                    "quit" | "quit-all" => {
                        let stop_services = event.id.as_ref() == "quit-all";
                        if let Some(window) = app.get_webview_window("main") { let _ = window.hide(); }
                        let app = app.clone();
                        thread::spawn(move || { shutdown_engine(stop_services); app.exit(0); });
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| match event {
                    TrayIconEvent::Enter { rect, .. } | TrayIconEvent::Move { rect, .. } => tray_usage::hover(tray.app_handle(), rect),
                    TrayIconEvent::DoubleClick { button: MouseButton::Left, .. } => { tray_usage::dismiss(tray.app_handle()); show(tray.app_handle()); }
                    TrayIconEvent::Click { .. } => tray_usage::dismiss(tray.app_handle()),
                    _ => {}
                }).build(app)?;
            check_updates(app.handle().clone());
            watch_usage(app.handle().clone());
            watch_alerts(app.handle().clone());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("StackPad failed to start");
}
