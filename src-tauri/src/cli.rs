// `StackPad.exe pad list` and friends for agents: the engine runs the command and this prints its answer.
use std::{ffi::c_void, fs, io::{Read, Write}, net::{SocketAddr, TcpStream, ToSocketAddrs}, path::PathBuf, time::Duration};
use serde_json::{json, Value};

const COMMANDS: [&str; 7] = ["help", "--help", "-h", "version", "--version", "padset", "pad"];
const STD_OUTPUT: u32 = -11i32 as u32;
const STD_ERROR: u32 = -12i32 as u32;
const ATTACH_PARENT_PROCESS: u32 = u32::MAX;

#[link(name = "kernel32")]
extern "system" {
    fn AttachConsole(process: u32) -> i32;
    fn GetStdHandle(kind: u32) -> *mut c_void;
    fn GetConsoleMode(handle: *mut c_void, mode: *mut u32) -> i32;
    fn WriteConsoleW(handle: *mut c_void, buffer: *const u16, length: u32, written: *mut u32, reserved: *mut c_void) -> i32;
    fn CreateFileW(name: *const u16, access: u32, share: u32, security: *mut c_void, disposition: u32, flags: u32, template: *mut c_void) -> *mut c_void;
}

pub fn requested(args: &[String]) -> bool {
    args.get(1).is_some_and(|first| COMMANDS.contains(&first.as_str()))
}

fn usable(handle: *mut c_void) -> bool {
    !handle.is_null() && handle as isize != -1
}

// The release app has no console of its own. Pipes from agents and scripts arrive as standard handles;
// a terminal without redirection is reached by joining the parent's console.
struct Output { console: Option<*mut c_void> }

impl Output {
    fn new() -> Self {
        let redirected = unsafe { usable(GetStdHandle(STD_OUTPUT)) || usable(GetStdHandle(STD_ERROR)) };
        if redirected || unsafe { AttachConsole(ATTACH_PARENT_PROCESS) } == 0 { return Output { console: None }; }
        if unsafe { usable(GetStdHandle(STD_OUTPUT)) } { return Output { console: None }; }
        let name: Vec<u16> = "CONOUT$\0".encode_utf16().collect();
        // GENERIC_READ | GENERIC_WRITE, FILE_SHARE_WRITE, OPEN_EXISTING
        let handle = unsafe { CreateFileW(name.as_ptr(), 0xC000_0000, 0x2, std::ptr::null_mut(), 3, 0, std::ptr::null_mut()) };
        Output { console: usable(handle).then_some(handle) }
    }

    fn write(&self, text: &str, error: bool) {
        if text.is_empty() { return; }
        // Rust writes UTF-16 to a console and UTF-8 bytes to a pipe or file.
        let standard = |to_error: bool| if to_error { let _ = std::io::stderr().write_all(text.as_bytes()); } else { let mut out = std::io::stdout(); let _ = out.write_all(text.as_bytes()); let _ = out.flush(); };
        if unsafe { usable(GetStdHandle(if error { STD_ERROR } else { STD_OUTPUT })) } { return standard(error); }
        if let Some(console) = self.console {
            let mut mode = 0;
            if unsafe { GetConsoleMode(console, &mut mode) } != 0 {
                let wide: Vec<u16> = text.encode_utf16().collect();
                let mut written = 0;
                unsafe { WriteConsoleW(console, wide.as_ptr(), wide.len() as u32, &mut written, std::ptr::null_mut()); }
            }
            return;
        }
        // Only one stream was captured; keep the message rather than lose it.
        if unsafe { usable(GetStdHandle(if error { STD_OUTPUT } else { STD_ERROR })) } { standard(!error); }
    }

    fn line(&self, text: &str, error: bool) {
        if text.is_empty() { return; }
        self.write(&if text.ends_with('\n') { text.to_string() } else { format!("{text}\n") }, error);
    }
}

fn engine_address() -> String {
    std::env::var("STACKPAD_ENGINE").ok().filter(|value| !value.trim().is_empty()).unwrap_or_else(|| crate::ENGINE.to_string())
}

fn token_file() -> Option<PathBuf> {
    let folder = std::env::var_os("STACKPAD_CONFIG_DIR").map(PathBuf::from).or_else(crate::config_dir)?;
    Some(folder.join("control-token"))
}

enum Failure { Unreachable(String), Rejected(String) }

fn request(address: &str, body: &str) -> Result<Value, Failure> {
    let not_running = || Failure::Unreachable(crate::text(
        "StackPad 엔진에 연결하지 못했습니다. StackPad를 실행한 다음 다시 시도해 주세요. (예: StackPad.exe --hidden)",
        "Could not reach the StackPad engine. Start StackPad and try again (for example StackPad.exe --hidden)."));
    let token = token_file().and_then(|path| fs::read_to_string(path).ok()).ok_or_else(not_running)?;
    let target: SocketAddr = address.to_socket_addrs().ok().and_then(|mut found| found.next()).ok_or_else(not_running)?;
    let mut stream = TcpStream::connect_timeout(&target, Duration::from_millis(800)).map_err(|_| not_running())?;
    // Group starts wait for each component, so give long commands time to answer.
    let _ = stream.set_read_timeout(Some(Duration::from_secs(600)));
    let lang = if crate::korean() { "ko" } else { "en" };
    let head = format!("POST /api/cli HTTP/1.0\r\nHost: {address}\r\nContent-Type: application/json\r\nX-StackPad-Control: {}\r\nX-StackPad-Lang: {lang}\r\nContent-Length: {}\r\n\r\n", token.trim(), body.len());
    stream.write_all(head.as_bytes()).and_then(|_| stream.write_all(body.as_bytes())).map_err(|_| not_running())?;
    let mut reply = Vec::new();
    stream.read_to_end(&mut reply).map_err(|_| not_running())?;
    let reply = String::from_utf8_lossy(&reply);
    let (headers, content) = reply.split_once("\r\n\r\n").ok_or_else(not_running)?;
    let status = headers.split_whitespace().nth(1).unwrap_or("");
    let data: Value = serde_json::from_str(content).unwrap_or(Value::Null);
    match status {
        "200" => Ok(data),
        "403" => Err(Failure::Rejected(crate::text(
            "엔진이 요청을 거부했습니다. StackPad를 다시 시작한 다음 시도해 주세요.",
            "The engine refused the request. Restart StackPad and try again."))),
        _ => Err(Failure::Rejected(data["detail"].as_str().map(str::to_string).unwrap_or_else(|| format!("HTTP {status}")))),
    }
}

pub fn run(args: &[String]) -> i32 {
    let output = Output::new();
    let mut args: Vec<String> = args.to_vec();
    match args[0].as_str() { "--help" | "-h" => args[0] = "help".into(), "--version" => args[0] = "version".into(), _ => {} }
    let mut stdin = String::new();
    if args.iter().any(|arg| arg == "-" || arg == "--json=-") {
        let mut bytes = Vec::new();
        let _ = std::io::stdin().read_to_end(&mut bytes);
        stdin = String::from_utf8_lossy(&bytes).trim_start_matches('\u{feff}').to_string();
    }
    let cwd = std::env::current_dir().map(|dir| dir.display().to_string()).unwrap_or_default();
    let body = json!({ "args": args, "cwd": cwd, "stdin": stdin }).to_string();
    match request(&engine_address(), &body) {
        Ok(answer) => {
            output.write(answer["output"].as_str().unwrap_or(""), false);
            output.line(answer["error"].as_str().unwrap_or(""), true);
            answer["exit_code"].as_i64().unwrap_or(1) as i32
        }
        Err(Failure::Unreachable(message)) => { output.line(&message, true); 3 }
        Err(Failure::Rejected(message)) => { output.line(&message, true); 1 }
    }
}
