// A console build of the command line: PowerShell and cmd wait for it and capture its output,
// which they do not do for the windowed StackPad.exe.
#[path = "../shared.rs"]
mod shared;
// Command detection is only for the windowed app, which also starts the screen.
#[allow(dead_code)]
#[path = "../cli.rs"]
mod cli;
use shared::{ENGINE, config_dir, korean, text};

fn main() {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() { args.push("help".into()); }
    std::process::exit(cli::run(&args));
}
