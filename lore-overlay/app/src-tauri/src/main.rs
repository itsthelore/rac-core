// Desktop entrypoint. Not built/run in this repo — see ../../README.md.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    lore_capture_overlay_lib::run()
}
