// Shared by the desktop app and the stackpad-cli console companion.
use std::path::PathBuf;

pub const ENGINE: &str = "127.0.0.1:48731";

// Tray and error texts follow the Windows display language.
pub fn korean() -> bool {
    sys_locale::get_locale().map(|locale| locale.to_lowercase().starts_with("ko")).unwrap_or(false)
}

pub fn text(ko: &str, en: &str) -> String {
    if korean() { ko.into() } else { en.into() }
}

pub fn config_dir() -> Option<PathBuf> {
    std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME")).map(|dir| PathBuf::from(dir).join(".config").join("stackpad"))
}
